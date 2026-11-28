package com.instantmechanic.dispatch.adapters.ranking

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.Candidate
import com.instantmechanic.dispatch.domain.model.RankedMechanic
import com.instantmechanic.dispatch.domain.port.RankingStrategy
import com.uber.h3core.H3Core
import io.ktor.client.HttpClient
import io.ktor.client.call.body
import io.ktor.client.engine.okhttp.OkHttp
import io.ktor.client.plugins.contentnegotiation.ContentNegotiation
import io.ktor.client.request.post
import io.ktor.client.request.setBody
import io.ktor.http.ContentType
import io.ktor.http.contentType
import io.ktor.serialization.kotlinx.json.json
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json

/** Fast, deterministic fallback used when the ML ranker is unavailable or slow (<300ms). */
class NearestAvailableStrategy : RankingStrategy {
    private val h3 = H3Core.newInstance()

    override fun rank(booking: Booking, candidates: List<Candidate>): List<RankedMechanic> =
        candidates.mapNotNull { candidate ->
            val steps = try {
                h3.gridDistance(booking.h3Res8, candidate.h3Res8).toInt()
            } catch (_: Exception) {
                return@mapNotNull null
            }
            val eta = (steps.coerceAtLeast(1) * 75).coerceAtMost(1800)
            RankedMechanic(candidate.mechanicId, eta, 1.0 / (1.0 + steps))
        }.sortedByDescending { it.score }
}

/**
 * Calls the Python ranker (`POST /rank/eta`) and falls back to nearest-distance
 * on any failure or a slow response. OCP: swapped in without touching the cascade.
 */
class MlEtaRankingStrategy(
    private val serviceUrl: String,
    private val timeoutMs: Long = 300,
    private val fallback: RankingStrategy = NearestAvailableStrategy(),
) : RankingStrategy {
    private val client = HttpClient(OkHttp) {
        install(ContentNegotiation) { json(Json { ignoreUnknownKeys = true }) }
    }

    @Serializable
    data class RankRequest(
        val booking_id: String,
        val origin_h3: String,
        val candidates: List<CandidateDto>,
    )

    @Serializable
    data class CandidateDto(val mechanic_id: String, val h3_res8: String, val lat: Double, val lon: Double)

    @Serializable
    data class RankResponse(val rankings: List<RankDto>)

    @Serializable
    data class RankDto(val mechanic_id: String, val eta_seconds: Int, val score: Double)

    override fun rank(booking: Booking, candidates: List<Candidate>): List<RankedMechanic> {
        // kotlinx.coroutines.runBlocking is acceptable here: Ktor routes already
        // dispatch blocking ranking onto Dispatchers.IO.
        return try {
            kotlinx.coroutines.runBlocking {
                withTimeoutOrNullCompat(timeoutMs) {
                    val response = client.post("$serviceUrl/rank/eta") {
                        contentType(ContentType.Application.Json)
                        setBody(
                            RankRequest(
                                booking.id.value.toString(), booking.h3Res8,
                                candidates.map {
                                    CandidateDto(
                                        it.mechanicId.value.toString(), it.h3Res8, it.lat, it.lon
                                    )
                                },
                            ),
                        )
                    }
                    val dto: RankResponse = response.body()
                    val byId = dto.rankings.associateBy { it.mechanic_id }
                    candidates.mapNotNull { c ->
                        byId[c.mechanicId.value.toString()]?.let {
                            RankedMechanic(c.mechanicId, it.eta_seconds, it.score)
                        }
                    }.ifEmpty { fallback.rank(booking, candidates) }
                } ?: fallback.rank(booking, candidates)
            }
        } catch (_: Exception) {
            fallback.rank(booking, candidates)
        }
    }

    private suspend fun <T> withTimeoutOrNullCompat(
        ms: Long,
        block: suspend kotlinx.coroutines.CoroutineScope.() -> T,
    ): T? = kotlinx.coroutines.withTimeoutOrNull(ms, block)
}
