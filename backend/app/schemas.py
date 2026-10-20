"""Pydantic request models and JSON serializers for the API."""
import re
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.constants import SERVICE_TYPES


class ChatRequest(BaseModel):
    message: str | None = ""
    session_id: str | None = None
    vehicle_make: str | None = None
    vehicle_model: str | None = None
    vehicle_year: str | None = None
    vehicle_fuel: str | None = None
    website: str | None = None


class DiagnosisRequest(BaseModel):
    session_id: str | None = None
    website: str | None = None


class BookingRequest(BaseModel):
    session_id: str | None = None
    diagnosis_id: str | None = None
    name: str
    phone: str
    service_type: str
    vehicle_details: str | None = ""
    location: str
    scheduled_at: str | None = ""
    notes: str | None = ""
    website: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value or len(value.strip()) < 2:
            raise ValueError("Name must be at least 2 characters.")
        if len(value) > 120:
            raise ValueError("Name is too long.")
        return value.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        digits = re.sub(r"\D", "", value or "")
        # Accept a +91 prefix or a 10-digit Indian mobile starting 6-9.
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise ValueError("Enter a valid 10-digit Indian mobile number.")
        return "+91 " + digits if not value.strip().startswith("+") else value.strip()

    @field_validator("location")
    @classmethod
    def validate_location(cls, value: str) -> str:
        if not value or len(value.strip()) < 5:
            raise ValueError("Please share a pickup/location with at least 5 characters.")
        return value.strip()

    @field_validator("service_type")
    @classmethod
    def validate_service_type(cls, value: str) -> str:
        if value not in SERVICE_TYPES:
            raise ValueError("Unknown service type.")
        return value


def validation_errors(exc: ValidationError) -> dict[str, list[str]]:
    """Convert Pydantic errors into the DRF-style {field: [message]} shape."""
    output: dict[str, list[str]] = {}
    for error in exc.errors():
        location = [str(part) for part in error["loc"]]
        field = location[0] if location else "__all__"
        message = error["msg"]
        if message.startswith("Value error, "):
            message = message[len("Value error, ") :]
        output.setdefault(field, []).append(message)
    return output


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    # SQLite returns naive datetimes; the app stores UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def chat_message_out(message) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "session": str(message.session_id),
        "role": message.role,
        "content": message.content,
        "ai_used": bool(message.ai_used),
        "created_at": _iso(message.created_at),
    }


def media_upload_out(upload) -> dict[str, Any]:
    return {
        "id": str(upload.id),
        "session": str(upload.session_id),
        "original_name": upload.original_name,
        "mime_type": upload.mime_type,
        "size_bytes": int(upload.size_bytes or 0),
        "kind": upload.kind,
        "analyzed": bool(upload.analyzed),
        "analysis_note": upload.analysis_note,
        "created_at": _iso(upload.created_at),
    }


def diagnosis_out(diagnosis) -> dict[str, Any]:
    return {
        "id": str(diagnosis.id),
        "session": str(diagnosis.session_id),
        "summary": diagnosis.summary,
        "possible_causes": list(diagnosis.possible_causes or []),
        "supporting_symptoms": list(diagnosis.supporting_symptoms or []),
        "recommended_service": diagnosis.recommended_service,
        "next_steps": list(diagnosis.next_steps or []),
        "urgency": diagnosis.urgency,
        "drive_guidance": diagnosis.drive_guidance,
        "safety_warning": diagnosis.safety_warning,
        "inspection_recommended": bool(diagnosis.inspection_recommended),
        "ai_generated": bool(diagnosis.ai_generated),
        "created_at": _iso(diagnosis.created_at),
    }


def booking_out(booking) -> dict[str, Any]:
    return {
        "id": str(booking.id),
        "session": str(booking.session_id) if booking.session_id else None,
        "diagnosis": str(booking.diagnosis_id) if booking.diagnosis_id else None,
        "name": booking.name,
        "phone": booking.phone,
        "service_type": booking.service_type,
        "vehicle_details": booking.vehicle_details,
        "location": booking.location,
        "scheduled_at": booking.scheduled_at,
        "notes": booking.notes,
        "status": booking.status,
        "created_at": _iso(booking.created_at),
        "updated_at": _iso(booking.updated_at),
    }
