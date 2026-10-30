"""Optional ONNX Runtime inference for INT8-quantized models.

The model path comes from settings (VISION_MODEL_PATH / NLP_MODEL_PATH). Every
failure returns a safe fallback; this module never raises into the API.
"""
import logging
import time
from pathlib import Path

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_sessions: dict[str, object] = {}
_vision_session = None
_nlp_session = None


def _fallback_vision() -> dict:
    return {"detections": [], "count": 0, "labels": [], "analyzed": False}


def load_onnx_model(path):
    """Load and cache an ONNX InferenceSession, or return None."""
    global _vision_session, _nlp_session
    try:
        key = str(path or "").strip()
        if not key:
            return None
        if key in _sessions:
            return _sessions[key]
        candidate = Path(key)
        if not candidate.is_file():
            return None
        import onnxruntime as ort

        session = ort.InferenceSession(
            str(candidate),
            providers=["CPUExecutionProvider"],
        )
        _sessions[key] = session
        if key == str(settings.VISION_MODEL_PATH or "").strip():
            _vision_session = session
        if key == str(settings.NLP_MODEL_PATH or "").strip():
            _nlp_session = session
        return session
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        logger.warning("ONNX model unavailable: %s", type(exc).__name__)
        return None


def _parse_yolo_output(outputs) -> list[dict]:
    if not outputs:
        return []
    prediction = np.asarray(outputs[0], dtype=float)
    if prediction.ndim == 3:
        prediction = prediction[0]
    if prediction.ndim != 2 or prediction.shape[1] < 5:
        return []
    # YOLOv8 commonly returns (84, 8400); also accept (8400, 84).
    if prediction.shape[0] < prediction.shape[1] and prediction.shape[0] <= 128:
        prediction = prediction.T
    if prediction.shape[1] < 5:
        return []
    class_scores = prediction[:, 4:]
    if class_scores.size == 0:
        return []
    class_ids = np.argmax(class_scores, axis=1)
    confidences = class_scores[np.arange(len(prediction)), class_ids]
    detections = []
    for index in np.where(confidences >= 0.25)[0]:
        center_x, center_y, width, height = prediction[index, :4]
        confidence = float(confidences[index])
        class_id = int(class_ids[index])
        detections.append(
            {
                "label": str(class_id),
                "confidence": round(confidence, 4),
                "bbox": [
                    round(float(center_x - width / 2), 2),
                    round(float(center_y - height / 2), 2),
                    round(float(center_x + width / 2), 2),
                    round(float(center_y + height / 2), 2),
                ],
            }
        )
    return detections


def run_vision_onnx(image_path) -> dict:
    """Run the ONNX vision model on an image; safe fallback on any failure."""
    try:
        path = Path(image_path)
        if not path.is_file():
            return _fallback_vision()
        session = load_onnx_model(settings.VISION_MODEL_PATH)
        if session is None:
            return _fallback_vision()

        import cv2

        image = cv2.imread(str(path))
        if image is None:
            return _fallback_vision()
        image = cv2.resize(image, (640, 640))
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        blob = image.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[None, ...]
        input_name = session.get_inputs()[0].name
        outputs = session.run(None, {input_name: blob})
        detections = _parse_yolo_output(outputs)
        return {
            "detections": detections,
            "count": len(detections),
            "labels": [item["label"] for item in detections],
            "analyzed": True,
        }
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        logger.warning("ONNX vision inference failed: %s", type(exc).__name__)
        return _fallback_vision()


def run_nlp_onnx(text: str, tokenizer) -> np.ndarray:
    """Run the ONNX NLP model; return an empty array on any failure."""
    try:
        if tokenizer is None:
            return np.array([])
        session = load_onnx_model(settings.NLP_MODEL_PATH)
        if session is None:
            return np.array([])
        encoded = tokenizer(
            (text or "")[:512],
            return_tensors="np",
            truncation=True,
            padding=True,
            max_length=512,
        )
        feed = {}
        for model_input in session.get_inputs():
            if model_input.name in encoded:
                feed[model_input.name] = np.asarray(encoded[model_input.name])
        if not feed:
            return np.array([])
        outputs = session.run(None, feed)
        return np.asarray(outputs[0]) if outputs else np.array([])
    except Exception as exc:  # pragma: no cover - depends on optional model/lib
        logger.warning("ONNX NLP inference failed: %s", type(exc).__name__)
        return np.array([])


def get_inference_time_ms(func, *args) -> float:
    """Return elapsed milliseconds, or 0.0 if the callable fails."""
    started = time.perf_counter()
    try:
        func(*args)
        return (time.perf_counter() - started) * 1000.0
    except Exception:
        return 0.0
