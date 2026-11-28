"""API-level hardening tests: headers, throttling, image privacy and payloads."""
import io
import logging
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.config import settings
from app.security.image_sanitizer import detect_image_format, sanitize_image_bytes
from app.security.middleware import (
    PIIScrubFilter,
    SECURITY_HEADERS,
    api_rate_limit,
    install_security,
    limiter,
    scrub_pii,
)


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buffer, format="PNG")
    return buffer.getvalue()


async def _session_id(client) -> str:
    response = await client.post("/api/chat/", json={"message": "flat tyre, need help"})
    assert response.status_code == 200
    return response.json()["session_id"]


@pytest.mark.asyncio
async def test_security_headers_on_every_response(client):
    response = await client.get("/api/health/")
    assert response.status_code == 200
    for name, value in SECURITY_HEADERS.items():
        assert response.headers.get(name) == value


@pytest.mark.asyncio
async def test_slowapi_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setattr(settings, "API_RATE_LIMIT_PER_MIN", 2)
    limiter.reset()

    test_app = FastAPI()
    install_security(test_app)

    @test_app.get("/ping/")
    @limiter.limit(api_rate_limit)
    async def ping(request: Request):
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        assert (await client.get("/ping/")).status_code == 200
        assert (await client.get("/ping/")).status_code == 200
        limited = await client.get("/ping/")
        assert limited.status_code == 429
        assert limited.headers.get("Retry-After") == "60"
        assert "Too many requests" in limited.json()["error"]
    limiter.reset()


@pytest.mark.asyncio
async def test_invalid_magic_bytes_rejected(client):
    session_id = await _session_id(client)
    response = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("dashboard.png", b"this is not an image", "image/png")},
    )
    assert response.status_code == 400
    assert "error" in response.json()


@pytest.mark.asyncio
async def test_oversized_image_rejected_before_storage(client):
    session_id = await _session_id(client)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (6 * 1024 * 1024)
    response = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("dashboard.png", big, "image/png")},
    )
    assert response.status_code == 400
    assert "5 MB" in response.json()["error"]


@pytest.mark.asyncio
async def test_exif_and_gps_are_stripped_in_memory(client, tmp_path, monkeypatch):
    buffer = io.BytesIO()
    image = Image.new("RGB", (16, 16), "green")
    exif = image.getexif()
    exif[271] = "LeakedCameraMake"  # Make tag
    gps = exif.get_ifd(34853)  # GPSInfo IFD
    gps[1] = "N"
    gps[2] = (28.0, 0.0, 0.0)
    image.save(buffer, format="PNG", exif=exif)
    raw = buffer.getvalue()
    assert b"LeakedCameraMake" in raw

    clean = sanitize_image_bytes(raw)
    assert b"LeakedCameraMake" not in clean.data
    with Image.open(io.BytesIO(clean.data)) as reopened:
        assert not reopened.getexif()

    monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
    session_id = await _session_id(client)
    response = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": ("dash.png", raw, "image/png")},
    )
    assert response.status_code == 201
    stored = next(Path(tmp_path).rglob("*.png"))
    assert b"LeakedCameraMake" not in stored.read_bytes()


@pytest.mark.asyncio
async def test_filename_injection_never_enters_chat_history(client):
    session_id = await _session_id(client)
    hostile_name = "'; DROP TABLE messages; --<script>.png"
    response = await client.post(
        "/api/upload/",
        data={"session_id": session_id},
        files={"file": (hostile_name, _png_bytes(), "image/png")},
    )
    assert response.status_code == 201
    history = await client.get(f"/api/history/{session_id}/")
    assert history.status_code == 200
    # The upload record keeps the client name, but no message/prompt ever sees it.
    transcript = " ".join(
        str(message["content"]) for message in history.json()["messages"]
    )
    assert "DROP TABLE" not in transcript
    assert "<script>" not in transcript


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    ["<script>alert(1)</script> start the car", "' OR 1=1 --", "../../etc/passwd"],
)
async def test_sqli_xss_payloads_are_rejected_by_validation(client, payload):
    response = await client.post("/api/chat/", json={"message": payload})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pii_is_scrubbed_from_log_records():
    message = "call 9876543210 or email atul@instantmechanic.online, VIN MH12AB12345678901"
    cleaned = scrub_pii(message)
    assert "9876543210" not in cleaned
    assert "atul@instantmechanic.online" not in cleaned
    assert "MH12AB12345678901" not in cleaned
    assert "[PHONE]" in cleaned and "[EMAIL]" in cleaned

    record = logging.LogRecord("test", logging.WARNING, __file__, 1, message, (), None)
    assert PIIScrubFilter().filter(record) is True
    assert "9876543210" not in str(record.msg)


@pytest.mark.asyncio
async def test_wide_conformal_set_returns_hitl_without_llm(client, tmp_path, monkeypatch):
    import json

    model_path = tmp_path / "model.bin"
    model_path.write_bytes(b"test")
    (tmp_path / "calibration.json").write_text(
        json.dumps({"temperature": 1.0, "q_hat": 0.5, "alpha": 0.05})
    )
    monkeypatch.setattr(settings, "ENABLE_ML_INFERENCE", True)
    monkeypatch.setattr(settings, "NLP_MODEL_PATH", str(model_path))
    monkeypatch.setattr("app.routes.diagnosis.nlp_available", lambda: True)
    monkeypatch.setattr(
        "app.routes.diagnosis.classify_symptoms",
        lambda text: {
            "predictions": [
                {"label": f"fault_{index}", "score": score}
                for index, score in enumerate((0.9, 0.8, 0.7, 0.6, 0.5))
            ],
            "top_label": "fault_0",
            "confidence": 0.9,
            "analyzed": True,
        },
    )
    vague = await client.post(
        "/api/chat/",
        json={
            "message": (
                "My Venue makes a prolonged whining sound from the front "
                "while accelerating gently uphill"
            )
        },
    )
    session_id = vague.json()["session_id"]
    response = await client.post("/api/diagnosis/", json={"session_id": session_id})
    assert response.status_code == 201
    body = response.json()
    assert body["recommended_service"] == "inspection"
    assert body["ai_used"] is False
    assert "uncertain" in body["summary"].lower()


def test_magic_byte_detection_ignores_extension():
    assert detect_image_format(b"\x89PNG\r\n\x1a\n" + b"x") == "PNG"
    assert detect_image_format(b"\xff\xd8\xff\xe0" + b"x") == "JPEG"
    assert detect_image_format(b"RIFF1234WEBPVP8 ") == "WEBP"
    assert detect_image_format(b"GIF89a........") is None
