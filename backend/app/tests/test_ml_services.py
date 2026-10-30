"""ML service tests. No model files or live inference calls are required."""
import logging
import sys
import types
from pathlib import Path

import numpy as np
import pytest

from app.config import settings
from app.services import (
    calibration,
    nlp_service,
    onnx_service,
    preprocessing,
    vision_service,
)

WEIGHTS_PATH = (
    Path(__file__).resolve().parents[2] / "models" / "dashboard_lights.pt"
)


class _Box:
    def __init__(self, class_id, confidence, box):
        self.cls = [class_id]
        self.conf = [confidence]
        self.xyxy = [box]


class _Boxes:
    def __init__(self, boxes):
        self._boxes = list(boxes)

    def __len__(self):
        return len(self._boxes)

    def __getitem__(self, index):
        return self._boxes[index]


class _Result:
    def __init__(self, names, boxes):
        self.names = names
        self.boxes = _Boxes(boxes)


class _FakeModel:
    names: dict = {}

    def __init__(self, names, boxes, error=None):
        self.names = names
        self._boxes = boxes
        self._error = error
        self.calls: list[dict] = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return [_Result(self.names, self._boxes)]


@pytest.fixture(autouse=True)
def _clear_vision_cache():
    vision_service.reset_model_cache()
    yield
    vision_service.reset_model_cache()


def _image(tmp_path):
    path = tmp_path / "dashboard.jpg"
    path.write_bytes(b"fake-image-bytes")
    return path


def test_vision_not_available_when_no_model(monkeypatch):
    monkeypatch.setattr(settings, "VISION_MODEL_PATH", "")
    assert vision_service.is_available() is False


def test_detect_returns_safe_fallback(monkeypatch):
    monkeypatch.setattr(settings, "VISION_MODEL_PATH", "")
    assert vision_service.detect_warning_lights("missing.jpg") == []


def test_reliable_thresholds_are_class_specific():
    assert vision_service.reliable_threshold_for("Braking System Issue") == 0.40
    assert vision_service.reliable_threshold_for("SRS-Airbag") == 0.40
    assert vision_service.reliable_threshold_for("Check Engine") == 0.50
    assert vision_service.reliable_threshold_for("Electronic Stability Problem -ESP-") == 0.50
    assert vision_service.reliable_threshold_for("Low Engine Oil Warning Light") == 0.50
    assert vision_service.is_reliable("Braking System Issue", 0.40) is True
    assert vision_service.is_reliable("Check Engine", 0.49) is False
    assert vision_service.is_reliable("Check Engine", 0.50) is True


def test_detect_sorts_and_marks_reliable(monkeypatch, tmp_path):
    names = {
        0: "Check Engine",
        1: "Braking System Issue",
        2: "Electronic Stability Problem -ESP-",
        3: "Low Engine Oil Warning Light",
        4: "SRS-Airbag",
        5: "Master warning light",
    }
    model = _FakeModel(
        names,
        [
            _Box(2, 0.62, [1.0, 2.0, 3.0, 4.0]),
            _Box(0, 0.7104, [5.0, 6.0, 7.0, 8.0]),
            _Box(3, 0.49, [9.0, 10.0, 11.0, 12.0]),
            _Box(1, 0.45, [13.0, 14.0, 15.0, 16.0]),
            _Box(4, 0.39, [17.0, 18.0, 19.0, 20.0]),
            _Box(5, 0.40, [21.0, 22.0, 23.0, 24.0]),
        ],
    )
    monkeypatch.setattr(vision_service, "load_model", lambda: model)

    result = vision_service.detect_warning_lights(_image(tmp_path))

    assert [item["label"] for item in result] == [
        "Check Engine",
        "Electronic Stability Problem -ESP-",
        "Low Engine Oil Warning Light",
        "Braking System Issue",
        "Master warning light",
        "SRS-Airbag",
    ]
    assert [item["confidence"] for item in result] == [
        0.71,
        0.62,
        0.49,
        0.45,
        0.40,
        0.39,
    ]
    reliable = {item["label"]: item["reliable"] for item in result}
    assert reliable["Check Engine"] is True
    assert reliable["Electronic Stability Problem -ESP-"] is True
    assert reliable["Low Engine Oil Warning Light"] is False
    assert reliable["Braking System Issue"] is True
    assert reliable["Master warning light"] is True
    assert reliable["SRS-Airbag"] is False
    assert result[0]["box"] == [5.0, 6.0, 7.0, 8.0]
    assert model.calls == [
        {
            "source": str(tmp_path / "dashboard.jpg"),
            "conf": settings.VISION_CONF,
            "imgsz": settings.VISION_IMGSZ,
            "iou": 0.5,
            "verbose": False,
        }
    ]


def test_detect_unreliable_weak_classes(monkeypatch, tmp_path):
    model = _FakeModel(
        {0: "Check Engine", 1: "Low Engine Oil Warning Light", 2: "Braking System Issue"},
        [
            _Box(0, 0.49, [1, 2, 3, 4]),
            _Box(1, 0.49, [5, 6, 7, 8]),
            _Box(2, 0.39, [9, 10, 11, 12]),
        ],
    )
    monkeypatch.setattr(vision_service, "load_model", lambda: model)

    result = vision_service.detect_warning_lights(_image(tmp_path))

    assert len(result) == 3
    assert all(item["reliable"] is False for item in result)


def test_detect_empty_result(monkeypatch, tmp_path):
    model = _FakeModel({}, [])
    monkeypatch.setattr(vision_service, "load_model", lambda: model)

    assert vision_service.detect_warning_lights(_image(tmp_path)) == []


def test_detect_inference_exception_returns_empty(monkeypatch, tmp_path, caplog):
    model = _FakeModel({}, [], error=RuntimeError("model exploded"))
    monkeypatch.setattr(vision_service, "load_model", lambda: model)

    with caplog.at_level(logging.ERROR):
        assert vision_service.detect_warning_lights(_image(tmp_path)) == []

    assert "Vision inference failed" in caplog.text


def test_model_is_loaded_once(monkeypatch, tmp_path):
    weights = tmp_path / "dashboard_lights.pt"
    weights.write_bytes(b"weights")
    calls = []

    class FakeYOLO:
        def __init__(self, path):
            calls.append(path)

    module = types.ModuleType("ultralytics")
    module.YOLO = FakeYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    monkeypatch.setattr(settings, "VISION_MODEL_PATH", str(weights))

    assert vision_service.load_model() is not None
    assert vision_service.load_model() is not None
    assert calls == [str(weights)]


def test_model_load_exception_returns_none(monkeypatch, tmp_path, caplog):
    weights = tmp_path / "dashboard_lights.pt"
    weights.write_bytes(b"weights")

    class BrokenYOLO:
        def __init__(self, path):
            raise RuntimeError("bad weights")

    module = types.ModuleType("ultralytics")
    module.YOLO = BrokenYOLO
    monkeypatch.setitem(sys.modules, "ultralytics", module)
    monkeypatch.setattr(settings, "VISION_MODEL_PATH", str(weights))

    with caplog.at_level(logging.ERROR):
        assert vision_service.load_model() is None

    assert "Vision model load failed" in caplog.text


@pytest.mark.skipif(
    not WEIGHTS_PATH.is_file(), reason="dashboard_lights.pt weights are not present"
)
def test_optional_dashboard_weights_integration(tmp_path, monkeypatch):
    pytest.importorskip("ultralytics")
    from PIL import Image

    image_path = tmp_path / "dashboard.png"
    Image.new("RGB", (640, 480), (25, 25, 25)).save(image_path)
    monkeypatch.setattr(settings, "VISION_MODEL_PATH", str(WEIGHTS_PATH))

    result = vision_service.detect_warning_lights(image_path)

    assert isinstance(result, list)
    for detection in result:
        assert {"label", "confidence", "box", "reliable"} <= set(detection)
        assert detection["confidence"] == round(detection["confidence"], 3)


def test_nlp_not_available_when_no_model(monkeypatch):
    monkeypatch.setattr(settings, "NLP_MODEL_PATH", "")
    assert nlp_service.is_available() is False


def test_classify_returns_safe_fallback(monkeypatch):
    monkeypatch.setattr(settings, "NLP_MODEL_PATH", "")
    assert nlp_service.classify_symptoms("engine overheating") == {
        "predictions": [],
        "top_label": "",
        "confidence": 0.0,
        "analyzed": False,
    }


def test_map_fault_to_service():
    assert nlp_service.map_fault_to_service("battery_electrical") == "battery_jumpstart"
    assert nlp_service.map_fault_to_service("tyre_puncture") == "flat_tyre"
    assert nlp_service.map_fault_to_service("fuel_system") == "fuel_delivery"
    assert nlp_service.map_fault_to_service("key_lock_access") == "key_lockout"
    assert nlp_service.map_fault_to_service("engine_overheating") == "towing"
    assert nlp_service.map_fault_to_service("brake_system") == "general_repair"
    assert nlp_service.map_fault_to_service("unknown_fault") == "general_repair"


def test_preprocess_returns_original_on_missing():
    assert preprocessing.preprocess_for_inference("missing.jpg") == "missing.jpg"


def test_is_low_quality_false_on_missing():
    assert preprocessing.is_low_quality("missing.jpg") is False


def test_temperature_scaler_scale():
    scaler = calibration.TemperatureScaler(1.5)
    scaled = scaler.scale([1.0, 2.0, 3.0])
    assert np.allclose(scaled, np.array([1.0, 2.0, 3.0]) / 1.5)


def test_conformal_predictor():
    rng = np.random.default_rng(0)
    scores = rng.random(100)
    labels = [f"label_{index % 5}" for index in range(100)]
    predictor = calibration.ConformalPredictor(alpha=0.05)
    predictor.calibrate(scores, labels)
    result = predictor.predict_set(np.array([0.1, 0.5, 0.9]), ["a", "b", "c"])
    assert {
        "prediction_set",
        "set_size",
        "q_hat",
        "coverage_guarantee",
        "confident",
    } <= set(result)
    assert result["set_size"] == len(result["prediction_set"])
    assert result["coverage_guarantee"] == pytest.approx(0.95)


def test_route_deterministic():
    payload = {"summary": "ml result"}
    assert calibration.route_prediction({"set_size": 1}, payload, "history") == (
        payload,
        "deterministic",
    )


def test_route_escalate():
    payload = {"summary": "ml result"}
    assert calibration.route_prediction({"set_size": 4}, payload, "history") == (
        None,
        "escalate_to_llm",
    )


def test_load_calibration_missing(tmp_path):
    assert calibration.load_calibration_params(tmp_path / "missing.json") is None


def test_onnx_vision_fallback():
    assert onnx_service.run_vision_onnx("missing.jpg") == {
        "detections": [],
        "count": 0,
        "labels": [],
        "analyzed": False,
    }


def test_onnx_nlp_fallback():
    result = onnx_service.run_nlp_onnx("engine noise", None)
    assert isinstance(result, np.ndarray)
    assert result.size == 0
