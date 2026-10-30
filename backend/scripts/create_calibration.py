"""Fit temperature scaling + split conformal prediction for the NLP classifier.

Standalone script; never imported by the web app. Requires a configured
NLP_MODEL_PATH and a labelled CSV.

Usage (from the repo root):
    python backend/scripts/create_calibration.py labelled.csv -o calibration.json
"""
import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import nlp_service  # noqa: E402
from app.services.calibration import (  # noqa: E402
    ConformalPredictor,
    TemperatureScaler,
    expected_calibration_error,
)

TEXT_COLUMNS = ("text", "complaint_text", "description", "symptom")
LABEL_COLUMNS = ("true_label", "label", "component", "fault")


def _softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - np.max(logits, axis=1, keepdims=True)
    values = np.exp(shifted)
    return values / np.sum(values, axis=1, keepdims=True)


def _field(fieldnames, candidates) -> str | None:
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
    return None


def _normalise_scores(raw) -> dict[str, float]:
    if isinstance(raw, dict):
        raw = [raw]
    if raw and isinstance(raw[0], list):
        raw = raw[0]
    result = {}
    for item in raw or []:
        if isinstance(item, dict):
            result[str(item.get("label", ""))] = float(item.get("score", 0.0))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Labelled CSV")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("calibration.json"),
        help="Output JSON (default: calibration.json)",
    )
    parser.add_argument("--alpha", type=float, default=0.05, help="Miscoverage rate")
    parser.add_argument("--test-size", type=float, default=0.3, help="Test fraction")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--text-column", default=None)
    parser.add_argument("--label-column", default=None)
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"Input CSV not found: {args.input}", file=sys.stderr)
        return 2
    if not nlp_service.is_available():
        print("NLP_MODEL_PATH must point to a local model directory/file.", file=sys.stderr)
        return 2

    with args.input.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        fieldnames = reader.fieldnames or []
        text_column = args.text_column or _field(fieldnames, TEXT_COLUMNS)
        label_column = args.label_column or _field(fieldnames, LABEL_COLUMNS)
        if text_column is None or label_column is None:
            print("CSV needs a text column and a label column.", file=sys.stderr)
            return 2
        rows = [
            (
                (row.get(text_column) or "").strip(),
                (row.get(label_column) or "").strip(),
            )
            for row in reader
        ]
    rows = [(text, label) for text, label in rows if text and label]
    if len(rows) < 10:
        print("At least 10 labelled rows are required.", file=sys.stderr)
        return 2

    classifier = nlp_service.load_classifier()
    if classifier is None:
        print("Could not load the NLP classifier.", file=sys.stderr)
        return 2

    raw_scores = []
    for text, _ in rows:
        try:
            raw = classifier(
                text[:512],
                top_k=None,
                truncation=True,
                max_length=512,
            )
            raw_scores.append(_normalise_scores(raw))
        except Exception as exc:
            print(f"Classifier failed on one row: {type(exc).__name__}", file=sys.stderr)
            return 2

    labels = sorted({label for mapping in raw_scores for label in mapping})
    labels += sorted({label for _, label in rows if label not in labels})
    label_index = {label: index for index, label in enumerate(labels)}
    # The HF pipeline exposes softmax scores; log them as a stable logit surrogate.
    logits = np.log(
        np.clip(
            np.asarray(
                [
                    [mapping.get(label, 1e-9) for label in labels]
                    for mapping in raw_scores
                ],
                dtype=float,
            ),
            1e-9,
            1.0,
        )
    )
    true_indices = np.asarray([label_index[label] for _, label in rows], dtype=int)

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(rows))
    split = max(1, int(len(rows) * (1.0 - args.test_size)))
    calibration_indices = order[:split]
    test_indices = order[split:]
    if len(test_indices) == 0:
        test_indices = order[:1]

    scaler = TemperatureScaler()
    scaler.calibrate(logits[calibration_indices], true_indices[calibration_indices])

    calibration_probabilities = _softmax(
        scaler.scale(logits[calibration_indices])
    )
    calibration_scores = (
        1.0
        - calibration_probabilities[
            np.arange(len(calibration_indices)),
            true_indices[calibration_indices],
        ]
    ) / scaler.temperature
    predictor = ConformalPredictor(alpha=args.alpha)
    predictor.calibrate(calibration_scores)

    test_probabilities = _softmax(scaler.scale(logits[test_indices]))
    test_scores = (1.0 - test_probabilities) / scaler.temperature
    covered = 0
    set_sizes = []
    for row_index, probability_row in enumerate(test_scores):
        prediction_set = predictor.predict_set(probability_row, labels)
        set_sizes.append(prediction_set["set_size"])
        if labels[true_indices[test_indices[row_index]]] in prediction_set["prediction_set"]:
            covered += 1

    ece = expected_calibration_error(
        test_probabilities,
        true_indices[test_indices],
    )
    result = {
        "temperature": round(float(scaler.temperature), 6),
        "q_hat": round(float(predictor.q_hat), 6) if predictor.q_hat is not None else None,
        "alpha": float(args.alpha),
        "labels": labels,
        "n_calibration": int(len(calibration_indices)),
        "n_test": int(len(test_indices)),
        "ece": round(float(ece), 6),
        "avg_set_size": round(float(np.mean(set_sizes)), 6),
        "empirical_coverage": round(float(covered / len(test_indices)), 6),
        "calibration_ece": round(float(scaler.ece), 6),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({key: result[key] for key in ("temperature", "q_hat", "alpha")}, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2))
    print(f"Saved calibration params to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
