package com.instantmechanic.dispatch.domain.events

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.Offer
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.PositionedTelemetry
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.time.Instant
import java.util.UUID

/** Builds contract envelopes defined under contracts/events. No broker imports. */
object Events {
    private const val PRODUCER = "dispatch-service"
    private const val VERSION = 1

    private fun envelope(eventType: String, bookingId: BookingId?) = buildJsonObject {
        put("event_id", UUID.randomUUID().toString())
        put("event_type", eventType)
        put("schema_version", VERSION)
        put("occurred_at", Instant.now().toString())
        put("producer", PRODUCER)
        if (bookingId != null) put("booking_id", bookingId.value.toString())
    }.toMap().toMutableMap()

    fun telemetryUpdated(t: PositionedTelemetry): String = buildJsonObject {
        val env = envelope("mechanic.telemetry.updated", null)
        env.forEach { (k, v) -> put(k, v) }
        put("mechanic_id", t.mechanicId.value.toString())
        put("status", t.status.name)
        put("lat", t.lat)
        put("lon", t.lon)
        put("h3_res8_index", t.h3Res8)
        put("h3_res7_index", t.h3Res7)
        t.skills.forEach { put("skills", kotlinx.serialization.json.JsonPrimitive(it)) }
    }.toString()

    fun offerCreated(offer: Offer, booking: Booking): String = buildJsonObject {
        envelope("dispatch.offer.created", offer.bookingId).forEach { (k, v) -> put(k, v) }
        put("offer_id", offer.id.value.toString())
        put("mechanic_id", offer.mechanicId.value.toString())
        put("h3_res8_index", offer.h3Res8)
        put("ring", offer.ring)
        put("eta_seconds", offer.etaSeconds)
        put("expires_at", offer.expiresAt.toString())
    }.toString()

    fun offerAccepted(bookingId: BookingId, offerId: OfferId, mechanicId: MechanicId): String =
        buildJsonObject {
            envelope("dispatch.offer.accepted", bookingId).forEach { (k, v) -> put(k, v) }
            put("offer_id", offerId.value.toString())
            put("mechanic_id", mechanicId.value.toString())
            put("accepted_at", Instant.now().toString())
        }.toString()

    fun offerRejected(bookingId: BookingId, offerId: OfferId, mechanicId: MechanicId, reason: String): String =
        buildJsonObject {
            envelope("dispatch.offer.rejected", bookingId).forEach { (k, v) -> put(k, v) }
            put("offer_id", offerId.value.toString())
            put("mechanic_id", mechanicId.value.toString())
            put("reason", reason)
            put("rejected_at", Instant.now().toString())
        }.toString()

    fun jobStatusChanged(bookingId: BookingId, from: JobStatus, to: JobStatus, mechanicId: MechanicId? = null): String =
        buildJsonObject {
            envelope("job.status.changed", bookingId).forEach { (k, v) -> put(k, v) }
            if (mechanicId != null) put("mechanic_id", mechanicId.value.toString())
            put("from_status", from.name)
            put("to_status", to.name)
            put("changed_at", Instant.now().toString())
        }.toString()

    fun escalated(bookingId: BookingId): String = jobStatusChanged(bookingId, JobStatus.SEARCHING, JobStatus.ESCALATED)
}
