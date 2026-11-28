package com.instantmechanic.dispatch.domain

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.model.RejectionReason
import com.instantmechanic.dispatch.domain.usecase.DispatchResult
import com.instantmechanic.dispatch.domain.usecase.OfferCascade
import com.instantmechanic.dispatch.support.FakeBookingRepository
import com.instantmechanic.dispatch.support.FakeLockStore
import com.instantmechanic.dispatch.support.FakePresenceStore
import com.instantmechanic.dispatch.support.FakeRanking
import com.instantmechanic.dispatch.support.FakeSpatialIndex
import com.instantmechanic.dispatch.support.RecordingPublisher
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import java.util.UUID

class OfferCascadeTest {
    private lateinit var spatial: FakeSpatialIndex
    private lateinit var presence: FakePresenceStore
    private lateinit var locks: FakeLockStore
    private lateinit var bookings: FakeBookingRepository
    private lateinit var publisher: RecordingPublisher
    private lateinit var cascade: OfferCascade
    private val origin = "cell-8-28.4-77.0"

    @BeforeEach fun setUp() {
        spatial = FakeSpatialIndex()
        presence = FakePresenceStore()
        locks = FakeLockStore()
        bookings = FakeBookingRepository()
        publisher = RecordingPublisher()
        cascade = OfferCascade(spatial, presence, locks, bookings, FakeRanking(), publisher)
    }

    private fun newBooking(skill: String = "battery_jumpstart"): BookingId {
        val id = BookingId(UUID.randomUUID())
        bookings.save(Booking(id, skill, "high", origin, "cell-7-28.4-77.0", 28.4, 77.0))
        return id
    }

    private fun mechanic() = MechanicId(UUID.randomUUID())

    @Test fun `offers the nearest matching mechanic in ring one`() {
        val bookingId = newBooking()
        val mechanic = mechanic()
        presence.add(mechanic, "$origin#0", setOf("battery_jumpstart"))

        val result = cascade.dispatch(bookingId) as DispatchResult.Offered

        assertEquals(mechanic, result.offer.mechanicId)
        assertEquals(1, result.offer.ring)
        assertEquals(60, result.offer.etaSeconds)
        assertTrue(locks.isHeld(mechanic))
        assertTrue(publisher.topics().contains("dispatch.offer.created"))
        assertEquals(JobStatus.OFFERED, bookings.findById(bookingId)?.status)
    }

    @Test fun `ignores mechanics without the required skill`() {
        val bookingId = newBooking("towing")
        presence.add(mechanic(), "$origin#0", setOf("battery_jumpstart"))

        assertEquals(DispatchResult.Escalated, cascade.dispatch(bookingId))
    }

    @Test fun `skips a mechanic whose lock is held and offers the next one`() {
        val bookingId = newBooking()
        val busy = mechanic()
        val free = mechanic()
        presence.add(busy, "$origin#0", setOf("battery_jumpstart"))
        presence.add(free, "$origin#1", setOf("battery_jumpstart"))
        locks.tryAcquire(busy, OfferId(UUID.randomUUID()), 15)

        val result = cascade.dispatch(bookingId) as DispatchResult.Offered

        assertEquals(free, result.offer.mechanicId)
    }

    @Test fun `expands to ring three before escalating`() {
        val bookingId = newBooking()
        val far = mechanic()
        presence.add(far, "$origin#20", setOf("battery_jumpstart")) // only in ring 3

        val result = cascade.dispatch(bookingId) as DispatchResult.Offered

        assertEquals(3, result.offer.ring)
        assertEquals(far, result.offer.mechanicId)
    }

    @Test fun `escalates to the hotline path after three empty rings`() {
        val bookingId = newBooking()

        assertEquals(DispatchResult.Escalated, cascade.dispatch(bookingId))
        assertEquals(JobStatus.ESCALATED, bookings.findById(bookingId)?.status)
        val payload = publisher.events.last { it.topic == "job.status.changed" }.payload
        assertTrue(payload.contains("ESCALATED"))
    }

    @Test fun `no double dispatch - a second accept loses and releases its lock`() {
        val bookingId = newBooking()
        val winner = mechanic()
        val loser = mechanic()
        presence.add(winner, "$origin#0", setOf("battery_jumpstart"))
        val offer = (cascade.dispatch(bookingId) as DispatchResult.Offered).offer

        val first = cascade.accept(bookingId, offer.id, winner)
        val second = cascade.accept(bookingId, OfferId(UUID.randomUUID()), loser)

        assertTrue(first is DispatchResult.Assigned)
        assertTrue(second is DispatchResult.AlreadyHandled)
        assertEquals(winner, bookings.findById(bookingId)?.assignedMechanic)
        assertTrue(!locks.isHeld(winner))
    }

    @Test fun `reject releases the lock and returns the booking to searching`() {
        val bookingId = newBooking()
        val mechanic = mechanic()
        presence.add(mechanic, "$origin#0", setOf("battery_jumpstart"))
        val offer = (cascade.dispatch(bookingId) as DispatchResult.Offered).offer

        cascade.reject(bookingId, offer.id, mechanic, RejectionReason.DECLINED)

        assertTrue(!locks.isHeld(mechanic))
        assertEquals(JobStatus.SEARCHING, bookings.findById(bookingId)?.status)
        assertTrue(publisher.topics().contains("dispatch.offer.rejected"))
    }

    @Test fun `advance enforces the job state machine`() {
        val bookingId = newBooking()
        val mechanic = mechanic()
        presence.add(mechanic, "$origin#0", setOf("battery_jumpstart"))
        val offer = (cascade.dispatch(bookingId) as DispatchResult.Offered).offer
        cascade.accept(bookingId, offer.id, mechanic)

        // Already ASSIGNED, so jumping straight to COMPLETED is illegal.
        org.junit.jupiter.api.assertThrows<IllegalArgumentException> {
            cascade.advance(bookingId, JobStatus.COMPLETED)
        }
    }
}
