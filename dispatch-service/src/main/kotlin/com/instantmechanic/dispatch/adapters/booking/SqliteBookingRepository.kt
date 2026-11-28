package com.instantmechanic.dispatch.adapters.booking

import com.instantmechanic.dispatch.domain.model.Booking
import com.instantmechanic.dispatch.domain.model.BookingId
import com.instantmechanic.dispatch.domain.model.JobStatus
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.port.BookingRepository
import java.io.File
import java.sql.Connection
import java.sql.DriverManager

/**
 * Local stand-in for MS SQL (ADR-001). Keeps the exact same atomic conditional
 * update and partial unique index, so the production adapter is a drop-in.
 */
class SqliteBookingRepository(url: String = "jdbc:sqlite:data/dispatch.db") : BookingRepository {
    private val connection: Connection

    init {
        File("data").mkdirs()
        connection = DriverManager.getConnection(url)
        connection.createStatement().use { stmt ->
            stmt.execute(
                """
                CREATE TABLE IF NOT EXISTS bookings (
                  booking_id TEXT PRIMARY KEY,
                  session_id TEXT,
                  required_skill TEXT NOT NULL,
                  urgency TEXT NOT NULL,
                  h3_res8 TEXT NOT NULL,
                  h3_res7 TEXT NOT NULL,
                  lat REAL NOT NULL,
                  lon REAL NOT NULL,
                  status TEXT NOT NULL DEFAULT 'SEARCHING',
                  assigned_mechanic TEXT
                )
                """.trimIndent(),
            )
            stmt.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_active_mechanic
                ON bookings(assigned_mechanic)
                WHERE status IN ('ASSIGNED','EN_ROUTE','ARRIVED','IN_REPAIR')
                """.trimIndent(),
            )
        }
    }

    override fun findById(id: BookingId): Booking? = connection.prepareStatement(
        "SELECT * FROM bookings WHERE booking_id = ?",
    ).use { ps ->
        ps.setString(1, id.value.toString())
        ps.executeQuery().use { rs ->
            if (!rs.next()) return null
            Booking(
                id = BookingId(java.util.UUID.fromString(rs.getString("booking_id"))),
                requiredSkill = rs.getString("required_skill"),
                urgency = rs.getString("urgency"),
                h3Res8 = rs.getString("h3_res8"),
                h3Res7 = rs.getString("h3_res7"),
                lat = rs.getDouble("lat"),
                lon = rs.getDouble("lon"),
                status = JobStatus.valueOf(rs.getString("status")),
                assignedMechanic = rs.getString("assigned_mechanic")?.let {
                    MechanicId(java.util.UUID.fromString(it))
                },
            )
        }
    }

    override fun save(booking: Booking) = connection.prepareStatement(
        """
        INSERT INTO bookings (booking_id, required_skill, urgency, h3_res8, h3_res7, lat, lon, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(booking_id) DO NOTHING
        """.trimIndent(),
    ).use { ps ->
        ps.setString(1, booking.id.value.toString())
        ps.setString(2, booking.requiredSkill)
        ps.setString(3, booking.urgency)
        ps.setString(4, booking.h3Res8)
        ps.setString(5, booking.h3Res7)
        ps.setDouble(6, booking.lat)
        ps.setDouble(7, booking.lon)
        ps.setString(8, booking.status.name)
        ps.executeUpdate()
        Unit
    }

    override fun tryAssign(id: BookingId, mechanicId: MechanicId): Boolean =
        connection.prepareStatement(
            """
            UPDATE bookings SET status='ASSIGNED', assigned_mechanic=?
            WHERE booking_id=? AND status IN ('SEARCHING','OFFERED')
            """.trimIndent(),
        ).use { ps ->
            ps.setString(1, mechanicId.value.toString())
            ps.setString(2, id.value.toString())
            ps.executeUpdate() == 1
        }

    override fun updateStatus(id: BookingId, from: JobStatus, to: JobStatus): Boolean =
        connection.prepareStatement(
            "UPDATE bookings SET status=? WHERE booking_id=? AND status=?",
        ).use { ps ->
            ps.setString(1, to.name)
            ps.setString(2, id.value.toString())
            ps.setString(3, from.name)
            ps.executeUpdate() == 1
        }
}
