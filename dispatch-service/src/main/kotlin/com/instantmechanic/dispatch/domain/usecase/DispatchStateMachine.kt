package com.instantmechanic.dispatch.domain.usecase

import com.instantmechanic.dispatch.domain.model.JobStatus

/**
 * SRP: only enforces valid job transitions. No framework, DB or broker imports.
 * ASSIGNED -> SEARCHING exists to release a job if the acceptance transaction is lost.
 */
class DispatchStateMachine {
    private val allowed: Map<JobStatus, Set<JobStatus>> = mapOf(
        JobStatus.SEARCHING to setOf(JobStatus.OFFERED, JobStatus.ESCALATED),
        JobStatus.OFFERED to setOf(JobStatus.ASSIGNED, JobStatus.SEARCHING),
        JobStatus.ASSIGNED to setOf(JobStatus.EN_ROUTE, JobStatus.SEARCHING),
        JobStatus.EN_ROUTE to setOf(JobStatus.ARRIVED),
        JobStatus.ARRIVED to setOf(JobStatus.IN_REPAIR),
        JobStatus.IN_REPAIR to setOf(JobStatus.COMPLETED),
        JobStatus.COMPLETED to emptySet(),
        JobStatus.ESCALATED to emptySet(),
    )

    fun canTransition(from: JobStatus, to: JobStatus): Boolean = to in allowed.getOrDefault(from, emptySet())

    fun requireTransition(from: JobStatus, to: JobStatus) {
        require(canTransition(from, to)) { "Illegal job transition: $from -> $to" }
    }

    fun allowedTargets(from: JobStatus): Set<JobStatus> = allowed[from] ?: emptySet()
}
