"""Best-effort Kafka producer for diagnosis.completed (ADR-001).

No external service is required: if Redpanda is unreachable the function returns
False and the diagnosis response is unchanged. Failures are logged by type only.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.services.spatial import lat_lng_to_cell, zone_cell

logger = logging.getLogger(__name__)

_PRODUCER = None
_INITIALIZED = False

# Gurugram simulator centre from contracts/h3.md. The prototype has no GPS
# field; production supplies real coordinates via the booking flow.
DEMO_LAT = 28.4595
DEMO_LON = 77.0266

SKILL_BY_SERVICE = {
    "battery_jumpstart": "battery_jumpstart",
    "tyre_puncture": "tyre_puncture",
    "engine_overheat": "engine_overheat",
    "towing": "towing",
    "brakes": "brakes",
    "fuel": "fuel",
    "key_lockout": "key_lockout",
}


def _get_producer():
    global _PRODUCER, _INITIALIZED
    if _INITIALIZED:
        return _PRODUCER
    _INITIALIZED = True
    try:
        from kafka import KafkaProducer

        _PRODUCER = KafkaProducer(
            bootstrap_servers=[b.strip() for b in settings.REDPANDA_BROKERS.split(",") if b.strip()],
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8"),
            retries=2,
        )
    except Exception:
        logger.warning("Kafka producer unavailable: %s", type(Exception).__name__)
        _PRODUCER = None
    return _PRODUCER


def publish_diagnosis_completed(
    *,
    session_id: str,
    diagnosis_id: str,
    recommended_service: str,
    urgency: str,
    summary: str,
    lat: float = DEMO_LAT,
    lon: float = DEMO_LON,
    photo_url: str | None = None,
    detections: list[dict] | None = None,
) -> bool:
    """Publish a contract-shaped event. Returns True only on a real send."""
    producer = _get_producer()
    if producer is None:
        return False
    try:
        res8 = lat_lng_to_cell(lat, lon, 8)
        zone = zone_cell(res8)
        payload = {
            "event_id": str(uuid.uuid4()),
            "event_type": "diagnosis.completed",
            "schema_version": 1,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "producer": "ai-service",
            "booking_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"diagnosis:{diagnosis_id}")),
            "session_id": session_id,
            "required_skill": SKILL_BY_SERVICE.get(recommended_service, "general_repair"),
            "urgency": urgency,
            "summary": summary[:1000],
            "recommended_service": recommended_service,
            "photo_url": photo_url,
            "detections": detections or [],
            "lat": lat,
            "lon": lon,
            "h3_res7_index": zone,
            "ai_used": False,
        }
        producer.send("diagnosis.completed", key=zone, value=payload)
        return True
    except Exception:
        logger.warning("diagnosis.completed publish failed: %s", type(Exception).__name__)
        return False
