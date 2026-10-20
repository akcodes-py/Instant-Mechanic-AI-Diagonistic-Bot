"""Shared enums used by the ORM models and Pydantic schemas."""

SERVICE_TYPES = (
    "battery_jumpstart",
    "flat_tyre",
    "towing",
    "fuel_delivery",
    "key_lockout",
    "general_repair",
    "inspection",
)

URGENCY_LEVELS = ("low", "medium", "high", "critical")
BOOKING_STATUSES = ("pending", "confirmed", "completed", "cancelled")
