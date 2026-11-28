package com.instantmechanic.dispatch.domain.port

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.Candidate
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.PositionedTelemetry
import com.instantmechanic.dispatch.domain.model.RankedMechanic

/** Ports (interfaces) the core use cases depend on. Adapters live elsewhere. */

interface SpatialIndex {
    fun cell(lat: Double, lon: Double, resolution: Int): String
    fun parent(cell: String, resolution: Int): String
    /** Full disk: k=1 -> 7 cells, k=2 -> 19, k=3 -> 37. */
    fun ring(cell: String, k: Int): Set<String>
}

interface PresenceStore {
    /** Upsert a live presence row (Redis/Cassandra) with a TTL in seconds. */
    fun upsert(telemetry: PositionedTelemetry, ttlSeconds: Long)
    /** Online mechanics inside any of the given cells that have the skill. */
    fun onlineMechanics(cells: Collection<String>, skill: String): List<Candidate>
    fun markOffline(mechanicId: MechanicId)
}

interface OfferLockStore {
    /** Redis SET NX EX. Returns true only for the winner. */
    fun tryAcquire(mechanicId: MechanicId, offerId: OfferId, ttlSeconds: Int): Boolean
    /** Compare-and-delete: only the owner may release. */
    fun release(mechanicId: MechanicId, offerId: OfferId): Boolean
}

interface BookingRepository {
    fun findById(id: BookingId): Booking?
    fun save(booking: Booking)
    /** Atomic UPDATE ... WHERE status='SEARCHING'. True only for the winner. */
    fun tryAssign(id: BookingId, mechanicId: MechanicId): Boolean
    fun updateStatus(id: BookingId, from: com.instantmechanic.dispatch.domain.model.JobStatus,
                     to: com.instantmechanic.dispatch.domain.model.JobStatus): Boolean
}

interface RankingStrategy {
    fun rank(booking: Booking, candidates: List<Candidate>): List<RankedMechanic>
}

interface EventPublisher {
    /** key is the Kafka partition key (Res-7 zone); payload is a JSON envelope. */
    fun publish(topic: String, key: String, payload: String)
}
