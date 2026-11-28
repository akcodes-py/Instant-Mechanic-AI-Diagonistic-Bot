"""CPU-only perturbation/occlusion benchmark for the existing YOLO11n weights.

The script never retrains or modifies weights. It applies deterministic
Pillow/NumPy perturbations to a validation subset, runs the SAME lazy YOLO
loader used by the API, and reports what actually happened. With no checkpoint
or no validation images it prints an honest "skipped" report instead of
inventing accuracy numbers.

Usage (from repo root):
    python backend/scripts/eval_vision_robustness.py \
        --weights backend/models/dashboard_lights.pt --images path/to/val/images
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from app.config import settings  # noqa: E402

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SEED = 20261124


def gaussian_noise(image: Image.Image, sigma: float = 0.12) -> Image.Image:
    rng = np.random.default_rng(SEED)
    array = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    noisy = array + rng.normal(0.0, sigma, size=array.shape)
    return Image.fromarray(np.clip(noisy * 255.0, 0, 255).astype(np.uint8))


def motion_blur(image: Image.Image, kernel: int = 9) -> Image.Image:
    array = np.asarray(image.convert("RGB"), dtype=np.float32)
    stacked = np.zeros_like(array)
    for offset in range(kernel):
        stacked += np.roll(array, offset - kernel // 2, axis=1)
    return Image.fromarray(np.clip(stacked / kernel, 0, 255).astype(np.uint8))


def low_light(image: Image.Image, factor: float = 0.35) -> Image.Image:
    array = np.asarray(image.convert("RGB"), dtype=np.float32) * factor
    return Image.fromarray(np.clip(array, 0, 255).astype(np.uint8))


def black_patch(image: Image.Image, coverage: float = 0.55) -> Image.Image:
    array = np.asarray(image.convert("RGB")).copy()
    height, width = array.shape[:2]
    side = max(2, int(min(height, width) * coverage))
    y0, x0 = (height - side) // 2, (width - side) // 2
    array[y0 : y0 + side, x0 : x0 + side] = 0
    return Image.fromarray(array)


PERTURBATIONS = {
    "clean": lambda image: image.copy(),
    "gaussian_noise": gaussian_noise,
    "motion_blur": motion_blur,
    "low_light": low_light,
    "black_patch": black_patch,
}


def _summary(detections: list[dict], threshold: float) -> dict:
    confidences = [
        float(item.get("confidence", 0.0))
        for item in detections
        if isinstance(item, dict)
    ]
    reliable = [
        item for item in detections if isinstance(item, dict) and item.get("reliable")
    ]
    return {
        "detections": len(detections),
        "mean_confidence": round(float(np.mean(confidences)), 4) if confidences else 0.0,
        "max_confidence": round(max(confidences), 4) if confidences else 0.0,
        "reliable_detections": len(reliable),
        "safe_hitl": not bool(reliable),
        "threshold": threshold,
    }


def run(weights: str | None, images: Path, threshold: float, limit: int) -> dict:
    files = sorted(
        path for path in images.rglob("*") if path.suffix.lower() in IMAGE_EXTS
    )[:limit]
    if not weights or not Path(weights).is_file():
        return {"status": "skipped", "reason": "no YOLO checkpoint supplied or found", "images": len(files)}
    if not files:
        return {"status": "skipped", "reason": "no validation images supplied", "images": 0}

    from app.services import vision_service

    settings.VISION_MODEL_PATH = str(Path(weights).resolve())
    vision_service.reset_model_cache()
    if not vision_service.is_available():
        return {"status": "skipped", "reason": "checkpoint could not be resolved", "images": len(files)}

    rows: dict[str, list[dict]] = {name: [] for name in PERTURBATIONS}
    for path in files:
        with Image.open(path) as original:
            original.load()
            for name, transform in PERTURBATIONS.items():
                perturbed = transform(original)
                detections = vision_service.detect_warning_lights(perturbed)
                rows[name].append(_summary(detections, threshold))

    aggregates: dict[str, dict] = {}
    for name, summaries in rows.items():
        count = len(summaries)
        aggregates[name] = {
            "images": count,
            "mean_confidence": round(
                float(np.mean([item["mean_confidence"] for item in summaries])), 4
            ),
            "mean_reliable_detections": round(
                float(np.mean([item["reliable_detections"] for item in summaries])), 3
            ),
            "safe_hitl_rate": round(
                sum(1 for item in summaries if item["safe_hitl"]) / count, 4
            ),
        }
    return {
        "status": "ok",
        "checkpoint": Path(weights).name,
        "images": len(files),
        "seed": SEED,
        "results": aggregates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default=settings.VISION_MODEL_PATH or "")
    parser.add_argument("--images", type=Path, default=Path("backend/models/val"))
    parser.add_argument("--conf", type=float, default=settings.VISION_CONF)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    report = run(args.weights, args.images, args.conf, args.limit)
    text = json.dumps(report, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
