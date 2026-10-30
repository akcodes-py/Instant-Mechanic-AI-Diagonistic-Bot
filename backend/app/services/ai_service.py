"""Isolated Groq integration. All AI calls go through this module only.

Provides:
- is_configured()
- groq_chat(messages, ...) -> str  (with timeout/rate-limit/error mapping)
- groq_structured_diagnosis(context) -> dict | raises AIServiceError

Never raises raw SDK errors to views; always AIServiceError with safe message.
Never logs or returns API keys.
"""
import json
import logging
import re
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_MECHANIC = (
    "You are IM Buddy, a senior automobile technician for Instant Mechanic "
    "(Delhi NCR roadside assistance). Be concise, practical, and safety-first. "
    "Only answer car/mechanical topics. Never invent prices, ETAs, mechanic "
    "names, or guaranteed outcomes. Always recommend in-person inspection for "
    "uncertain or safety-critical issues. If symptoms suggest an unsafe vehicle "
    "(smoke, fire, fuel leak, brake failure, overheating, steering loss), tell "
    "the user to stop safely and call +91 6392077642."
)


class AIServiceError(Exception):
    def __init__(self, message: str, kind: str = "provider_error"):
        super().__init__(message)
        self.kind = kind  # missing_key|timeout|rate_limit|invalid_response|provider_error


def is_configured() -> bool:
    return bool(getattr(settings, "GROQ_API_KEY", ""))


def _client():
    if not is_configured():
        raise AIServiceError(
            "AI service is not configured on the server.", kind="missing_key"
        )
    try:
        from groq import Groq
    except ImportError as e:  # pragma: no cover
        raise AIServiceError("AI provider library unavailable.", kind="provider_error") from e
    return Groq(api_key=settings.GROQ_API_KEY, timeout=settings.GROQ_TIMEOUT_S)


def groq_chat(messages: list, max_tokens: int = 400) -> str:
    """Free-form assistant reply for nuanced cases. Caller must validate input first."""
    client = _client()
    try:
        resp = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "system", "content": SYSTEM_MECHANIC}] + messages,
            max_tokens=max_tokens,
            temperature=0.4,
        )
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            raise AIServiceError("Empty response from AI provider.", kind="invalid_response")
        return text
    except AIServiceError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg or "rate_limit" in msg:
            raise AIServiceError("AI service is busy. Please try again shortly.", kind="rate_limit") from e
        if "timeout" in msg or "timed out" in msg:
            raise AIServiceError("AI service timed out. Please try again.", kind="timeout") from e
        logger.warning("Groq chat error: %s", type(e).__name__)
        raise AIServiceError("AI service is temporarily unavailable.", kind="provider_error") from e


DIAGNOSIS_SCHEMA_HINT = """Return ONLY valid JSON with keys:
{"summary": str, "possible_causes": [str...], "supporting_symptoms": [str...],
"recommended_service": one of [battery_jumpstart, flat_tyre, towing, fuel_delivery, key_lockout, general_repair, inspection],
"next_steps": [str...], "urgency": one of [low, medium, high, critical],
"drive_guidance": str, "safety_warning": str, "inspection_recommended": bool}"""


def groq_structured_diagnosis(symptom_text: str, vehicle: str = "") -> dict:
    client = _client()
    prompt = (
        f"Vehicle: {vehicle or 'unknown'}\nSymptoms & history:\n{symptom_text[:4000]}\n\n"
        + DIAGNOSIS_SCHEMA_HINT
    )
    try:
        resp = client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_MECHANIC},
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
            temperature=0.3,
        )
        raw = (resp.choices[0].message.content or "").strip()
        return parse_diagnosis_json(raw)
    except AIServiceError:
        raise
    except Exception as e:
        msg = str(e).lower()
        if "rate" in msg or "429" in msg:
            raise AIServiceError("AI service is busy. Please try again shortly.", kind="rate_limit") from e
        if "timeout" in msg or "timed out" in msg:
            raise AIServiceError("AI service timed out. Please try again.", kind="timeout") from e
        logger.warning("Groq diagnosis error: %s", type(e).__name__)
        raise AIServiceError("AI service is temporarily unavailable.", kind="provider_error") from e


def parse_diagnosis_json(raw: str) -> dict:
    """Extract and validate structured JSON from model output."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    candidate = m.group(0) if m else raw
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise AIServiceError("AI returned an unreadable diagnosis.", kind="invalid_response") from e
    allowed_services = {"battery_jumpstart", "flat_tyre", "towing", "fuel_delivery", "key_lockout", "general_repair", "inspection"}
    allowed_urgency = {"low", "medium", "high", "critical"}
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        raise AIServiceError("AI returned an incomplete diagnosis.", kind="invalid_response")
    data.setdefault("possible_causes", [])
    data.setdefault("supporting_symptoms", [])
    data.setdefault("next_steps", [])
    if data.get("recommended_service") not in allowed_services:
        data["recommended_service"] = "general_repair"
    if data.get("urgency") not in allowed_urgency:
        data["urgency"] = "medium"
    data.setdefault("drive_guidance", "")
    data.setdefault("safety_warning", "")
    data.setdefault("inspection_recommended", True)
    # Truncate to sane sizes (avoid DB bloat / prompt injection spill).
    for k in ("possible_causes", "supporting_symptoms", "next_steps"):
        if not isinstance(data[k], list):
            data[k] = []
        data[k] = [str(x)[:300] for x in data[k][:8]]
    data["summary"] = data["summary"][:1000]
    return data
