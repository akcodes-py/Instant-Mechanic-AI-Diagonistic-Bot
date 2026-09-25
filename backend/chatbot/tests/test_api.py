"""Comprehensive API tests. No live Groq calls — all provider interactions mocked."""
import io
import json
import uuid
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings

from chatbot.models import Booking, ChatMessage, ChatSession, Diagnosis
from chatbot.services import ai_service


def post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type="application/json")


@pytest.mark.django_db
def test_health(client):
    r = client.get("/api/health/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.django_db
def test_valid_chat_creates_session_and_persists(client):
    r = post(client, "/api/chat/", {"message": "My Creta 2021 diesel makes grinding noise when braking"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    assert ChatSession.objects.filter(id=sid).exists()
    assert ChatMessage.objects.filter(session_id=sid).count() == 2  # user + assistant
    # follow-up expected for brake rule
    assert "brak" in r.json()["reply"].lower()


@pytest.mark.django_db
def test_empty_chat_input(client):
    r = post(client, "/api/chat/", {"message": "   "})
    assert r.status_code == 200
    assert "describe" in r.json()["reply"].lower()


@pytest.mark.django_db
def test_malformed_chat_long_message(client):
    r = post(client, "/api/chat/", {"message": "x" * 2001})
    assert r.status_code == 400


@pytest.mark.django_db
def test_irrelevant_rejected_politely(client):
    r = post(client, "/api/chat/", {"message": "What is the capital of France and best pasta recipe?"})
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "reject"
    assert "car" in body["reply"].lower()


@pytest.mark.django_db
def test_greeting_flow(client):
    r = post(client, "/api/chat/", {"message": "Hello"})
    assert r.status_code == 200
    assert r.json()["action"] == "greet"


@pytest.mark.django_db
def test_follow_up_for_battery(client):
    r = post(client, "/api/chat/", {"message": "car wont start clicking sound, Swift petrol"})
    assert r.status_code == 200
    assert r.json()["action"] == "follow_up"
    assert "click" in r.json()["reply"].lower()


@pytest.mark.django_db
def test_vehicle_extraction_saved(client):
    r = post(client, "/api/chat/", {"message": "My Honda City 2019 petrol overheats, steam from bonnet"})
    sid = r.json()["session_id"]
    s = ChatSession.objects.get(id=sid)
    assert s.vehicle_make == "Honda"
    assert s.vehicle_year == "2019"


@pytest.mark.django_db
def test_diagnosis_rule_based_battery(client):
    r = post(client, "/api/chat/", {"message": "wont start rapid clicking, battery dead"})
    sid = r.json()["session_id"]
    d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 201
    body = d.json()
    assert body["recommended_service"] == "battery_jumpstart"
    assert body["ai_used"] is False
    assert Diagnosis.objects.filter(session_id=sid).exists()
    assert "not a confirmed" in body["disclaimer"].lower()


@pytest.mark.django_db
def test_diagnosis_insufficient_no_messages(client):
    s = ChatSession.objects.create()
    r = post(client, "/api/diagnosis/", {"session_id": str(s.id)})
    assert r.status_code == 400


@pytest.mark.django_db
def test_diagnosis_insufficient_irrelevant_only(client):
    r = post(client, "/api/chat/", {"message": "Hi"})
    sid = r.json()["session_id"]
    d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code in (400, 422)


@pytest.mark.django_db
def test_diagnosis_unsafe_override(client):
    r = post(client, "/api/chat/", {"message": "There is smoke and burning smell plus fuel leak from engine"})
    sid = r.json()["session_id"]
    d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 201
    assert d.json()["urgency"] == "critical"
    assert "DO NOT DRIVE" in d.json()["drive_guidance"]


@pytest.mark.django_db
def test_groq_structured_success_mocked(client):
    r = post(client, "/api/chat/", {"message": "My car makes a weird whistling at 80kmph with AC on, Verna 2020"})
    sid = r.json()["session_id"]
    fake = {
        "summary": "AC belt or blower issue at speed.",
        "possible_causes": ["Worn auxiliary belt"],
        "supporting_symptoms": ["whistling at speed"],
        "recommended_service": "general_repair",
        "next_steps": ["Inspect belt"],
        "urgency": "medium",
        "drive_guidance": "Drive gently.",
        "safety_warning": "Preliminary only.",
        "inspection_recommended": True,
    }
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "groq_structured_diagnosis", return_value=fake
    ):
        d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 201
    assert d.json()["ai_used"] is True
    assert d.json()["summary"] == fake["summary"]


@pytest.mark.django_db
def test_missing_api_key_falls_back_without_crash(client):
    r = post(client, "/api/chat/", {"message": "strange vibration at idle, i20 2018 petrol"})
    sid = r.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=False):
        d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 201
    assert d.json()["ai_used"] is False


@pytest.mark.django_db
def test_provider_timeout_returns_504(client):
    r = post(client, "/api/chat/", {"message": "odd humming from rear wheel at 60kmph"})
    sid = r.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "groq_structured_diagnosis",
        side_effect=ai_service.AIServiceError("timed out", kind="timeout"),
    ):
        d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 504
    assert "timed out" in d.json()["error"].lower()


@pytest.mark.django_db
def test_provider_rate_limit_returns_503(client):
    r = post(client, "/api/chat/", {"message": "odd humming from rear wheel at 60kmph"})
    sid = r.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "groq_structured_diagnosis",
        side_effect=ai_service.AIServiceError("busy", kind="rate_limit"),
    ):
        d = post(client, "/api/diagnosis/", {"session_id": sid})
    assert d.status_code == 503


@pytest.mark.django_db
def test_groq_chat_mocked_no_live_call(client):
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "groq_chat", return_value="Is the noise louder when turning left or right?"
    ) as m:
        r = post(client, "/api/chat/", {"message": "My Venue makes a prolonged whining sound from the front while accelerating gently uphill"})
        assert r.status_code == 200
        assert m.called or r.json()["action"] in ("follow_up", "ready")


def _png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.django_db
def test_valid_image_upload(client, tmp_path):
    r = post(client, "/api/chat/", {"message": "flat tyre, need help"})
    sid = r.json()["session_id"]
    f = SimpleUploadedFile("tyre.png", _png_bytes(), content_type="image/png")
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        up = client.post("/api/upload/", {"session_id": sid, "file": f})
    assert up.status_code == 201
    assert up.json()["kind"] == "image"
    assert "not auto-analyzed" in up.json()["note"].lower() or "mechanic" in up.json()["note"].lower()


@pytest.mark.django_db
def test_unsupported_file_rejected(client):
    r = post(client, "/api/chat/", {"message": "battery issue"})
    sid = r.json()["session_id"]
    f = SimpleUploadedFile("evil.exe", b"MZ fake", content_type="application/octet-stream")
    up = client.post("/api/upload/", {"session_id": sid, "file": f})
    assert up.status_code == 400


@pytest.mark.django_db
def test_oversized_upload_rejected(client):
    r = post(client, "/api/chat/", {"message": "battery issue"})
    sid = r.json()["session_id"]
    big = SimpleUploadedFile("big.png", b"\xff\xd8\xff" + b"0" * (11 * 1024 * 1024), content_type="image/jpeg")
    up = client.post("/api/upload/", {"session_id": sid, "file": big})
    assert up.status_code == 400


@pytest.mark.django_db
def test_fake_image_content_rejected(client, tmp_path):
    r = post(client, "/api/chat/", {"message": "tyre cut photo"})
    sid = r.json()["session_id"]
    f = SimpleUploadedFile("fake.png", b"not an image at all", content_type="image/png")
    with override_settings(MEDIA_ROOT=str(tmp_path)):
        up = client.post("/api/upload/", {"session_id": sid, "file": f})
    assert up.status_code == 400


@pytest.mark.django_db
def test_booking_creation_and_retrieval(client):
    r = post(client, "/api/chat/", {"message": "out of fuel near Sohna road"})
    sid = r.json()["session_id"]
    b = post(client, "/api/booking/", {
        "session_id": sid, "name": "Atul Kumar", "phone": "9876543210",
        "service_type": "fuel_delivery", "location": "Sohna Road, Gurugram",
    })
    assert b.status_code == 201
    bid = b.json()["id"]
    assert Booking.objects.filter(id=bid).exists()
    g = client.get(f"/api/booking/{bid}/")
    assert g.status_code == 200
    assert g.json()["service_type"] == "fuel_delivery"


@pytest.mark.django_db
def test_booking_invalid_phone(client):
    b = post(client, "/api/booking/", {
        "name": "A", "phone": "123", "service_type": "towing", "location": "x",
    })
    assert b.status_code == 400


@pytest.mark.django_db
def test_booking_invalid_service(client):
    b = post(client, "/api/booking/", {
        "name": "Atul", "phone": "9876543210", "service_type": "spaceship",
        "location": "Sector 75 Gurugram",
    })
    assert b.status_code == 400


@pytest.mark.django_db
def test_unknown_booking_404(client):
    g = client.get(f"/api/booking/{uuid.uuid4()}/")
    assert g.status_code == 404


@pytest.mark.django_db
def test_session_isolation_booking_lookup(client):
    r = post(client, "/api/chat/", {"message": "key locked inside car"})
    sid = r.json()["session_id"]
    b = post(client, "/api/booking/", {
        "session_id": sid, "name": "Atul", "phone": "9876543210",
        "service_type": "key_lockout", "location": "MG Road Gurugram",
    })
    bid = b.json()["id"]
    other = ChatSession.objects.create()
    g = client.get(f"/api/booking/{bid}/?session_id={other.id}")
    assert g.status_code == 404


@pytest.mark.django_db
def test_diagnosis_session_mismatch_rejected(client):
    r1 = post(client, "/api/chat/", {"message": "battery dead clicking"})
    sid1 = r1.json()["session_id"]
    s2 = ChatSession.objects.create()
    d = post(client, "/api/diagnosis/", {"session_id": sid1})
    did = d.json()["id"]
    b = post(client, "/api/booking/", {
        "session_id": str(s2.id), "diagnosis_id": did, "name": "Atul",
        "phone": "9876543210", "service_type": "battery_jumpstart",
        "location": "Sector 75 Gurugram",
    })
    assert b.status_code == 400


@pytest.mark.django_db
def test_history_returns_conversation(client):
    r = post(client, "/api/chat/", {"message": "flat tyre,puncture"})
    sid = r.json()["session_id"]
    post(client, "/api/diagnosis/", {"session_id": sid})
    h = client.get(f"/api/history/{sid}/")
    assert h.status_code == 200
    assert len(h.json()["messages"]) >= 2
    assert len(h.json()["diagnoses"]) >= 1


@pytest.mark.django_db
def test_unknown_session_history_404(client):
    h = client.get(f"/api/history/{uuid.uuid4()}/")
    assert h.status_code == 404


@pytest.mark.django_db
def test_errors_do_not_leak_secrets(client):
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service, "groq_structured_diagnosis",
        side_effect=Exception("GROQ_API_KEY=sk-secret traceback /etc/passwd"),
    ):
        r = post(client, "/api/chat/", {"message": "weird dashboard light humming noise at night"})
        sid = r.json()["session_id"]
        d = post(client, "/api/diagnosis/", {"session_id": sid})
    body = json.dumps(d.json())
    assert "sk-secret" not in body
    assert "traceback" not in body.lower()


@pytest.mark.django_db
def test_honeypot_rejected(client):
    r = post(client, "/api/chat/", {"message": "battery issue", "website": "bot"})
    assert r.status_code == 400
