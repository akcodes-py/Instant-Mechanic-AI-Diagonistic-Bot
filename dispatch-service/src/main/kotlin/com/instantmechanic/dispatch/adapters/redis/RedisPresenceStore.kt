package com.instantmechanic.dispatch.adapters.redis

import com.instantmechanic.dispatch.domain.model.Candidate
import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.PositionedTelemetry
import com.instantmechanic.dispatch.domain.port.PresenceStore
import io.lettuce.core.RedisClient
import io.lettuce.core.api.sync.RedisCommands
import kotlinx.serialization.json.Json

/**
 * Local stand-in for Cassandra presence (same port, see ADR-001). Hot supply
 * sets expire after 60s, so a mechanic who stops pinging disappears automatically.
 */
class RedisPresenceStore(client: RedisClient) : PresenceStore {
    private val redis: RedisCommands<String, String> = client.connect().sync()
    private val json = Json { ignoreUnknownKeys = true }

    @kotlinx.serialization.Serializable
    private data class Stored(val lat: Double, val lon: Double, val h3: String)

    override fun upsert(telemetry: PositionedTelemetry, ttlSeconds: Long) {
        val id = telemetry.mechanicId.value.toString()
        val payload = json.encodeToString(Stored(telemetry.lat, telemetry.lon, telemetry.h3Res8))
        telemetry.skills.forEach { skill ->
            val supply = "supply:${telemetry.h3Res8}:$skill"
            redis.sadd(supply, id)
            redis.expire(supply, ttlSeconds)
            redis.sadd("index:$id", "$supply")
            redis.expire("index:$id", ttlSeconds)
        }
        redis.set("presence:${telemetry.h3Res8}:$id", payload,
            io.lettuce.core.SetArgs.Builder.ex(ttlSeconds))
    }

    override fun onlineMechanics(cells: Collection<String>, skill: String): List<Candidate> {
        val result = mutableListOf<Candidate>()
        cells.forEach { cell ->
            redis.smembers("supply:$cell:$skill").forEach { id ->
                val raw = redis.get("presence:$cell:$id") ?: return@forEach
                try {
                    val stored = json.decodeFromString<Stored>(raw)
                    result += Candidate(MechanicId(java.util.UUID.fromString(id)), stored.h3, stored.lat, stored.lon)
                } catch (_: Exception) {
                    // Malformed presence is ignored; never fail a dispatch on bad cache data.
                }
            }
        }
        return result.distinctBy { it.mechanicId }
    }

    override fun markOffline(mechanicId: MechanicId) {
        val id = mechanicId.value.toString()
        redis.smembers("index:$id").forEach { supply ->
            redis.srem(supply, id)
            val cell = supply.removePrefix("supply:").substringBefore(":")
            redis.del("presence:$cell:$id")
        }
        redis.del("index:$id")
    }
}
