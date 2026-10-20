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
from app.services.media import safe_filename, validate_upload
from app.services.session_store import get_session

logger = logging.getLogger(__name__)
router = APIRouter()


def _copy_file(source, destination: Path) -> None:
    with destination.open("wb") as target:
        shutil.copyfileobj(source, target, length=1024 * 1024)


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

    try:
        kind, _ = validate_upload(file)
    except ValueError as exc:
        return error_response(400, str(exc))

    original_name = (file.filename or "file")[:255]
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

    # Media analysis: only images get a lightweight note. Audio/video are stored,
    # not transcribed. Never fabricate observations.
    if kind == "image":
        try:
            from PIL import Image

            with Image.open(destination) as image:
                width, height = image.size
            upload_row.analysis_note = (
                f"Image received ({width}x{height}, {size_bytes / 1024:.0f} KB). "
                "Visual content was not auto-analyzed; a mechanic will review it "
                "during inspection."
            )
        except Exception:
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

    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=f"[Uploaded {kind}: {upload_row.original_name}]",
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
        },
    )
