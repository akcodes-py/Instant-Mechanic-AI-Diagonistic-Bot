package com.instantmechanic.dispatch.support

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.Candidate
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.PositionedTelemetry
import com.instantmechanic.dispatch.domain.model.RankedMechanic
import com.instantmechanic.dispatch.domain.port.BookingRepository
import com.instantmechanic.dispatch.domain.port.EventPublisher
import com.instantmechanic.dispatch.domain.port.OfferLockStore
import com.instantmechanic.dispatch.domain.port.PresenceStore
import com.instantmechanic.dispatch.domain.port.RankingStrategy
import com.instantmechanic.dispatch.domain.port.SpatialIndex

/** Deterministic in-memory ports: no Redis, Kafka, SQLite or H3 native lib needed. */
class FakeSpatialIndex : SpatialIndex {
    override fun cell(lat: Double, lon: Double, resolution: Int): String = "cell-$resolution-$lat-$lon"
    override fun parent(cell: String, resolution: Int): String = cell.replace("cell-8-", "cell-$resolution-")
    override fun ring(cell: String, k: Int): Set<String> {
        val size = when (k) { 1 -> 7; 2 -> 19; 3 -> 37; else -> 0 }
        return (0 until size).map { "$cell#$it" }.toSet()
    }
}

class FakePresenceStore : PresenceStore {
    private data class Stored(val candidate: Candidate, val skills: Set<String>)
    private val rows = mutableListOf<Stored>()

    fun add(mechanicId: MechanicId, cell: String, skills: Set<String>, lat: Double = 28.4, lon: Double = 77.0) {
        rows += Stored(Candidate(mechanicId, cell, lat, lon), skills)
    }

    override fun upsert(telemetry: PositionedTelemetry, ttlSeconds: Long) {
        add(telemetry.mechanicId, telemetry.h3Res8, telemetry.skills, telemetry.lat, telemetry.lon)
    }

    override fun onlineMechanics(cells: Collection<String>, skill: String): List<Candidate> =
        rows.filter { it.candidate.h3Res8 in cells && skill in it.skills }.map { it.candidate }

    override fun markOffline(mechanicId: MechanicId) { rows.removeAll { it.candidate.mechanicId == mechanicId } }
}

class FakeLockStore : OfferLockStore {
    private val held = mutableSetOf<MechanicId>()
    override fun tryAcquire(mechanicId: MechanicId, offerId: OfferId, ttlSeconds: Int): Boolean = held.add(mechanicId)
    override fun release(mechanicId: MechanicId, offerId: OfferId): Boolean = held.remove(mechanicId)
    fun isHeld(id: MechanicId) = id in held
}

class FakeBookingRepository : BookingRepository {
    private val rows = mutableMapOf<BookingId, Booking>()
    override fun findById(id: BookingId): Booking? = rows[id]
    override fun save(booking: Booking) { rows.putIfAbsent(booking.id, booking) }
    override fun tryAssign(id: BookingId, mechanicId: MechanicId): Boolean {
        val booking = rows[id] ?: return false
        if (booking.status != JobStatus.SEARCHING && booking.status != JobStatus.OFFERED) return false
        rows[id] = booking.copy(status = JobStatus.ASSIGNED, assignedMechanic = mechanicId)
        return true
    }
    override fun updateStatus(id: BookingId, from: JobStatus, to: JobStatus): Boolean {
        val booking = rows[id] ?: return false
        if (booking.status != from) return false
        rows[id] = booking.copy(status = to)
        return true
    }
}

class FakeRanking : RankingStrategy {
    override fun rank(booking: Booking, candidates: List<Candidate>): List<RankedMechanic> =
        candidates.mapIndexed { index, c -> RankedMechanic(c.mechanicId, 60 + index * 10, 1.0 - index * 0.1) }
}

class RecordingPublisher : EventPublisher {
    data class Event(val topic: String, val key: String, val payload: String)
    val events = mutableListOf<Event>()
    override fun publish(topic: String, key: String, payload: String) { events += Event(topic, key, payload) }
    fun topics() = events.map { it.topic }
}
