"""Temperature scaling and split conformal prediction utilities.

These are pure NumPy/SciPy helpers; no torch or model files are required. Every
public function degrades gracefully instead of raising into the request path.
"""
import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / np.sum(exp, axis=1, keepdims=True)


def expected_calibration_error(probabilities, labels) -> float:
    """Expected Calibration Error with 10 confidence bins."""
    try:
        probs = np.asarray(probabilities, dtype=float)
        labels = np.asarray(labels)
        if probs.ndim != 2 or len(probs) == 0:
            return 0.0
        confidences = np.max(probs, axis=1)
        predictions = np.argmax(probs, axis=1)
        correct = predictions == labels
        total = len(probs)
        ece = 0.0
        boundaries = np.linspace(0.0, 1.0, 11)
        for index in range(10):
            lower, upper = boundaries[index], boundaries[index + 1]
            if index == 9:
                mask = (confidences >= lower) & (confidences <= upper)
            else:
                mask = (confidences >= lower) & (confidences < upper)
            count = int(np.sum(mask))
            if count == 0:
                continue
            accuracy = float(np.mean(correct[mask]))
            confidence = float(np.mean(confidences[mask]))
            ece += (count / total) * abs(accuracy - confidence)
        return float(ece)
    except Exception:
        return 0.0


class TemperatureScaler:
    """Single-parameter temperature scaling fitted by NLL minimization."""

    def __init__(self, temperature: float = 1.0):
        try:
            value = float(temperature)
        except (TypeError, ValueError):
            value = 1.0
        self.temperature = value if value > 0 else 1.0
        self._probabilities: np.ndarray | None = None
        self._label_indices: np.ndarray | None = None

    def scale(self, logits) -> np.ndarray:
        return np.asarray(logits, dtype=float) / self.temperature

    def calibrate(self, logits, labels) -> None:
        """Fit T on logits with integer or string labels."""
        try:
            from scipy.optimize import minimize_scalar

            values = np.asarray(logits, dtype=float)
            if values.ndim == 1:
                values = values.reshape(-1, 1)
            if values.ndim != 2 or len(values) == 0:
                return

            raw_labels = list(labels)
            if not raw_labels:
                return
            if isinstance(raw_labels[0], str):
                ordered = sorted(set(raw_labels))
                mapping = {label: index for index, label in enumerate(ordered)}
                indices = np.asarray([mapping[label] for label in raw_labels], dtype=int)
            else:
                indices = np.asarray(raw_labels, dtype=int)

            if np.max(indices) >= values.shape[1]:
                return

            def negative_log_likelihood(temperature: float) -> float:
                probs = _softmax(values / max(float(temperature), 1e-6))
                true_probs = probs[np.arange(len(values)), indices]
                return float(-np.mean(np.log(np.clip(true_probs, 1e-12, 1.0))))

            result = minimize_scalar(
                negative_log_likelihood,
                bounds=(0.1, 10.0),
                method="bounded",
            )
            if result.success:
                self.temperature = float(result.x)
            self._probabilities = _softmax(values / self.temperature)
            self._label_indices = indices
        except Exception as exc:  # pragma: no cover - numerical guard
            logger.warning("Temperature calibration failed: %s", type(exc).__name__)

    @property
    def ece(self) -> float:
        if self._probabilities is None or self._label_indices is None:
            return 0.0
        return expected_calibration_error(self._probabilities, self._label_indices)


class ConformalPredictor:
    """Split-conformal prediction with a finite-sample quantile."""

    def __init__(self, alpha: float = 0.05):
        try:
            value = float(alpha)
        except (TypeError, ValueError):
            value = 0.05
        self.alpha = min(max(value, 0.001), 0.999)
        self.q_hat: float | None = None

    def calibrate(self, scores, labels=None) -> None:
        try:
            values = np.asarray(scores, dtype=float).ravel()
            if len(values) == 0:
                return
            quantile = min(1.0, (1.0 - self.alpha) * (1.0 + 1.0 / len(values)))
            self.q_hat = float(np.quantile(values, quantile))
        except Exception as exc:  # pragma: no cover - numerical guard
            logger.warning("Conformal calibration failed: %s", type(exc).__name__)
            self.q_hat = None

    def predict_set(self, scores, labels: list[str]) -> dict:
        try:
            values = np.asarray(scores, dtype=float).ravel()
            names = [str(label) for label in labels]
            if self.q_hat is None:
                prediction_set = names
            else:
                prediction_set = [
                    name for name, score in zip(names, values) if score <= self.q_hat
                ]
                if not prediction_set and names:
                    prediction_set = [names[int(np.argmin(values))]]
            set_size = len(prediction_set)
            return {
                "prediction_set": prediction_set,
                "set_size": set_size,
                "q_hat": self.q_hat,
                "coverage_guarantee": 1.0 - self.alpha,
                "confident": set_size <= 2,
            }
        except Exception:
            return {
                "prediction_set": [],
                "set_size": 0,
                "q_hat": self.q_hat,
                "coverage_guarantee": 1.0 - self.alpha,
                "confident": False,
            }


def load_calibration_params(path) -> tuple[float, float, float] | None:
    """Load {"temperature", "q_hat", "alpha"} from JSON, or None."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return (
            float(data["temperature"]),
            float(data["q_hat"]),
            float(data["alpha"]),
        )
    except Exception:
        return None


def route_prediction(pred_set, ml_diagnosis, history) -> tuple[dict | None, str]:
    """Route a conformal set: <=2 labels use ML, otherwise escalate to Groq."""
    try:
        set_size = int(pred_set.get("set_size", 0))
        if set_size == 1:
            return ml_diagnosis, "deterministic"
        if set_size == 2:
            return ml_diagnosis, "ml_assisted"
        return None, "escalate_to_llm"
    except Exception:
        return None, "escalate_to_llm"
