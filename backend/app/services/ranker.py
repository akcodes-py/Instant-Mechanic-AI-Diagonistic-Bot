"""ETA + mechanic ranker used by the Kotlin dispatch service.

No accuracy is claimed and no model is committed. With no ETA_MODEL_PATH the
ranker is an honest deterministic nearest-distance heuristic. A trained model
can be mounted at deploy time; the response says which path produced the result.
"""
from __future__ import annotations

import math
from pathlib import Path

from app.config import settings
from app.services.spatial import cell_to_lat_lng, grid_distance, is_valid_cell

_MODEL = None
_MODEL_LOADED = False


def _load_model():
    global _MODEL, _MODEL_LOADED
    if _MODEL_LOADED:
        return _MODEL
    _MODEL_LOADED = True
    path = (settings.ETA_MODEL_PATH or "").strip()
    if not path or not Path(path).is_file():
        return None
    try:
        import joblib  # type: ignore

        _MODEL = joblib.load(path)
    except Exception:
        _MODEL = None
    return _MODEL


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km (WGS84 approximation)."""
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(a)))


def rank(booking_id: str, origin_h3: str, candidates: list[dict]) -> dict:
    """Return rankings sorted by ETA. Never raises on a bad candidate."""
    origin = cell_to_lat_lng(origin_h3) if is_valid_cell(origin_h3) else (None, None)
    model = _load_model()
    rankings: list[dict] = []

    for candidate in candidates:
        mechanic_id = str(candidate.get("mechanic_id") or "").strip()
        if not mechanic_id:
            continue
        cell = str(candidate.get("h3_res8") or "")
        try:
            lat = float(candidate.get("lat", 0))
            lon = float(candidate.get("lon", 0))
        except (TypeError, ValueError):
            continue

        if None in origin:
            distance_km, steps = 5.0, 10
        else:
            distance_km = haversine_km(origin[0], origin[1], lat, lon)
            steps = grid_distance(origin_h3, cell) if is_valid_cell(cell, 8) else 10

        eta = max(60, min(3600, int(distance_km / 0.5 * 60)))
        score = round(1.0 / (1.0 + distance_km), 6)
        if model is not None:
            try:
                predicted = float(model.predict([[distance_km, steps, 1.0]])[0])
                if math.isfinite(predicted):
                    eta = max(60, min(3600, int(predicted)))
            except Exception:
                pass  # A failing model never changes availability of dispatch.

        rankings.append(
            {"mechanic_id": mechanic_id, "eta_seconds": eta, "score": score}
        )

    rankings.sort(key=lambda item: (item["eta_seconds"], -item["score"]))
    return {
        "booking_id": booking_id,
        "rankings": rankings,
        "model_used": model is not None,
        "strategy": "mounted_model" if model is not None else "nearest_distance",
    }
