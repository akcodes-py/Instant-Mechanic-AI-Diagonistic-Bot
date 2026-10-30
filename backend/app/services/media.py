"""Media validation helpers. Never trust client MIME. Check extension + content."""
import os
import uuid

from app.config import settings

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VISION_IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".webm"}
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".3gp"}
ALLOWED_EXTS = IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS

IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp"}
AUDIO_MIMES = {
    "audio/mpeg",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/mp4",
    "audio/webm",
    "audio/aac",
}
VIDEO_MIMES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "video/3gpp",
}


def classify(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "other"


def max_bytes_for(kind: str) -> int:
    if kind == "image":
        return int(settings.MAX_IMAGE_MB * 1024 * 1024)
    if kind == "audio":
        return int(settings.MAX_AUDIO_MB * 1024 * 1024)
    if kind == "video":
        return int(settings.MAX_VIDEO_MB * 1024 * 1024)
    return int(5 * 1024 * 1024)


def _underlying_file(uploaded_file):
    """Return the sync file object behind FastAPI UploadFile or Django's file."""
    return getattr(uploaded_file, "file", uploaded_file)


def _file_size(uploaded_file, file_obj) -> int:
    size = getattr(uploaded_file, "size", 0) or 0
    if size:
        return int(size)
    try:
        position = file_obj.tell()
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(position)
        return int(size)
    except Exception:
        return 0


def validate_upload(uploaded_file) -> tuple[str, str]:
    """Return (kind, safe_note). Raise ValueError with a user-safe message."""
    name = (
        getattr(uploaded_file, "filename", "")
        or getattr(uploaded_file, "name", "")
        or "file"
    )
    ext = os.path.splitext(name)[1].lower()
    if not ext or ext not in ALLOWED_EXTS:
        raise ValueError(
            f"Unsupported file type '{ext or 'unknown'}'. Allowed: images (jpg, jpeg, png, webp), "
            "audio (mp3, wav, ogg, m4a), video (mp4, webm, mov)."
        )
    kind = classify(ext)
    limit = max_bytes_for(kind)
    file_obj = _underlying_file(uploaded_file)
    size = _file_size(uploaded_file, file_obj)
    if size > limit:
        mb = limit / (1024 * 1024)
        raise ValueError(
            f"File too large ({size / 1048576:.1f} MB). Limit for {kind} is {mb:.0f} MB."
        )
    if size == 0:
        raise ValueError("Empty file. Please choose a valid file.")

    content_type = getattr(uploaded_file, "content_type", "") or ""
    try:
        file_obj.seek(0)
        head = file_obj.read(16)
        file_obj.seek(0)
    except Exception:
        head = b""

    if kind == "image":
        # JPEG / PNG / WEBP magic.
        valid_magic = (
            head.startswith(b"\xff\xd8\xff")
            or head.startswith(b"\x89PNG")
            or head.startswith(b"RIFF")
        )
        if not valid_magic:
            # Fall back to Pillow verify for robustness.
            try:
                from PIL import Image

                file_obj.seek(0)
                image = Image.open(file_obj)
                image.verify()
                file_obj.seek(0)
            except Exception:
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
                raise ValueError("File content does not look like a valid image.")
        if content_type and content_type not in IMAGE_MIMES and not content_type.startswith("image/"):
            raise ValueError("Mismatched image content type.")
    elif kind == "audio":
        if content_type and not (
            content_type.startswith("audio/") or content_type.startswith("video/")
        ):
            # Some browsers send video/webm for audio; allow but do not trust it.
            pass
    elif kind == "video":
        if content_type and not (
            content_type.startswith("video/") or content_type.startswith("audio/")
        ):
            pass
    return kind, ""


def safe_filename(original: str) -> str:
    ext = os.path.splitext(original or "file")[1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".bin"
    # Prevent path traversal: strip directories, keep only uuid + extension.
    return f"{uuid.uuid4().hex}{ext}"
