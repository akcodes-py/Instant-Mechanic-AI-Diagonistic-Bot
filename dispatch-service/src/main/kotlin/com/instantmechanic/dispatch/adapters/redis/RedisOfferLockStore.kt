package com.instantmechanic.dispatch.adapters.redis

import com.instantmechanic.dispatch.domain.model.MechanicId
import com.instantmechanic.dispatch.domain.model.OfferId
import com.instantmechanic.dispatch.domain.port.OfferLockStore
import io.lettuce.core.RedisClient
import io.lettuce.core.ScriptOutputType
import io.lettuce.core.api.sync.RedisCommands

/** 15-second exclusive offer lock: SET NX EX + atomic compare-and-delete. */
class RedisOfferLockStore(client: RedisClient) : OfferLockStore {
    private val redis: RedisCommands<String, String> = client.connect().sync()

    override fun tryAcquire(mechanicId: MechanicId, offerId: OfferId, ttlSeconds: Int): Boolean =
        "OK" == redis.setexnx(lockKey(mechanicId), offerId.value.toString(), ttlSeconds.toLong())

    override fun release(mechanicId: MechanicId, offerId: OfferId): Boolean {
        val script = """
            if redis.call('get', KEYS[1]) == ARGV[1] then
                return redis.call('del', KEYS[1])
            else
                return 0
            end
        """.trimIndent()
        @Suppress("UNCHECKED_CAST")
        val result = redis.eval(
            script, ScriptOutputType.INTEGER,
            arrayOf(lockKey(mechanicId)), offerId.value.toString(),
        ) as Long
        return result == 1L
    }

    private fun lockKey(id: MechanicId) = "lock:mechanic:${id.value}"
}

private fun RedisCommands<String, String>.setexnx(key: String, value: String, seconds: Long): String? =
    this.set(key, value, io.lettuce.core.SetArgs.Builder.nx().ex(seconds))
