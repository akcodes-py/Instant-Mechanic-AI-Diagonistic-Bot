"""Optional DistilBERT/DeBERTa symptom classifier.

Model loading is lazy and every failure returns an empty, safe result. The app
must keep working when transformers is missing or no model path is configured.
"""
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

FAULT_LABELS = [
    "battery_electrical",
    "engine_overheating",
    "brake_system",
    "tyre_puncture",
    "fuel_system",
    "steering_suspension",
    "transmission_clutch",
    "cooling_system",
    "exhaust_emission",
    "ignition_starter",
    "key_lock_access",
    "noise_vibration",
]

SERVICE_BY_FAULT = {
    "battery_electrical": "battery_jumpstart",
    "tyre_puncture": "flat_tyre",
    "fuel_system": "fuel_delivery",
    "key_lock_access": "key_lockout",
    "engine_overheating": "towing",
}

_classifier = None
_failed_path: str | None = None


def _fallback() -> dict:
    return {
        "predictions": [],
        "top_label": "",
        "confidence": 0.0,
        "analyzed": False,
    }


def _model_path() -> str:
    return (settings.NLP_MODEL_PATH or "").strip()


def is_available() -> bool:
    path = _model_path()
    if not path:
        return False
    try:
        candidate = Path(path)
        if candidate.is_file():
            return candidate.stat().st_size > 0
        if candidate.is_dir():
            return any(candidate.iterdir())
        return False
    except OSError:
        return False


def load_classifier():
    """Lazy-load the text-classification pipeline, or return None."""
    global _classifier, _failed_path
    path = _model_path()
    if _classifier is not None:
        return _classifier
    if path == _failed_path:
        return None
    # The configured path wins. The public classify function never downloads a
    # fallback when no model path is configured (ML stays off by default).
    model_ref = path or "distilbert-base-uncased"
    if path and not is_available():
        _failed_path = path
        return None
    try:
        from transformers import pipeline

        _classifier = pipeline(
            "text-classification",
            model=model_ref,
            tokenizer=model_ref,
            top_k=None,
            truncation=True,
            max_length=512,
        )
        _failed_path = None
    except Exception as exc:  # pragma: no cover - depends on optional lib/model
        _failed_path = path or model_ref
        _classifier = None
        logger.warning("NLP model unavailable: %s", type(exc).__name__)
    return _classifier


def _normalize_label(label: str) -> str:
    # Fine-tuned checkpoints exported with generic LABEL_N names.
    if label.startswith("LABEL_") and label[6:].isdigit():
        index = int(label[6:])
        if 0 <= index < len(FAULT_LABELS):
            return FAULT_LABELS[index]
    return label


def classify_symptoms(text: str, top_k: int = 3) -> dict:
    """Classify symptom text; return a safe fallback on any failure."""
    if not is_available():
        return _fallback()
    classifier = load_classifier()
    if classifier is None:
        return _fallback()
    try:
        raw = classifier(
            (text or "")[:512],
            top_k=top_k,
            truncation=True,
            max_length=512,
        )
        if isinstance(raw, dict):
            raw = [raw]
        if raw and isinstance(raw[0], list):
            raw = raw[0]
        predictions = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            predictions.append(
                {
                    "label": _normalize_label(str(item.get("label", ""))),
                    "score": float(item.get("score", 0.0)),
                }
            )
        predictions.sort(key=lambda item: item["score"], reverse=True)
        predictions = predictions[:top_k]
        if not predictions:
            return _fallback()
        return {
            "predictions": predictions,
            "top_label": predictions[0]["label"],
            "confidence": predictions[0]["score"],
            "analyzed": True,
        }
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        logger.warning("NLP inference failed: %s", type(exc).__name__)
        return _fallback()


def map_fault_to_service(fault_label: str) -> str:
    return SERVICE_BY_FAULT.get(fault_label, "general_repair")
