package com.instantmechanic.dispatch

import com.instantmechanic.dispatch.adapters.booking.SqliteBookingRepository
import com.instantmechanic.dispatch.adapters.http.FanoutPublisher
import com.instantmechanic.dispatch.adapters.http.HubPublisher
import com.instantmechanic.dispatch.adapters.http.WebSocketHub
import com.instantmechanic.dispatch.adapters.kafka.KafkaEventPublisher
import com.instantmechanic.dispatch.adapters.ranking.MlEtaRankingStrategy
import com.instantmechanic.dispatch.adapters.ranking.NearestAvailableStrategy
import com.instantmechanic.dispatch.adapters.redis.RedisOfferLockStore
import com.instantmechanic.dispatch.adapters.redis.RedisPresenceStore
import com.instantmechanic.dispatch.adapters.spatial.H3SpatialIndex
import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.MechanicStatus
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.RejectionReason
import com.instantmechanic.dispatch.domain.model.Telemetry
import com.instantmechanic.dispatch.domain.port.EventPublisher
import com.instantmechanic.dispatch.domain.usecase.DispatchStateMachine
import com.instantmechanic.dispatch.domain.usecase.OfferCascade
import com.instantmechanic.dispatch.domain.usecase.TelemetryHandler
import io.ktor.http.HttpStatusCode
import io.ktor.serialization.kotlinx.json.json
import io.ktor.server.application.install
import io.ktor.server.engine.embeddedServer
import io.ktor.server.netty.Netty
import io.ktor.server.plugins.contentnegotiation.ContentNegotiation
import io.ktor.server.request.receive
import io.ktor.server.response.respond
import io.ktor.server.routing.get
import io.ktor.server.routing.post
import io.ktor.server.routing.route
import io.ktor.server.routing.routing
import io.ktor.server.websocket.WebSockets
import io.ktor.server.websocket.webSocket
import io.ktor.websocket.close
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import java.util.UUID
import java.util.concurrent.ConcurrentHashMap

@Serializable data class TelemetryDto(
    val mechanic_id: String, val status: String, val lat: Double, val lon: Double,
    val skills: List<String> = emptyList(), val speed_kmh: Double = 0.0, val heading: Double = 0.0,
)
@Serializable data class BookingDto(
    val booking_id: String? = null, val required_skill: String, val urgency: String = "medium",
    val lat: Double, val lon: Double,
)
@Serializable data class OfferActionDto(val mechanic_id: String)
@Serializable data class StatusDto(val to: String)
@Serializable data class Message(val message: String)

fun main() {
    val redisUrl = System.getenv("REDIS_URL") ?: "redis://localhost:6379/0"
    val kafkaBrokers = System.getenv("REDPANDA_BROKERS") ?: "localhost:9092"
    val rankerUrl = System.getenv("AI_SERVICE_URL") ?: "http://localhost:8000"
    val useMl = System.getenv("ENABLE_ML_RANKING")?.equals("true", ignoreCase = true) == true

    val redisClient = io.lettuce.core.RedisClient.create(redisUrl)
    val spatial = H3SpatialIndex()
    val presence = RedisPresenceStore(redisClient)
    val locks = RedisOfferLockStore(redisClient)
    val bookings = SqliteBookingRepository()
    val hub = WebSocketHub()
    val publisher: EventPublisher = FanoutPublisher(
        listOf(KafkaEventPublisher(kafkaBrokers), HubPublisher(hub)),
    )
    val ranking = if (useMl) MlEtaRankingStrategy(rankerUrl) else NearestAvailableStrategy()

    val telemetryHandler = TelemetryHandler(spatial, presence, publisher)
    val cascade = OfferCascade(spatial, presence, locks, bookings, ranking, publisher)
    val stateMachine = DispatchStateMachine()
    val offerIndex = ConcurrentHashMap<OfferId, Pair<BookingId, MechanicId>>()

    embeddedServer(Netty, port = 8081, host = "0.0.0.0") {
        install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
        install(WebSockets)
        routing {
            route("/api/dispatch") {
                get("/health/") { call.respond(Message("ok")) }

                post("/telemetry/") {
                    val dto = call.receive<TelemetryDto>()
                    val result = telemetryHandler.handle(
                        Telemetry(
                            mechanicId = MechanicId(uuid(dto.mechanic_id)),
                            status = runCatching { MechanicStatus.valueOf(dto.status) }
                                .getOrDefault(MechanicStatus.OFFLINE),
                            lat = dto.lat, lon = dto.lon, skills = dto.skills.toSet(),
                            speedKmh = dto.speed_kmh, heading = dto.heading,
                        ),
                    )
                    if (result == null) {
                        call.respond(HttpStatusCode.BadRequest, Message("invalid telemetry"))
                    } else {
                        call.respond(mapOf("h3_res8" to result.h3Res8, "h3_res7" to result.h3Res7))
                    }
                }

                post("/bookings/") {
                    val dto = call.receive<BookingDto>()
                    val id = BookingId(dto.booking_id?.let { uuid(it) } ?: UUID.randomUUID())
                    val res8 = spatial.cell(dto.lat, dto.lon, 8)
                    bookings.save(
                        Booking(id, dto.required_skill, dto.urgency, res8, spatial.parent(res8, 7), dto.lat, dto.lon),
                    )
                    call.respond(HttpStatusCode.Created, mapOf("booking_id" to id.value.toString()))
                }

                post("/bookings/{id}/dispatch/") {
                    val id = BookingId(uuid(call.parameters["id"]))
                    when (val result = cascade.dispatch(id)) {
                        is com.instantmechanic.dispatch.domain.usecase.DispatchResult.Offered -> {
                            offerIndex[result.offer.id] = id to result.offer.mechanicId
                            call.respond(
                                mapOf(
                                    "status" to "OFFERED", "offer_id" to result.offer.id.value.toString(),
                                    "mechanic_id" to result.offer.mechanicId.value.toString(),
                                    "eta_seconds" to result.offer.etaSeconds, "ring" to result.offer.ring,
                                    "hotline" to com.instantmechanic.dispatch.domain.model.EMERGENCY_HOTLINE,
                                ),
                            )
                        }
                        is com.instantmechanic.dispatch.domain.usecase.DispatchResult.Escalated ->
                            call.respond(
                                mapOf(
                                    "status" to "ESCALATED",
                                    "hotline" to com.instantmechanic.dispatch.domain.model.EMERGENCY_HOTLINE,
                                ),
                            )
                        is com.instantmechanic.dispatch.domain.usecase.DispatchResult.NotFound ->
                            call.respond(HttpStatusCode.NotFound, Message("booking not found"))
                        else -> call.respond(HttpStatusCode.Conflict, Message("booking already handled"))
                    }
                }

                post("/offers/{id}/accept/") {
                    val offerId = OfferId(uuid(call.parameters["id"]))
                    val body = call.receive<OfferActionDto>()
                    val pair = offerIndex[offerId]
                    if (pair == null || pair.second != MechanicId(uuid(body.mechanic_id))) {
                        call.respond(HttpStatusCode.NotFound, Message("offer not found"))
                        return@post
                    }
                    when (cascade.accept(pair.first, offerId, pair.second)) {
                        is com.instantmechanic.dispatch.domain.usecase.DispatchResult.Assigned ->
                            call.respond(mapOf("status" to "ASSIGNED"))
                        else -> call.respond(HttpStatusCode.Conflict, Message("offer lost"))
                    }
                }

                post("/offers/{id}/reject/") {
                    val offerId = OfferId(uuid(call.parameters["id"]))
                    val body = call.receive<OfferActionDto>()
                    val pair = offerIndex[offerId]
                    if (pair == null) {
                        call.respond(HttpStatusCode.NotFound, Message("offer not found"))
                        return@post
                    }
                    cascade.reject(pair.first, offerId, pair.second, RejectionReason.DECLINED)
                    call.respond(Message("rejected"))
                }

                post("/jobs/{id}/status/") {
                    val id = BookingId(uuid(call.parameters["id"]))
                    val to = runCatching { JobStatus.valueOf(call.receive<StatusDto>().to) }
                        .getOrDefault(JobStatus.SEARCHING)
                    if (cascade.advance(id, to)) call.respond(mapOf("status" to to.name))
                    else call.respond(HttpStatusCode.BadRequest, Message("illegal transition"))
                }

                webSocket("/ws/jobs/{id}") {
                    val key = uuid(call.parameters["id"]).toString()
                    hub.register(key, this)
                    try {
                        for (frame in incoming) {
                            if (frame is io.ktor.websocket.Frame.Close) break
                        }
                    } finally {
                        hub.unregister(key, this)
                        close()
                    }
                }
            }
        }
    }.start(wait = true)
}

private fun uuid(value: String?): UUID =
    value?.let { runCatching { UUID.fromString(it) }.getOrNull() }
        ?: throw IllegalArgumentException("invalid uuid: $value")
