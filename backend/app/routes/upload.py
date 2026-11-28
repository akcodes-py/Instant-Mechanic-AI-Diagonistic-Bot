"""POST /api/upload/ — validated media storage, never fake AI analysis."""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ChatMessage, MediaUpload
from app.routes.common import error_response
from app.security.image_sanitizer import (
    load_pil_image,
    sanitize_image_bytes,
    to_enum_observations,
    vision_context,
)
from app.security.audit_logger import client_ip_from_request, log_security_event
from app.security.middleware import api_rate_limit, limiter
from app.services.media import VISION_IMAGE_EXTS, safe_filename, validate_upload
# Kept as a monkeypatch target for the existing ML upload tests. Vision now
# runs on sanitized in-memory bytes via preprocess_image_in_memory below.
from app.services.preprocessing import (  # noqa: F401
    preprocess_for_inference,
    preprocess_image_in_memory,
)
from app.services.session_store import get_session
from app.services.vision_service import detect_warning_lights, is_reliable

logger = logging.getLogger(__name__)
router = APIRouter()

VISION_MAX_BYTES = 10 * 1024 * 1024
NO_RELIABLE_MESSAGE = (
    "No reliable warning-light detection was possible. Please upload a clearer, "
    "closer photo of the dashboard, or describe the warning light in text."
)


def _copy_file(source, destination: Path) -> None:
    with destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


def _write_bytes(data: bytes, destination: Path) -> None:
    destination.write_bytes(data)


def _reject(request: Request, status_code: int, message: str, reason: str):
    """Log an INVALID_UPLOAD event and return the usual error payload."""
    log_security_event(
        "INVALID_UPLOAD",
        client_ip=client_ip_from_request(request),
        endpoint="/api/upload/",
        status=status_code,
        detail=reason,
    )
    return error_response(status_code, message)


def _upload_size(uploaded_file) -> int:
    size = getattr(uploaded_file, "size", 0) or 0
    if size:
        return int(size)
    file_obj = getattr(uploaded_file, "file", None)
    if file_obj is None:
        return 0
    try:
        position = file_obj.tell()
        file_obj.seek(0, 2)
        size = file_obj.tell()
        file_obj.seek(position)
        return int(size)
    except Exception:
        return 0


def _normalise_detections(raw) -> list[dict]:
    """Accept the vision service list and tolerate older dict-shaped mocks."""
    if isinstance(raw, dict):
        raw = raw.get("detections") if "detections" in raw else [raw]
    if not isinstance(raw, (list, tuple)):
        return []

    detections: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        box = item.get("box", item.get("bbox", []))
        if not isinstance(box, (list, tuple)):
            box = []
        try:
            box = [float(value) for value in box]
        except (TypeError, ValueError):
            box = []
        reliable = item.get("reliable")
        if reliable is None:
            reliable = is_reliable(label, confidence)
        detections.append(
            {
                "label": label,
                "confidence": round(confidence, 3),
                "box": box,
                "reliable": bool(reliable),
            }
        )
    detections.sort(key=lambda item: item["confidence"], reverse=True)
    return detections


def _vision_payload(detections: list[dict]) -> dict:
    labels = [item["label"] for item in detections]
    reliable_labels = [item["label"] for item in detections if item["reliable"]]
    return {
        "detections": detections,
        "count": len(detections),
        "labels": labels,
        "reliable_labels": reliable_labels,
        "analyzed": bool(detections),
    }


@router.post("/upload/")
@limiter.limit(api_rate_limit)
async def upload(
    request: Request,
    session_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if session is None:
        return _reject(request, 400, "Valid session_id is required.", "unknown_session")
    if file is None:
        return _reject(request, 400, "No file provided. Use multipart field 'file'.", "missing_file")

    original_name = (file.filename or "file")[:255]
    extension = Path(original_name).suffix.lower()
    if settings.ENABLE_ML_INFERENCE and extension not in VISION_IMAGE_EXTS:
        return _reject(
            request,
            400,
            "Warning-light analysis supports JPG, JPEG, PNG, or WebP images only. "
            "Please upload a dashboard photo.",
            "extension_not_allowed",
        )
    if settings.ENABLE_ML_INFERENCE and _upload_size(file) > VISION_MAX_BYTES:
        return _reject(
            request,
            400,
            "Image too large. Warning-light photos must be 10 MB or smaller.",
            "declared_size_too_large",
        )

    try:
        kind, _ = validate_upload(file)
    except ValueError as exc:
        return _reject(request, 400, str(exc), "validation_failed")

    # Read once into memory. Images are validated by magic bytes and re-encoded
    # through Pillow so EXIF/GPS never reaches storage or inference.
    try:
        file.file.seek(0)
        raw_bytes = await run_in_threadpool(file.file.read)
    except Exception:
        logger.warning("Upload read failed", exc_info=False)
        return _reject(request, 400, "Could not read the uploaded file.", "read_failed")

    sanitized = None
    if kind == "image":
        try:
            sanitized = sanitize_image_bytes(raw_bytes)
        except ValueError as exc:
            return _reject(request, 400, str(exc), "image_sanitizer_rejected")
        payload_bytes = sanitized.data
    else:
        payload_bytes = raw_bytes

    stored_name = safe_filename(original_name)
    now = datetime.now(timezone.utc)
    relative_dir = Path("uploads") / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
    destination_dir = Path(settings.MEDIA_ROOT) / relative_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / stored_name

    try:
        await run_in_threadpool(_write_bytes, payload_bytes, destination)
    except Exception:
        logger.warning("Upload write failed", exc_info=False)
        return error_response(500, "Could not store the uploaded file.")

    size_bytes = destination.stat().st_size
    upload_row = MediaUpload(
        session_id=session.id,
        file_path=(relative_dir / stored_name).as_posix(),
        original_name=original_name,
        mime_type=(file.content_type or "")[:120],
        size_bytes=size_bytes,
        kind=kind,
        analyzed=False,
    )
    db.add(upload_row)
    await db.commit()
    await db.refresh(upload_row)

    # Media analysis: images may get an optional warning-light check. Audio/video
    # are stored, not transcribed. Never fabricate observations.
    vision_result = None
    detections: list[dict] = []
    reliable_labels: list[str] = []
    width = height = None
    if kind == "image":
        width = sanitized.width if sanitized is not None else None
        height = sanitized.height if sanitized is not None else None
        dimensions = f"{width}x{height}, "
        received = f"Image received ({dimensions}{size_bytes / 1024:.0f} KB). "

        if settings.ENABLE_ML_INFERENCE:
            inference_ran = False
            try:
                with load_pil_image(sanitized) as image:
                    processed = await run_in_threadpool(
                        preprocess_image_in_memory, image
                    )
                    # No user photo is written to disk for inference: the model
                    # receives a sanitized in-memory Pillow image only.
                    raw = await run_in_threadpool(detect_warning_lights, processed)
                detections = _normalise_detections(raw)
                inference_ran = True
            except Exception:
                logger.warning("Vision inference failed; keeping upload", exc_info=False)

            reliable_labels = [
                item["label"] for item in detections if item["reliable"]
            ]
            upload_row.analyzed = bool(detections)
            if reliable_labels:
                upload_row.analysis_note = (
                    received
                    + "Automated check detected: "
                    + ", ".join(reliable_labels)
                    + ". A mechanic will verify during inspection."
                )
            elif detections:
                upload_row.analysis_note = (
                    received
                    + "Low-confidence warning-light detections were not treated as "
                    "reliable. "
                    + NO_RELIABLE_MESSAGE
                )
            else:
                upload_row.analysis_note = received + NO_RELIABLE_MESSAGE
            if inference_ran:
                vision_result = _vision_payload(detections)
        else:
            upload_row.analysis_note = (
                received
                + "Visual content was not auto-analyzed; a mechanic will review it "
                "during inspection."
            )
            if width is None:
                upload_row.analysis_note = (
                    "Image received but could not be previewed. A mechanic will review it."
                )
    else:
        upload_row.analysis_note = (
            f"{kind.title()} file received ({size_bytes / 1048576:.1f} MB). "
            "Audio/video contents are stored for the mechanic and were not "
            "auto-transcribed by AI."
        )
    await db.commit()

    # Only reliable labels enter the chat history that feeds the existing
    # diagnosis/LLM explanation step. Safety-critical rules still run first.
    observations = to_enum_observations(detections)
    enum_context = " " + vision_context(observations) if observations else ""
    llm_context = (
        " Reliable dashboard warning lights detected: "
        + ", ".join(reliable_labels)
        + "."
        + enum_context
        if reliable_labels
        else ""
    )
    # Never put a client-supplied filename into history/prompts.
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=f"[Uploaded {kind}]{llm_context}",
            ai_used=False,
        )
    )
    await db.commit()

    return JSONResponse(
        status_code=201,
        content={
            "id": str(upload_row.id),
            "session_id": str(session.id),
            "kind": kind,
            "size_bytes": size_bytes,
            "analyzed": bool(upload_row.analyzed),
            "note": upload_row.analysis_note,
            "message": upload_row.analysis_note,
            "detections": detections,
            "reliable_labels": reliable_labels,
            "vision": vision_result,
        },
    )
