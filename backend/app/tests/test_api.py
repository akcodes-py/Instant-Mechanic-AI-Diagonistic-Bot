"""Comprehensive API tests. No live Groq calls — all provider interactions mocked."""
import io
import json
import uuid
from unittest.mock import patch

import pytest
from PIL import Image
from sqlalchemy import func, select

from app.config import settings
from app.models import Booking, ChatMessage, ChatSession, Diagnosis
from app.services import ai_service


async def post(client, path, payload):
    return await client.post(path, json=payload)


def _png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/api/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_valid_chat_creates_session_and_persists(client, db_session):
    response = await post(
        client,
        "/api/chat/",
        {"message": "My Creta 2021 diesel makes grinding noise when braking"},
    )
    assert response.status_code == 200
    session_id = response.json()["session_id"]
    assert await db_session.get(ChatSession, session_id) is not None
    count = await db_session.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )
    assert count == 2  # user + assistant
    assert "brak" in response.json()["reply"].lower()


@pytest.mark.asyncio
async def test_empty_chat_input(client):
    response = await post(client, "/api/chat/", {"message": "   "})
    assert response.status_code == 200
    assert "describe" in response.json()["reply"].lower()


@pytest.mark.asyncio
async def test_malformed_chat_long_message(client):
    response = await post(client, "/api/chat/", {"message": "x" * 2001})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_irrelevant_rejected_politely(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "What is the capital of France and best pasta recipe?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["action"] == "reject"
    assert "car" in body["reply"].lower()


@pytest.mark.asyncio
async def test_greeting_flow(client):
    response = await post(client, "/api/chat/", {"message": "Hello"})
    assert response.status_code == 200
    assert response.json()["action"] == "greet"


@pytest.mark.asyncio
async def test_follow_up_for_battery(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "car wont start clicking sound, Swift petrol"},
    )
    assert response.status_code == 200
    assert response.json()["action"] == "follow_up"
    assert "click" in response.json()["reply"].lower()


@pytest.mark.asyncio
async def test_vehicle_extraction_saved(client, db_session):
    response = await post(
        client,
        "/api/chat/",
        {"message": "My Honda City 2019 petrol overheats, steam from bonnet"},
    )
    session_id = response.json()["session_id"]
    session = await db_session.get(ChatSession, session_id)
    assert session.vehicle_make == "Honda"
    assert session.vehicle_year == "2019"


@pytest.mark.asyncio
async def test_diagnosis_rule_based_battery(client, db_session):
    response = await post(
        client,
        "/api/chat/",
        {"message": "wont start rapid clicking, battery dead"},
    )
    session_id = response.json()["session_id"]
    diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 201
    body = diagnosis.json()
    assert body["recommended_service"] == "battery_jumpstart"
    assert body["ai_used"] is False
    exists = await db_session.scalar(
        select(func.count(Diagnosis.id)).where(Diagnosis.session_id == session_id)
    )
    assert exists == 1
    assert "not a confirmed" in body["disclaimer"].lower()


@pytest.mark.asyncio
async def test_diagnosis_insufficient_no_messages(client, db_session):
    session = ChatSession()
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    response = await post(client, "/api/diagnosis/", {"session_id": str(session.id)})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_diagnosis_insufficient_irrelevant_only(client):
    response = await post(client, "/api/chat/", {"message": "Hi"})
    session_id = response.json()["session_id"]
    diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code in (400, 422)


@pytest.mark.asyncio
async def test_diagnosis_unsafe_override(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "There is smoke and burning smell plus fuel leak from engine"},
    )
    session_id = response.json()["session_id"]
    diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 201
    assert diagnosis.json()["urgency"] == "critical"
    assert "DO NOT DRIVE" in diagnosis.json()["drive_guidance"]


@pytest.mark.asyncio
async def test_groq_structured_success_mocked(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "My car makes a weird whistling at 80kmph with AC on, Verna 2020"},
    )
    session_id = response.json()["session_id"]
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
        diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 201
    assert diagnosis.json()["ai_used"] is True
    assert diagnosis.json()["summary"] == fake["summary"]


@pytest.mark.asyncio
async def test_missing_api_key_falls_back_without_crash(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "strange vibration at idle, i20 2018 petrol"},
    )
    session_id = response.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=False):
        diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 201
    assert diagnosis.json()["ai_used"] is False


@pytest.mark.asyncio
async def test_provider_timeout_returns_504(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "odd humming from rear wheel at 60kmph"},
    )
    session_id = response.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service,
        "groq_structured_diagnosis",
        side_effect=ai_service.AIServiceError("timed out", kind="timeout"),
    ):
        diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 504
    assert "timed out" in diagnosis.json()["error"].lower()


@pytest.mark.asyncio
async def test_provider_rate_limit_returns_503(client):
    response = await post(
        client,
        "/api/chat/",
        {"message": "odd humming from rear wheel at 60kmph"},
    )
    session_id = response.json()["session_id"]
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service,
        "groq_structured_diagnosis",
        side_effect=ai_service.AIServiceError("busy", kind="rate_limit"),
    ):
        diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    assert diagnosis.status_code == 503


@pytest.mark.asyncio
async def test_groq_chat_mocked_no_live_call(client):
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service,
        "groq_chat",
        return_value="Is the noise louder when turning left or right?",
    ) as mocked:
        response = await post(
            client,
            "/api/chat/",
            {
                "message": (
                    "My Venue makes a prolonged whining sound from the front "
                    "while accelerating gently uphill"
                )
            },
        )
        assert response.status_code == 200
        assert mocked.called or response.json()["action"] in ("follow_up", "ready")


@pytest.mark.asyncio
async def test_valid_image_upload(client, tmp_path, monkeypatch):
    response = await post(client, "/api/chat/", {"message": "flat tyre, need help"})
    session_id = response.json()["session_id"]
    monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
    upload = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("tyre.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201
    assert upload.json()["kind"] == "image"
    note = upload.json()["note"].lower()
    assert "not auto-analyzed" in note or "mechanic" in note


@pytest.mark.asyncio
async def test_unsupported_file_rejected(client):
    response = await post(client, "/api/chat/", {"message": "battery issue"})
    session_id = response.json()["session_id"]
    upload = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("evil.exe", b"MZ fake", "application/octet-stream")},
    )
    assert upload.status_code == 400


@pytest.mark.asyncio
async def test_oversized_upload_rejected(client):
    response = await post(client, "/api/chat/", {"message": "battery issue"})
    session_id = response.json()["session_id"]
    big = b"\xff\xd8\xff" + b"0" * (11 * 1024 * 1024)
    upload = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("big.png", big, "image/jpeg")},
    )
    assert upload.status_code == 400


@pytest.mark.asyncio
async def test_fake_image_content_rejected(client, tmp_path, monkeypatch):
    response = await post(client, "/api/chat/", {"message": "tyre cut photo"})
    session_id = response.json()["session_id"]
    monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
    upload = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("fake.png", b"not an image at all", "image/png")},
    )
    assert upload.status_code == 400


@pytest.mark.asyncio
async def test_booking_creation_and_retrieval(client, db_session):
    response = await post(client, "/api/chat/", {"message": "out of fuel near Sohna road"})
    session_id = response.json()["session_id"]
    booking = await post(
        client,
        "/api/booking/",
        {
            "session_id": session_id,
            "name": "Atul Kumar",
            "phone": "9876543210",
            "service_type": "fuel_delivery",
            "location": "Sohna Road, Gurugram",
        },
    )
    assert booking.status_code == 201
    booking_id = booking.json()["id"]
    assert await db_session.get(Booking, booking_id) is not None
    fetched = await client.get(f"/api/booking/{booking_id}/")
    assert fetched.status_code == 200
    assert fetched.json()["service_type"] == "fuel_delivery"


@pytest.mark.asyncio
async def test_booking_invalid_phone(client):
    booking = await post(
        client,
        "/api/booking/",
        {
            "name": "A",
            "phone": "123",
            "service_type": "towing",
            "location": "x",
        },
    )
    assert booking.status_code == 400


@pytest.mark.asyncio
async def test_booking_invalid_service(client):
    booking = await post(
        client,
        "/api/booking/",
        {
            "name": "Atul",
            "phone": "9876543210",
            "service_type": "spaceship",
            "location": "Sector 75 Gurugram",
        },
    )
    assert booking.status_code == 400


@pytest.mark.asyncio
async def test_unknown_booking_404(client):
    response = await client.get(f"/api/booking/{uuid.uuid4()}/")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_session_isolation_booking_lookup(client, db_session):
    response = await post(client, "/api/chat/", {"message": "key locked inside car"})
    session_id = response.json()["session_id"]
    booking = await post(
        client,
        "/api/booking/",
        {
            "session_id": session_id,
            "name": "Atul",
            "phone": "9876543210",
            "service_type": "key_lockout",
            "location": "MG Road Gurugram",
        },
    )
    booking_id = booking.json()["id"]
    other = ChatSession()
    db_session.add(other)
    await db_session.commit()
    await db_session.refresh(other)
    fetched = await client.get(
        f"/api/booking/{booking_id}/", params={"session_id": str(other.id)}
    )
    assert fetched.status_code == 404


@pytest.mark.asyncio
async def test_diagnosis_session_mismatch_rejected(client, db_session):
    first = await post(client, "/api/chat/", {"message": "battery dead clicking"})
    session_id = first.json()["session_id"]
    second_session = ChatSession()
    db_session.add(second_session)
    await db_session.commit()
    await db_session.refresh(second_session)
    diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    diagnosis_id = diagnosis.json()["id"]
    booking = await post(
        client,
        "/api/booking/",
        {
            "session_id": str(second_session.id),
            "diagnosis_id": diagnosis_id,
            "name": "Atul",
            "phone": "9876543210",
            "service_type": "battery_jumpstart",
            "location": "Sector 75 Gurugram",
        },
    )
    assert booking.status_code == 400


@pytest.mark.asyncio
async def test_history_returns_conversation(client):
    response = await post(client, "/api/chat/", {"message": "flat tyre,puncture"})
    session_id = response.json()["session_id"]
    await post(client, "/api/diagnosis/", {"session_id": session_id})
    history = await client.get(f"/api/history/{session_id}/")
    assert history.status_code == 200
    assert len(history.json()["messages"]) >= 2
    assert len(history.json()["diagnoses"]) >= 1


@pytest.mark.asyncio
async def test_unknown_session_history_404(client):
    response = await client.get(f"/api/history/{uuid.uuid4()}/")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_errors_do_not_leak_secrets(client):
    with patch.object(ai_service, "is_configured", return_value=True), patch.object(
        ai_service,
        "groq_structured_diagnosis",
        side_effect=Exception("GROQ_API_KEY=sk-secret traceback /etc/passwd"),
    ), patch.object(ai_service, "groq_chat", return_value=""):
        response = await post(
            client,
            "/api/chat/",
            {"message": "weird dashboard light humming noise at night"},
        )
        session_id = response.json()["session_id"]
        diagnosis = await post(client, "/api/diagnosis/", {"session_id": session_id})
    body = json.dumps(diagnosis.json())
    assert "sk-secret" not in body
    assert "traceback" not in body.lower()


@pytest.mark.asyncio
async def test_honeypot_rejected(client):
    response = await post(
        client, "/api/chat/", {"message": "battery issue", "website": "bot"}
    )
    assert response.status_code == 400
