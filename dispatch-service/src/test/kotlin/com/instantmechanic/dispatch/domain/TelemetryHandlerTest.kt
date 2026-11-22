package com.instantmechanic.dispatch.domain

import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.MechanicStatus
import com.instantmechanic.dispatch.domain.model.Telemetry
import com.instantmechanic.dispatch.domain.usecase.TelemetryHandler
import com.instantmechanic.dispatch.support.FakePresenceStore
import com.instantmechanic.dispatch.support.FakeSpatialIndex
import com.instantmechanic.dispatch.support.RecordingPublisher
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test
import java.util.UUID

class TelemetryHandlerTest {
    private val spatial = FakeSpatialIndex()
    private val presence = FakePresenceStore()
    private val publisher = RecordingPublisher()
    private val handler = TelemetryHandler(spatial, presence, publisher)

    private fun telemetry(status: MechanicStatus, lat: Double = 28.4, lon: Double = 77.0) = Telemetry(
        mechanicId = MechanicId(UUID.randomUUID()),
        status = status,
        lat = lat, lon = lon,
        skills = setOf("battery_jumpstart"),
    )

    @Test fun `online ping is indexed at res 8 and res 7 and published`() {
        val result = handler.handle(telemetry(MechanicStatus.ONLINE))

        assertNotNull(result)
        assertEquals("cell-8-28.4-77.0", result!!.h3Res8)
        assertEquals("cell-7-28.4-77.0", result.h3Res7)
        assertEquals("mechanic.telemetry.updated", publisher.events.single().topic)
        assertEquals(result.h3Res7, publisher.events.single().key)
        assertEquals(1, presence.onlineMechanics(listOf(result.h3Res8), "battery_jumpstart").size)
    }

    @Test fun `on job mechanics stay in supply`() {
        val result = handler.handle(telemetry(MechanicStatus.ON_JOB))
        assertNotNull(result)
    }

    @Test fun `offline ping removes presence and publishes nothing`() {
        val t = telemetry(MechanicStatus.OFFLINE)

        assertNull(handler.handle(t))
        assertTrue(publisher.events.isEmpty())
    }

    @Test fun `out of range coordinates are rejected without side effects`() {
        assertNull(handler.handle(telemetry(MechanicStatus.ONLINE, lat = 91.0)))
        assertNull(handler.handle(telemetry(MechanicStatus.ONLINE, lon = -181.0)))
        assertTrue(publisher.events.isEmpty())
    }

    private fun assertTrue(value: Boolean) = org.junit.jupiter.api.Assertions.assertTrue(value)
}
