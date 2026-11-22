"""H3 spatial helper tests. No external services or model files required."""
import pytest

from app.services import spatial


def test_lat_lng_to_cell_defaults_to_resolution_8():
    cell = spatial.lat_lng_to_cell(28.4595, 77.0266)
    assert len(cell) == 15
    assert cell[1] == "8"  # H3's resolution nibble is the 2nd hex character
    assert spatial.is_valid_cell(cell, 8)


def test_lat_lng_to_cell_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError, match="lat"):
        spatial.lat_lng_to_cell(91.0, 77.0)
    with pytest.raises(ValueError, match="lon"):
        spatial.lat_lng_to_cell(28.0, 181.0)


def test_ring_sizes_follow_the_h3_convention():
    origin = spatial.lat_lng_to_cell(28.4595, 77.0266)
    assert len(spatial.ring(origin, 0)) == 1
    assert len(spatial.ring(origin, 1)) == 7
    assert len(spatial.ring(origin, 2)) == 19
    assert len(spatial.ring(origin, 3)) == 37


def test_ring_rejects_negative_radius():
    origin = spatial.lat_lng_to_cell(28.4595, 77.0266)
    with pytest.raises(ValueError, match=">= 0"):
        spatial.ring(origin, -1)


def test_cascade_rings_are_disjoint_and_cover_all_three_rings():
    origin = spatial.lat_lng_to_cell(28.4595, 77.0266)
    rings = list(spatial.cascade_rings(origin))
    assert [k for k, _ in rings] == [1, 2, 3]
    assert [len(cells) for _, cells in rings] == [7, 12, 18]
    flat = [cell for _, cells in rings for cell in cells]
    assert len(flat) == len(set(flat)) == 37
    assert set(flat) == set(spatial.ring(origin, 3))


def test_zone_cell_returns_parent_resolution_7():
    cell = spatial.lat_lng_to_cell(28.4595, 77.0266)
    zone = spatial.zone_cell(cell)
    assert zone[1] == "7"
    assert spatial.zone_cell(28.4595, 77.0266) == zone


def test_zone_cell_rejects_ambiguous_arguments():
    cell = spatial.lat_lng_to_cell(28.4595, 77.0266)
    with pytest.raises(ValueError):
        spatial.zone_cell(cell, 77.0)
    with pytest.raises(ValueError):
        spatial.zone_cell(28.4595)


def test_cell_to_lat_lng_round_trip_is_close():
    cell = spatial.lat_lng_to_cell(28.4595, 77.0266)
    lat, lon = spatial.cell_to_lat_lng(cell)
    assert lat == pytest.approx(28.4595, abs=0.02)
    assert lon == pytest.approx(77.0266, abs=0.02)


def test_grid_distance_between_adjacent_cells_is_one():
    origin = spatial.lat_lng_to_cell(28.4595, 77.0266)
    neighbours = spatial.ring(origin, 1)
    other = next(cell for cell in neighbours if cell != origin)
    assert spatial.grid_distance(origin, other) == 1


def test_is_valid_cell_checks_resolution_and_handles_garbage():
    cell = spatial.lat_lng_to_cell(28.4595, 77.0266)
    assert spatial.is_valid_cell(cell)
    assert not spatial.is_valid_cell(cell, 7)
    assert not spatial.is_valid_cell("not-a-cell")
    assert not spatial.is_valid_cell(None)
