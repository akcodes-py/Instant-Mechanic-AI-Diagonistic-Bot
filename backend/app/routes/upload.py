"""POST /api/upload/ — validated media storage, never fake AI analysis."""
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import ChatMessage, MediaUpload
from app.routes.common import error_response
from app.services.media import VISION_IMAGE_EXTS, safe_filename, validate_upload
from app.services.preprocessing import preprocess_for_inference
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
async def upload(
    session_id: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    session = await get_session(db, session_id)
    if session is None:
        return error_response(400, "Valid session_id is required.")
    if file is None:
        return error_response(400, "No file provided. Use multipart field 'file'.")

    original_name = (file.filename or "file")[:255]
    extension = Path(original_name).suffix.lower()
    if settings.ENABLE_ML_INFERENCE and extension not in VISION_IMAGE_EXTS:
        return error_response(
            400,
            "Warning-light analysis supports JPG, JPEG, PNG, or WebP images only. "
            "Please upload a dashboard photo.",
        )
    if settings.ENABLE_ML_INFERENCE and _upload_size(file) > VISION_MAX_BYTES:
        return error_response(
            400,
            "Image too large. Warning-light photos must be 10 MB or smaller.",
        )

    try:
        kind, _ = validate_upload(file)
    except ValueError as exc:
        return error_response(400, str(exc))

    stored_name = safe_filename(original_name)
    now = datetime.now(timezone.utc)
    relative_dir = Path("uploads") / f"{now:%Y}" / f"{now:%m}" / f"{now:%d}"
    destination_dir = Path(settings.MEDIA_ROOT) / relative_dir
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / stored_name

    try:
        file.file.seek(0)
        await run_in_threadpool(_copy_file, file.file, destination)
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
        try:
            from PIL import Image

            with Image.open(destination) as image:
                width, height = image.size
        except Exception:
            pass

        dimensions = (
            f"{width}x{height}, " if width is not None and height is not None else ""
        )
        received = f"Image received ({dimensions}{size_bytes / 1024:.0f} KB). "

        if settings.ENABLE_ML_INFERENCE:
            inference_ran = False
            try:
                processed_path = await run_in_threadpool(
                    preprocess_for_inference, destination
                )
                raw = await run_in_threadpool(detect_warning_lights, processed_path)
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
    llm_context = (
        " Reliable dashboard warning lights detected: "
        + ", ".join(reliable_labels)
        + "."
        if reliable_labels
        else ""
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=f"[Uploaded {kind}: {upload_row.original_name}]{llm_context}",
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
