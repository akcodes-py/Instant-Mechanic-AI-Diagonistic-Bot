package com.instantmechanic.dispatch.domain.model

import java.time.Instant
import java.util.UUID

/** Core domain types. No framework, database or broker imports in this package. */

@JvmInline value class MechanicId(val value: UUID)
@JvmInline value class BookingId(val value: UUID)
@JvmInline value class OfferId(val value: UUID)

enum class MechanicStatus { ONLINE, OFFLINE, ON_JOB }

enum class JobStatus {
    SEARCHING, OFFERED, ASSIGNED, EN_ROUTE, ARRIVED, IN_REPAIR, COMPLETED, ESCALATED
}

data class Telemetry(
    val mechanicId: MechanicId,
    val status: MechanicStatus,
    val lat: Double,
    val lon: Double,
    val skills: Set<String>,
    val speedKmh: Double = 0.0,
    val heading: Double = 0.0,
    val timestamp: Instant = Instant.now(),
)

data class PositionedTelemetry(
    val mechanicId: MechanicId,
    val status: MechanicStatus,
    val lat: Double,
    val lon: Double,
    val h3Res8: String,
    val h3Res7: String,
    val skills: Set<String>,
    val speedKmh: Double = 0.0,
    val heading: Double = 0.0,
    val timestamp: Instant = Instant.now(),
)

data class Booking(
    val id: BookingId,
    val requiredSkill: String,
    val urgency: String,
    val h3Res8: String,
    val h3Res7: String,
    val lat: Double,
    val lon: Double,
    val status: JobStatus = JobStatus.SEARCHING,
    val assignedMechanic: MechanicId? = null,
    val customerPhone: String = "",
)

/** Nearby supply: identity + position, as returned by the presence store. */
data class Candidate(
    val mechanicId: MechanicId,
    val h3Res8: String,
    val lat: Double,
    val lon: Double,
)

data class RankedMechanic(
    val mechanicId: MechanicId,
    val etaSeconds: Int,
    val score: Double,
)

data class Offer(
    val id: OfferId,
    val bookingId: BookingId,
    val mechanicId: MechanicId,
    val h3Res8: String,
    val ring: Int,
    val etaSeconds: Int,
    val expiresAt: Instant,
)

enum class RejectionReason { DECLINED, TIMEOUT, LOCK_LOST, CANCELLED }

const val EMERGENCY_HOTLINE = "+916392077642"
