"""H3 hexagonal spatial helpers shared by dispatch, diagnostics and analytics.

The conventions are defined in ``contracts/h3.md``:

* Resolution 8 (~460 m) - live presence and ring dispatch.
* Resolution 7 (~1.22 km) - Kafka partition key, heatmaps and analytics.

This module has no framework or database dependencies so it can be reused by
batch jobs and tested without services. See ADR-001.
"""
from __future__ import annotations

from collections.abc import Iterator

import h3

from app.config import settings

PRESENCE_RESOLUTION = 8
ZONE_RESOLUTION = 7
MAX_RING = 3
RING_SIZES = {1: 7, 2: 19, 3: 37}


def lat_lng_to_cell(lat: float, lon: float, resolution: int | None = None) -> str:
    """Index a WGS84 coordinate at the given resolution (default Res-8)."""
    if not -90.0 <= lat <= 90.0:
        raise ValueError("lat must be between -90 and 90")
    if not -180.0 <= lon <= 180.0:
        raise ValueError("lon must be between -180 and 180")
    res = resolution if resolution is not None else settings.H3_PRESENCE_RESOLUTION
    return h3.latlng_to_cell(lat, lon, res)


def cell_to_lat_lng(cell: str) -> tuple[float, float]:
    """Return the centre (lat, lon) of an H3 cell."""
    lat, lon = h3.cell_to_latlng(cell)
    return float(lat), float(lon)


def ring(origin_cell: str, k: int) -> list[str]:
    """All cells within k hops of ``origin_cell``, including the origin.

    k=1 -> 7 hexes, k=2 -> 19 hexes, k=3 -> 37 hexes (for a non-pentagon origin).
    """
    if k < 0:
        raise ValueError("ring radius k must be >= 0")
    return list(h3.grid_disk(origin_cell, k))


def cascade_rings(
    origin_cell: str, max_ring: int | None = None
) -> Iterator[tuple[int, list[str]]]:
    """Yield successive dispatch rings from the origin outward.

    Ring 1 is the origin cell itself (a single hex); ring k>0 is the set of
    *newly added* cells at that hop, so each mechanic is offered at most once.
    """
    limit = max_ring if max_ring is not None else settings.DISPATCH_MAX_RING
    seen: set[str] = set()
    for k in range(1, limit + 1):
        cells = [cell for cell in ring(origin_cell, k) if cell not in seen]
        seen.update(cells)
        yield k, cells


def zone_cell(cell_or_lat: str | float, lon: float | None = None) -> str:
    """Return the Res-7 zone for a Res-8 cell or a (lat, lon) pair."""
    if isinstance(cell_or_lat, str):
        if lon is not None:
            raise ValueError("pass either a cell string or a (lat, lon) pair")
        return h3.cell_to_parent(cell_or_lat, settings.H3_ZONE_RESOLUTION)
    if lon is None:
        raise ValueError("lon is required with a numeric lat")
    return lat_lng_to_cell(cell_or_lat, lon, settings.H3_ZONE_RESOLUTION)


def grid_distance(a: str, b: str) -> int:
    """Number of H3 steps between two cells (used by the nearest-ETA fallback)."""
    return h3.grid_distance(a, b)


def is_valid_cell(value: str, resolution: int | None = None) -> bool:
    """True when ``value`` is a valid H3 cell at the expected resolution."""
    try:
        if not h3.is_valid_cell(value):
            return False
        if resolution is not None and h3.get_resolution(value) != resolution:
            return False
        return True
    except (TypeError, ValueError):
        return False
