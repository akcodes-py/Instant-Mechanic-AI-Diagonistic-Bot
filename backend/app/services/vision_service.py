"""Optional Ultralytics YOLO dashboard warning-light detection.

The model is loaded once, lazily, and every load/inference failure returns an
empty list. This module must remain importable when ultralytics/torch/opencv are
not installed, so all heavy imports stay inside the functions.
"""
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_RELIABLE_THRESHOLD = 0.40
WEAK_CLASS_THRESHOLD = 0.50

# These classes had lower validation recall in the trained detector. Require a
# higher confidence before treating them as reliable. Labels are read from the
# loaded model; these markers only choose the confidence gate.
_WEAK_CLASS_MARKERS = (
    "electronic stability",
    "esp",
    "check engine",
    "low engine oil",
)

_model = None
_loaded_path: str | None = None
_failed_path: str | None = None


def reset_model_cache() -> None:
    """Drop the cached model (used by tests and after a configuration change)."""
    global _model, _loaded_path, _failed_path
    _model = None
    _loaded_path = None
    _failed_path = None


def _model_path() -> str:
    return (settings.VISION_MODEL_PATH or "").strip()


def _resolve_model_path() -> Path | None:
    raw = _model_path()
    if not raw:
        return None
    try:
        p = Path(raw)
        if p.is_file() and p.stat().st_size > 0:
            return p
        backend_dir = Path(__file__).resolve().parents[2]
        repo_root = backend_dir.parent
        for base in (backend_dir, repo_root):
            cand = base / raw
            if cand.is_file() and cand.stat().st_size > 0:
                return cand
    except OSError:
        pass
    return None


def is_available() -> bool:
    """Return True only when a non-empty model file is configured."""
    return _resolve_model_path() is not None


def load_model():
    """Lazy-load and cache the YOLO model, or return None on any failure."""
    global _model, _loaded_path, _failed_path
    resolved = _resolve_model_path()
    if resolved is None:
        return None

    path_str = str(resolved.resolve())
    if _model is not None and (_loaded_path == path_str or _loaded_path is None):
        return _model
    if _model is not None and _loaded_path != path_str:
        _model = None
        _loaded_path = None

    if path_str == _failed_path:
        return None

    try:
        from ultralytics import YOLO

        _model = YOLO(path_str)
        _loaded_path = path_str
        _failed_path = None
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        _model = None
        _loaded_path = None
        _failed_path = path_str
        # Do not log the path, weights, or raw exception text.
        logger.error("Vision model load failed: %s", type(exc).__name__)
    return _model


def reliable_threshold_for(label: str) -> float:
    """Return the confidence gate for a model-provided class label."""
    text = (label or "").lower()
    if any(marker in text for marker in _WEAK_CLASS_MARKERS):
        return WEAK_CLASS_THRESHOLD
    return DEFAULT_RELIABLE_THRESHOLD


def is_reliable(label: str, confidence: float) -> bool:
    """Apply the per-class confidence gate (inclusive)."""
    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return False
    return value >= reliable_threshold_for(label)


def _number(value, default: float = 0.0) -> float:
    try:
        if hasattr(value, "item"):
            value = value.item()
        return float(value)
    except Exception:
        return default


def _label_for(names, class_id: int) -> str:
    try:
        if isinstance(names, dict):
            return str(names.get(class_id, class_id))
        if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
            return str(names[class_id])
    except Exception:
        pass
    return str(class_id)


def _coordinates(value) -> list[float]:
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        single = _number(value)
        return [single, single, single, single]


def detect_warning_lights(image_path: str | Path) -> list[dict]:
    """Run YOLO inference and return detections sorted by confidence.

    Each detection contains ``label``, ``confidence`` (3 decimals), ``box``
    (x1, y1, x2, y2) and ``reliable``. A missing model, missing image, or any
    model/inference error returns an empty list rather than raising into the
    upload request.
    """
    model = load_model()
    if model is None:
        return []

    try:
        path = Path(image_path)
        exists = path.is_file()
    except (TypeError, ValueError, OSError):
        logger.error("Vision inference skipped: invalid input path")
        return []
    if not exists:
        logger.error("Vision inference skipped: input file not found")
        return []

    try:
        results = model.predict(
            source=str(path),
            conf=settings.VISION_CONF,
            imgsz=settings.VISION_IMGSZ,
            iou=0.5,
            verbose=False,
        )
        names = getattr(model, "names", {}) or {}
        detections: list[dict] = []
        for result in results or []:
            result_names = getattr(result, "names", None) or names
            boxes = getattr(result, "boxes", None)
            if boxes is None:
                continue
            for index in range(len(boxes)):
                box = boxes[index]
                class_id = int(_number(box.cls[0]))
                confidence = _number(box.conf[0])
                label = _label_for(result_names, class_id)
                detections.append(
                    {
                        "label": label,
                        "confidence": round(confidence, 3),
                        "box": _coordinates(box.xyxy[0]),
                        "reliable": is_reliable(label, confidence),
                    }
                )
        detections.sort(key=lambda item: item["confidence"], reverse=True)
        return detections
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        # Do not log the path, weights, or raw exception text.
        logger.error("Vision inference failed: %s", type(exc).__name__)
        return []
