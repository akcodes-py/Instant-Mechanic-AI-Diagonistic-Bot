from rest_framework import serializers
from .models import Booking, ChatMessage, ChatSession, Diagnosis, MediaUpload


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatSession
        fields = ["id", "vehicle_make", "vehicle_model", "vehicle_year", "vehicle_fuel", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ChatMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChatMessage
        fields = ["id", "session", "role", "content", "ai_used", "created_at"]
        read_only_fields = ["id", "created_at"]


class MediaUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = MediaUpload
        fields = ["id", "session", "original_name", "mime_type", "size_bytes", "kind", "analyzed", "analysis_note", "created_at"]
        read_only_fields = ["id", "created_at"]


class DiagnosisSerializer(serializers.ModelSerializer):
    class Meta:
        model = Diagnosis
        fields = [
            "id", "session", "summary", "possible_causes", "supporting_symptoms",
            "recommended_service", "next_steps", "urgency", "drive_guidance",
            "safety_warning", "inspection_recommended", "ai_generated", "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BookingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Booking
        fields = [
            "id", "session", "diagnosis", "name", "phone", "service_type",
            "vehicle_details", "location", "scheduled_at", "notes", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "status", "created_at", "updated_at"]

    def validate_phone(self, value: str):
        import re
        digits = re.sub(r"\D", "", value or "")
        # Accept +91 prefix or 10-digit Indian mobile starting 6-9.
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        return "+91 " + digits if not value.strip().startswith("+") else value.strip()

    def validate_name(self, value: str):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        # Honeypot: reject obvious bot payloads.
        if len(value) > 120:
            raise serializers.ValidationError("Name is too long.")
        return value.strip()

    def validate_location(self, value: str):
        if not value or len(value.strip()) < 5:
            raise serializers.ValidationError("Please share a pickup/location with at least 5 characters.")
        return value.strip()

    def validate(self, attrs):
        # Session isolation: if diagnosis given, it must belong to the session (when session given).
        session = attrs.get("session") or (self.instance.session if self.instance else None)
        diagnosis = attrs.get("diagnosis")
        if diagnosis and session and diagnosis.session_id != session.id:
            raise serializers.ValidationError({"diagnosis": "Diagnosis does not belong to this chat session."})
        return attrs
