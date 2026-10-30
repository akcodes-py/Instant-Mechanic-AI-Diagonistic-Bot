"""Optional image preprocessing with Albumentations.

All optional imports are lazy so the module (and the API) stays importable when
opencv/albumentations are not installed. Failures return the original path.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def preprocess_for_inference(image_path: str | Path) -> str:
    """Apply CLAHE/sharpen/contrast and save a preprocessed copy.

    Returns the original path unchanged on any failure.
    """
    original = str(image_path)
    try:
        import albumentations as A
        import cv2

        path = Path(image_path)
        image = cv2.imread(str(path))
        if image is None:
            return original
        transform = A.Compose(
            [
                A.CLAHE(clip_limit=2.0, tile_grid_size=(8, 8), p=1.0),
                A.Sharpen(alpha=(0.2, 0.5), lightness=(0.5, 1.0), p=0.5),
                A.RandomBrightnessContrast(
                    brightness_limit=0.2, contrast_limit=0.2, p=0.3
                ),
            ]
        )
        processed = transform(image=image)["image"]
        destination = path.with_name("preprocessed_" + path.name)
        if not cv2.imwrite(str(destination), processed):
            return original
        return str(destination)
    except Exception as exc:  # pragma: no cover - depends on optional libs
        logger.warning("Preprocessing failed: %s", type(exc).__name__)
        return original


def is_low_quality(image_path: str | Path) -> bool:
    """Return True for a blurry or too-dark image; False on any error."""
    try:
        import cv2
        import numpy as np

        image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            return False
        if float(np.mean(image)) < 50:
            return True
        return float(cv2.Laplacian(image, cv2.CV_64F).var()) < 100
    except Exception:  # pragma: no cover - depends on optional libs
        return False
