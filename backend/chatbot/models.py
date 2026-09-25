"""Database models for chat-to-diagnosis-to-booking workflow."""
import uuid
from django.db import models


class ChatSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    vehicle_make = models.CharField(max_length=80, blank=True, default="")
    vehicle_model = models.CharField(max_length=80, blank=True, default="")
    vehicle_year = models.CharField(max_length=10, blank=True, default="")
    vehicle_fuel = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):  # pragma: no cover
        return f"Session {self.id}"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ("user", "user"),
        ("assistant", "assistant"),
        ("system", "system"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    ai_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["session", "created_at"])]

    def __str__(self):  # pragma: no cover
        return f"{self.role}: {self.content[:40]}"


class MediaUpload(models.Model):
    KIND_CHOICES = [
        ("image", "image"),
        ("audio", "audio"),
        ("video", "video"),
        ("other", "other"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="uploads"
    )
    file = models.FileField(upload_to="uploads/%Y/%m/%d/")
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True, default="")
    size_bytes = models.PositiveIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="other")
    analyzed = models.BooleanField(default=False)
    analysis_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):  # pragma: no cover
        return f"{self.kind} {self.original_name}"


class Diagnosis(models.Model):
    URGENCY_CHOICES = [
        ("low", "low"),
        ("medium", "medium"),
        ("high", "high"),
        ("critical", "critical"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession, on_delete=models.CASCADE, related_name="diagnoses"
    )
    summary = models.TextField()
    possible_causes = models.JSONField(default=list)
    supporting_symptoms = models.JSONField(default=list)
    recommended_service = models.CharField(max_length=200)
    next_steps = models.JSONField(default=list)
    urgency = models.CharField(max_length=10, choices=URGENCY_CHOICES, default="medium")
    drive_guidance = models.TextField(blank=True, default="")
    safety_warning = models.TextField(blank=True, default="")
    inspection_recommended = models.BooleanField(default=True)
    ai_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["session", "-created_at"])]

    def __str__(self):  # pragma: no cover
        return f"Diagnosis {self.id} ({self.urgency})"


class Booking(models.Model):
    STATUS_CHOICES = [
        ("pending", "pending"),
        ("confirmed", "confirmed"),
        ("completed", "completed"),
        ("cancelled", "cancelled"),
    ]
    SERVICE_CHOICES = [
        ("battery_jumpstart", "battery_jumpstart"),
        ("flat_tyre", "flat_tyre"),
        ("towing", "towing"),
        ("fuel_delivery", "fuel_delivery"),
        ("key_lockout", "key_lockout"),
        ("general_repair", "general_repair"),
        ("inspection", "inspection"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    diagnosis = models.ForeignKey(
        Diagnosis,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, db_index=True)
    service_type = models.CharField(max_length=30, choices=SERVICE_CHOICES)
    vehicle_details = models.CharField(max_length=255, blank=True, default="")
    location = models.TextField()
    scheduled_at = models.CharField(max_length=80, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):  # pragma: no cover
        return f"Booking {self.id} {self.service_type}"
