package com.instantmechanic.dispatch.adapters.http

import com.instantmechanic.dispatch.domain.port.EventPublisher
import io.ktor.server.websocket.WebSocketServerSession
import io.ktor.websocket.send
import java.util.concurrent.ConcurrentHashMap
import kotlinx.coroutines.runBlocking

/** WebSocket fan-out by booking_id (the Res-7 zone is used for Kafka keys). */
class WebSocketHub {
    private val sockets = ConcurrentHashMap<String, MutableSet<WebSocketServerSession>>()

    fun register(key: String, session: WebSocketServerSession) {
        sockets.computeIfAbsent(key) { ConcurrentHashMap.newKeySet() }.add(session)
    }

    fun unregister(key: String, session: WebSocketServerSession) {
        sockets[key]?.remove(session)
    }

    fun broadcast(key: String, payload: String) {
        runBlocking {
            sockets[key]?.forEach { session ->
                try {
                    session.send(payload)
                } catch (_: Exception) {
                    // A dead socket never fails a dispatch.
                }
            }
        }
    }
}

class HubPublisher(private val hub: WebSocketHub) : EventPublisher {
    override fun publish(topic: String, key: String, payload: String) = hub.broadcast(key, payload)
}

class FanoutPublisher(private val publishers: List<EventPublisher>) : EventPublisher {
    override fun publish(topic: String, key: String, payload: String) =
        publishers.forEach { it.publish(topic, key, payload) }
}
