package com.instantmechanic.dispatch.adapters.kafka

import com.instantmechanic.dispatch.domain.port.EventPublisher
import org.apache.kafka.clients.producer.KafkaProducer
import org.apache.kafka.clients.producer.ProducerRecord
import org.apache.kafka.common.serialization.StringSerializer
import java.util.Properties

/** Redpanda/Kafka producer. No secrets; broker list comes from configuration. */
class KafkaEventPublisher(brokers: String) : EventPublisher {
    private val producer: KafkaProducer<String, String> = KafkaProducer(
        Properties().apply {
            put("bootstrap.servers", brokers)
            put("key.serializer", StringSerializer::class.java.name)
            put("value.serializer", StringSerializer::class.java.name)
            put("acks", "1")
            put("retries", "2")
            put("linger.ms", "5")
        },
    )

    override fun publish(topic: String, key: String, payload: String) {
        producer.send(ProducerRecord(topic, key, payload))
    }
}
