package com.instantmechanic.dispatch.domain.usecase

import com.instantmechanic.dispatch.domain.events.Events
import com.instantmechanic.dispatch.domain.model.MechanicStatus
import com.instantmechanic.dispatch.domain.model.PositionedTelemetry
import com.instantmechanic.dispatch.domain.model.Telemetry
import com.instantmechanic.dispatch.domain.port.EventPublisher
import com.instantmechanic.dispatch.domain.port.PresenceStore
import com.instantmechanic.dispatch.domain.port.SpatialIndex

/**
 * SRP: ingests one GPS/status ping. Computes H3 Res-8/7 indices, writes live
 * presence with a TTL and publishes the telemetry event. OFFLINE pings remove
 * presence, which prevents "ghost" mechanics in the supply sets.
 */
class TelemetryHandler(
    private val spatial: SpatialIndex,
    private val presence: PresenceStore,
    private val publisher: EventPublisher,
    private val presenceTtlSeconds: Long = 60,
) {
    fun handle(telemetry: Telemetry): PositionedTelemetry? {
        if (telemetry.lat !in -90.0..90.0 || telemetry.lon !in -180.0..180.0) return null

        if (telemetry.status == MechanicStatus.OFFLINE) {
            presence.markOffline(telemetry.mechanicId)
            return null
        }

        val res8 = spatial.cell(telemetry.lat, telemetry.lon, 8)
        val res7 = spatial.parent(res8, 7)
        val positioned = PositionedTelemetry(
            mechanicId = telemetry.mechanicId,
            status = telemetry.status,
            lat = telemetry.lat,
            lon = telemetry.lon,
            h3Res8 = res8,
            h3Res7 = res7,
            skills = telemetry.skills,
            speedKmh = telemetry.speedKmh,
            heading = telemetry.heading,
            timestamp = telemetry.timestamp,
        )
        presence.upsert(positioned, presenceTtlSeconds)
        publisher.publish("mechanic.telemetry.updated", res7, Events.telemetryUpdated(positioned))
        return positioned
    }
}
