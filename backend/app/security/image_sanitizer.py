"""In-memory image validation, EXIF/GPS stripping and enum-only vision handoff.

Uploaded photos are untrusted input. This module validates magic bytes (never
the file extension or client MIME), enforces the 5 MB vision cap, re-encodes the
image through Pillow into ``BytesIO`` so EXIF/GPS metadata is discarded, and
converts raw detector labels into a strict enum + numeric confidence before
anything can reach an LLM prompt.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass
from enum import Enum

from PIL import Image, UnidentifiedImageError

from app.config import settings

MAX_VISION_BYTES = int(settings.MAX_VISION_IMAGE_MB * 1024 * 1024)


class ImageSanitizerError(ValueError):
    """User-safe rejection reason for an untrusted image."""


@dataclass(frozen=True)
class SanitizedImage:
    data: bytes
    format: str
    width: int
    height: int

    @property
    def size_bytes(self) -> int:
        return len(self.data)


class VisionLabel(str, Enum):
    """The only label values allowed to cross into an LLM prompt."""

    BRAKE_FAILURE = "brake_failure"
    OIL_PRESSURE = "oil_pressure"
    ENGINE_OVERHEAT = "engine_overheat"
    AIRBAG_ABS = "airbag_abs"
    CHECK_ENGINE = "check_engine"
    BATTERY = "battery"
    FLAT_TYRE = "flat_tyre"
    ELECTRONIC_STABILITY = "electronic_stability"
    FUEL = "fuel"
    OTHER_KNOWN = "other_known"


CRITICAL_VISION_LABELS = frozenset(
    {
        VisionLabel.BRAKE_FAILURE,
        VisionLabel.OIL_PRESSURE,
        VisionLabel.ENGINE_OVERHEAT,
        VisionLabel.AIRBAG_ABS,
    }
)

# Keyword -> canonical enum. Model class names are read from the weights and
# are never trusted verbatim; anything unmappable is discarded from LLM context.
_LABEL_RULES: tuple[tuple[re.Pattern[str], VisionLabel], ...] = (
    (re.compile(r"brak|abs.{0,6}(fail|fault)|brake.?fluid", re.I), VisionLabel.BRAKE_FAILURE),
    (re.compile(r"oil|lubric", re.I), VisionLabel.OIL_PRESSURE),
    (re.compile(r"overheat|temperat|coolant|radiator|thermostat", re.I), VisionLabel.ENGINE_OVERHEAT),
    (re.compile(r"airbag|srs|\babs\b|supplemental", re.I), VisionLabel.AIRBAG_ABS),
    (re.compile(r"check.?engine|engine.?check", re.I), VisionLabel.CHECK_ENGINE),
    (re.compile(r"battery|alternator|charging|volt", re.I), VisionLabel.BATTERY),
    (re.compile(r"tyre|tire|puncture|flat|pressure", re.I), VisionLabel.FLAT_TYRE),
    (re.compile(r"stabil|esp|traction|esc", re.I), VisionLabel.ELECTRONIC_STABILITY),
    (re.compile(r"fuel|petrol|diesel|gas.?station", re.I), VisionLabel.FUEL),
)

_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "JPEG"),
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"RIFF", "WEBP"),
)


def detect_image_format(data: bytes) -> str | None:
    """Return JPEG/PNG/WEBP from magic bytes only."""
    head = (data or b"")[:16]
    for magic, fmt in _MAGIC:
        if head.startswith(magic):
            if fmt == "WEBP" and head[8:12] != b"WEBP":
                return None
            return fmt
    return None


def sanitize_image_bytes(data: bytes, *, max_bytes: int | None = None) -> SanitizedImage:
    """Validate and re-encode an image entirely in memory.

    The returned bytes contain no EXIF/GPS/IPTC/XMP metadata. Failure always
    raises ``ImageSanitizerError`` with a message that is safe to return to a
    client (no filesystem paths, no decoder internals).
    """
    limit = max_bytes or MAX_VISION_BYTES
    if not data:
        raise ImageSanitizerError("Empty image. Please choose a valid photo.")
    if len(data) > limit:
        raise ImageSanitizerError(
            f"Image too large. Limit is {limit // (1024 * 1024)} MB."
        )
    fmt = detect_image_format(data)
    if fmt is None:
        raise ImageSanitizerError(
            "Invalid image content. Only JPEG, PNG and WebP photos are accepted."
        )
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()  # force decode now, while the bytes are still in RAM
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ImageSanitizerError("Invalid image dimensions.")
            buffer = io.BytesIO()
            # Saving without an ``exif`` argument drops EXIF/GPS; Pillow also
            # drops IPTC/XMP because no encoderinfo is supplied.
            image.convert("RGB" if fmt == "JPEG" else image.mode).save(
                buffer, format=fmt
            )
            clean = buffer.getvalue()
    except ImageSanitizerError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ImageSanitizerError("File content does not look like a valid image.") from exc
    return SanitizedImage(clean, fmt, width, height)


def load_pil_image(sanitized: SanitizedImage) -> Image.Image:
    """Open the sanitized bytes for in-RAM inference (caller closes it)."""
    return Image.open(io.BytesIO(sanitized.data))


def map_label(raw_label: str) -> VisionLabel | None:
    """Map an untrusted detector label to a canonical enum, or None."""
    text = (raw_label or "").strip()
    if not text or len(text) > 120:
        return None
    for pattern, label in _LABEL_RULES:
        if pattern.search(text):
            return label
    return None


@dataclass(frozen=True)
class VisionObservation:
    warning_light_id: VisionLabel
    confidence: float

    def as_context(self) -> str:
        return f"{self.warning_light_id.value}:{self.confidence:.3f}"


def to_enum_observations(detections: list[dict], *, min_confidence: float = 0.0) -> list[VisionObservation]:
    """Convert raw detections to enum-only, numeric-confidence observations.

    Unknown labels, non-finite confidences and free text (filenames, OCR) are
    dropped. This is the strict vision -> LLM boundary.
    """
    observations: list[VisionObservation] = []
    for item in detections or ():
        if not isinstance(item, dict):
            continue
        if not item.get("reliable", False):
            continue
        label = map_label(str(item.get("label") or ""))
        if label is None:
            continue
        try:
            confidence = float(item.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue
        if not 0.0 <= confidence <= 1.0 or confidence < min_confidence:
            continue
        observations.append(VisionObservation(label, round(confidence, 3)))
    observations.sort(key=lambda item: item.confidence, reverse=True)
    return observations


def vision_context(observations: list[VisionObservation]) -> str:
    """Render a compact, enum-only string for prompt construction."""
    if not observations:
        return ""
    return "warning_light_id=" + ";".join(item.as_context() for item in observations)
