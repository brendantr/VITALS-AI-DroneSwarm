"""
Integration tests for vitals_osm_features.sql functions.

Set VITALS_POSTGIS_URL, or defaults to the shared PostGIS helper URL.

Run with: pytest test_vitals_osm_features.py -v
"""

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.docker


class TestVitalsOSMFeatures:

    def test_classify_highway_function_exists(self, postgis_engine):
        q = "SELECT vitals.classify_highway('residential') AS res"
        with postgis_engine.connect() as conn:
            result = conn.execute(text(q)).fetchone()
        assert result and result.res == "highway"

    def test_query_features_in_polygon(self, postgis_engine):
        small_poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.query_features_in_polygon(:poly) LIMIT 1"
        with postgis_engine.connect() as conn:
            try:
                conn.execute(text(q), {"poly": small_poly}).fetchone()
            except Exception as exc:
                pytest.fail(f"Function call failed: {exc}")

    def test_bounding_box_4326(self, postgis_engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.bounding_box_4326(:poly)"
        with postgis_engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly}).fetchone()
        assert row is not None

    def test_haversine_distance_m(self, postgis_engine):
        q = "SELECT vitals.haversine_distance_m(0, 0, 0, 1) AS d"
        with postgis_engine.connect() as conn:
            row = conn.execute(text(q)).fetchone()
        assert row and row.d > 0

    def test_offset_point_by_meters(self, postgis_engine):
        q = "SELECT * FROM vitals.offset_point_by_meters(0, 0, 1000, 0)"
        with postgis_engine.connect() as conn:
            row = conn.execute(text(q)).fetchone()
        assert isinstance(row.new_lat, float) and isinstance(row.new_lon, float)

    def test_grid_tile_polygons(self, postgis_engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.grid_tile_polygons(:poly, :tilesz) LIMIT 1"
        with postgis_engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly, "tilesz": 60}).fetchone()
        assert row is not None

    def test_get_tile_counts_4326(self, postgis_engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.get_tile_counts_4326(:poly, :tilesz) LIMIT 1"
        with postgis_engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly, "tilesz": 60}).fetchone()
        assert row is not None
