package com.instantmechanic.dispatch.domain.usecase

import com.instantmechanic.dispatch.domain.events.Events
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.Offer
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.RejectionReason
import com.instantmechanic.dispatch.domain.port.BookingRepository
import com.instantmechanic.dispatch.domain.port.EventPublisher
import com.instantmechanic.dispatch.domain.port.OfferLockStore
import com.instantmechanic.dispatch.domain.port.PresenceStore
import com.instantmechanic.dispatch.domain.port.RankingStrategy
import com.instantmechanic.dispatch.domain.port.SpatialIndex
import java.time.Instant
import java.util.UUID

/** Outcome of a dispatch attempt. */
sealed interface DispatchResult {
    data class Offered(val offer: Offer) : DispatchResult
    data class Assigned(val mechanicId: MechanicId, val offerId: OfferId) : DispatchResult
    data object Escalated : DispatchResult
    data object NotFound : DispatchResult
    data object AlreadyHandled : DispatchResult
}

/**
 * OCP: ranking is injected via the RankingStrategy port; this orchestrator never
 * changes when the strategy is swapped (nearest vs ML ETA).
 *
 * Zero double-dispatch is enforced twice: a 15s exclusive Redis lock per mechanic
 * and an atomic conditional booking update (`WHERE status='SEARCHING'`).
 */
class OfferCascade(
    private val spatial: SpatialIndex,
    private val presence: PresenceStore,
    private val locks: OfferLockStore,
    private val bookings: BookingRepository,
    private val ranking: RankingStrategy,
    private val publisher: EventPublisher,
    private val stateMachine: DispatchStateMachine = DispatchStateMachine(),
    private val offerTtlSeconds: Int = 15,
    private val maxRing: Int = 3,
) {
    fun dispatch(bookingId: BookingId): DispatchResult {
        val booking = bookings.findById(bookingId) ?: return DispatchResult.NotFound
        if (booking.status != JobStatus.SEARCHING) return DispatchResult.AlreadyHandled

        val seen = mutableSetOf<MechanicId>()
        for (ring in 1..maxRing) {
            val cells = spatial.ring(booking.h3Res8, ring)
            if (cells.isEmpty()) continue

            val candidates = presence.onlineMechanics(cells, booking.requiredSkill)
                .filterNot { seen.contains(it.mechanicId) }
            seen.addAll(candidates.map { it.mechanicId })
            if (candidates.isEmpty()) continue

            for (ranked in ranking.rank(booking, candidates)) {
                // Re-check authority before offering: another accept may have won.
                if (bookings.findById(bookingId)?.status != JobStatus.SEARCHING) {
                    return DispatchResult.AlreadyHandled
                }
                val offerId = OfferId(UUID.randomUUID())
                if (!locks.tryAcquire(ranked.mechanicId, offerId, offerTtlSeconds)) continue

                stateMachine.requireTransition(JobStatus.SEARCHING, JobStatus.OFFERED)
                bookings.updateStatus(bookingId, JobStatus.SEARCHING, JobStatus.OFFERED)
                val offer = Offer(
                    id = offerId,
                    bookingId = bookingId,
                    mechanicId = ranked.mechanicId,
                    h3Res8 = booking.h3Res8,
                    ring = ring,
                    etaSeconds = ranked.etaSeconds,
                    expiresAt = Instant.now().plusSeconds(offerTtlSeconds.toLong()),
                )
                publisher.publish(
                    "dispatch.offer.created", booking.h3Res7,
                    Events.offerCreated(offer, booking),
                )
                return DispatchResult.Offered(offer)
            }
        }

        stateMachine.requireTransition(JobStatus.SEARCHING, JobStatus.ESCALATED)
        bookings.updateStatus(bookingId, JobStatus.SEARCHING, JobStatus.ESCALATED)
        publisher.publish("job.status.changed", booking.h3Res7, Events.escalated(bookingId))
        return DispatchResult.Escalated
    }

    fun accept(bookingId: BookingId, offerId: OfferId, mechanicId: MechanicId): DispatchResult {
        // The conditional update is the authoritative guard; the lock is best-effort.
        if (!bookings.tryAssign(bookingId, mechanicId)) {
            locks.release(mechanicId, offerId)
            return DispatchResult.AlreadyHandled
        }
        locks.release(mechanicId, offerId)
        publisher.publish(
            "dispatch.offer.accepted", bookings.findById(bookingId)?.h3Res7 ?: "",
            Events.offerAccepted(bookingId, offerId, mechanicId),
        )
        return DispatchResult.Assigned(mechanicId, offerId)
    }

    fun reject(bookingId: BookingId, offerId: OfferId, mechanicId: MechanicId, reason: RejectionReason) {
        locks.release(mechanicId, offerId)
        bookings.updateStatus(bookingId, JobStatus.OFFERED, JobStatus.SEARCHING)
        val key = bookings.findById(bookingId)?.h3Res7 ?: ""
        publisher.publish(
            "dispatch.offer.rejected", key,
            Events.offerRejected(bookingId, offerId, mechanicId, reason.name.lowercase()),
        )
    }

    /** EN_ROUTE -> ARRIVED -> IN_REPAIR -> COMPLETED, validated by the state machine. */
    fun advance(bookingId: BookingId, to: JobStatus): Boolean {
        val booking = bookings.findById(bookingId) ?: return false
        stateMachine.requireTransition(booking.status, to)
        if (!bookings.updateStatus(bookingId, booking.status, to)) return false
        publisher.publish("job.status.changed", booking.h3Res7, Events.jobStatusChanged(bookingId, booking.status, to))
        return true
    }
}
