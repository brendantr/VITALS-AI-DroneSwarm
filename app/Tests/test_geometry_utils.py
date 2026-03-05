"""
Pure unit tests for geometry utilities — no Docker required.

Run:  cd app && pytest Tests/test_geometry_utils.py -v
"""

from TerrainPreProcessing.geometry_utils import (
    haversine,
    rectangle_side_lengths,
    add_meters_to_latitude,
    add_meters_to_longitude,
    find_extreme_coordinates,
    Tile,
)


class TestHaversine:
    def test_same_point_is_zero(self):
        assert haversine(28.6, -81.2, 28.6, -81.2) == 0.0

    def test_known_distance(self):
        dist = haversine(40.7128, -74.0060, 51.5074, -0.1278)
        assert 5_500_000 < dist < 5_650_000

    def test_short_distance(self):
        dist = haversine(28.600, -81.200, 28.601, -81.200)
        assert 100 < dist < 120


class TestRectangleSideLengths:
    def test_returns_two_lengths(self):
        w, h = rectangle_side_lengths(28.60, -81.20, 28.61, -81.19)
        assert w > 0
        assert h > 0

    def test_square_ish(self):
        w, h = rectangle_side_lengths(28.60, -81.20, 28.61, -81.19)
        ratio = max(w, h) / min(w, h)
        assert ratio < 1.5


class TestAddMeters:
    def test_add_latitude_positive(self):
        new_lat = add_meters_to_latitude(28.6, 1000)
        assert new_lat > 28.6

    def test_add_latitude_negative(self):
        new_lat = add_meters_to_latitude(28.6, -1000)
        assert new_lat < 28.6

    def test_add_longitude_positive(self):
        new_lon = add_meters_to_longitude(28.6, -81.2, 1000)
        assert new_lon > -81.2

    def test_roundtrip_latitude(self):
        original = 28.6
        moved = add_meters_to_latitude(original, 500)
        dist = haversine(original, -81.2, moved, -81.2)
        assert abs(dist - 500) < 5


class TestFindExtremeCoordinates:
    def test_basic(self):
        coords = [(28.60, -81.20), (28.61, -81.19), (28.59, -81.21)]
        result = find_extreme_coordinates(coords)
        assert result["lowest_latitude"] == 28.59
        assert result["highest_latitude"] == 28.61
        assert result["leftmost_longitude"] == -81.21
        assert result["rightmost_longitude"] == -81.19

    def test_empty_returns_none(self):
        assert find_extreme_coordinates([]) is None


class TestTile:
    def test_default_values(self):
        t = Tile()
        assert t.in_searcharea is True
        assert t.total_count == 0
        assert isinstance(t.contains, dict)
        assert isinstance(t.contains_count, dict)