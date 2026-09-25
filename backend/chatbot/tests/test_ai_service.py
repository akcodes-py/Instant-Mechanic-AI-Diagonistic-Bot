"""Unit tests for the isolated Groq service layer (all HTTP mocked)."""
from unittest.mock import MagicMock, patch

import pytest

from chatbot.services import ai_service


def _resp(content):
    m = MagicMock()
    m.choices = [MagicMock(message=MagicMock(content=content))]
    return m


@pytest.mark.django_db
def test_missing_key_raises():
    with patch.object(ai_service, "is_configured", return_value=False):
        with pytest.raises(ai_service.AIServiceError) as e:
            ai_service.groq_chat([{"role": "user", "content": "hi"}])
        assert e.value.kind == "missing_key"


def test_parse_valid_json():
    raw = '{"summary": "Battery weak", "possible_causes": ["old battery"], "supporting_symptoms": ["click"], "recommended_service": "battery_jumpstart", "next_steps": ["jumpstart"], "urgency": "medium", "drive_guidance": "ok", "safety_warning": "careful", "inspection_recommended": true}'
    out = ai_service.parse_diagnosis_json("prefix " + raw + " suffix")
    assert out["recommended_service"] == "battery_jumpstart"
    assert out["urgency"] == "medium"


def test_parse_invalid_json_raises():
    with pytest.raises(ai_service.AIServiceError) as e:
        ai_service.parse_diagnosis_json("not json at all {{{")
    assert e.value.kind == "invalid_response"


def test_parse_normalizes_bad_enums():
    raw = '{"summary": "x", "recommended_service": "teleport", "urgency": "extreme"}'
    out = ai_service.parse_diagnosis_json(raw)
    assert out["recommended_service"] == "general_repair"
    assert out["urgency"] == "medium"


def test_groq_chat_timeout_mapped():
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception("connection timed out")
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "_client", return_value=fake_client
    ):
        with pytest.raises(ai_service.AIServiceError) as e:
            ai_service.groq_chat([{"role": "user", "content": "noise?"}])
        assert e.value.kind == "timeout"


def test_groq_chat_rate_limit_mapped():
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = Exception("429 rate_limit_exceeded")
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "_client", return_value=fake_client
    ):
        with pytest.raises(ai_service.AIServiceError) as e:
            ai_service.groq_chat([{"role": "user", "content": "noise?"}])
        assert e.value.kind == "rate_limit"
