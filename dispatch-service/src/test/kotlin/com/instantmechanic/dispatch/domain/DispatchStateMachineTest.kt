package com.instantmechanic.dispatch.domain

import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.usecase.DispatchStateMachine
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows

class DispatchStateMachineTest {
    private val machine = DispatchStateMachine()

    @Test fun `allows the happy path from searching to completed`() {
        val transitions = listOf(
            JobStatus.SEARCHING to JobStatus.OFFERED,
            JobStatus.OFFERED to JobStatus.ASSIGNED,
            JobStatus.ASSIGNED to JobStatus.EN_ROUTE,
            JobStatus.EN_ROUTE to JobStatus.ARRIVED,
            JobStatus.ARRIVED to JobStatus.IN_REPAIR,
            JobStatus.IN_REPAIR to JobStatus.COMPLETED,
        )
        transitions.forEach { (from, to) -> assertTrue(machine.canTransition(from, to), "$from -> $to") }
    }

    @Test fun `allows escalation and release back to searching`() {
        assertTrue(machine.canTransition(JobStatus.SEARCHING, JobStatus.ESCALATED))
        assertTrue(machine.canTransition(JobStatus.OFFERED, JobStatus.SEARCHING))
        assertTrue(machine.canTransition(JobStatus.ASSIGNED, JobStatus.SEARCHING))
    }

    @Test fun `rejects skipping steps and leaving terminal states`() {
        assertFalse(machine.canTransition(JobStatus.SEARCHING, JobStatus.COMPLETED))
        assertFalse(machine.canTransition(JobStatus.EN_ROUTE, JobStatus.IN_REPAIR))
        assertFalse(machine.canTransition(JobStatus.COMPLETED, JobStatus.EN_ROUTE))
        assertFalse(machine.canTransition(JobStatus.ESCALATED, JobStatus.SEARCHING))
    }

    @Test fun `requireTransition throws with a useful message`() {
        val error = assertThrows<IllegalArgumentException> {
            machine.requireTransition(JobStatus.COMPLETED, JobStatus.SEARCHING)
        }
        assertTrue(error.message!!.contains("COMPLETED"))
    }
}
