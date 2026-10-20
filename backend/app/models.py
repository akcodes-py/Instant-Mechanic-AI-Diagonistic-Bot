"""SQLAlchemy 2.0 models for chat-to-diagnosis-to-booking workflow."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.constants import BOOKING_STATUSES, SERVICE_TYPES, URGENCY_LEVELS
from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
    vehicle_make = Column(String(80), nullable=False, default="")
    vehicle_model = Column(String(80), nullable=False, default="")
    vehicle_year = Column(String(10), nullable=False, default="")
    vehicle_fuel = Column(String(20), nullable=False, default="")

    messages = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChatMessage.created_at",
    )
    diagnoses = relationship(
        "Diagnosis",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    uploads = relationship(
        "MediaUpload",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="MediaUpload.created_at",
    )
    bookings = relationship(
        "Booking",
        back_populates="session",
        passive_deletes=True,
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_created", "session_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    ai_used = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    session = relationship("ChatSession", back_populates="messages")


class MediaUpload(Base):
    __tablename__ = "media_uploads"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_path = Column(String(500), nullable=False)
    original_name = Column(String(255), nullable=False)
    mime_type = Column(String(120), nullable=False, default="")
    size_bytes = Column(Integer, nullable=False, default=0)
    kind = Column(String(10), nullable=False, default="other")
    analyzed = Column(Boolean, nullable=False, default=False)
    analysis_note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    session = relationship("ChatSession", back_populates="uploads")


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (
        Index("ix_diagnoses_session_created", "session_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    summary = Column(Text, nullable=False)
    possible_causes = Column(JSON, nullable=False, default=list)
    supporting_symptoms = Column(JSON, nullable=False, default=list)
    recommended_service = Column(String(200), nullable=False, default="general_repair")
    next_steps = Column(JSON, nullable=False, default=list)
    urgency = Column(String(10), nullable=False, default="medium")
    drive_guidance = Column(Text, nullable=False, default="")
    safety_warning = Column(Text, nullable=False, default="")
    inspection_recommended = Column(Boolean, nullable=False, default=True)
    ai_generated = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    session = relationship("ChatSession", back_populates="diagnoses")
    bookings = relationship("Booking", back_populates="diagnosis", passive_deletes=True)


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(String(36), primary_key=True, default=_uuid)
    session_id = Column(
        String(36),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    diagnosis_id = Column(
        String(36),
        ForeignKey("diagnoses.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = Column(String(120), nullable=False)
    phone = Column(String(20), nullable=False, index=True)
    service_type = Column(String(30), nullable=False)
    vehicle_details = Column(String(255), nullable=False, default="")
    location = Column(Text, nullable=False)
    scheduled_at = Column(String(80), nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    status = Column(String(12), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    session = relationship("ChatSession", back_populates="bookings")
    diagnosis = relationship("Diagnosis", back_populates="bookings")


# Keep the text constants importable for validation and tests.
__all__ = [
    "Base",
    "Booking",
    "ChatMessage",
    "ChatSession",
    "Diagnosis",
    "MediaUpload",
    "BOOKING_STATUSES",
    "SERVICE_TYPES",
    "URGENCY_LEVELS",
]
