"""
Integration tests for vitals_osm_features.sql functions.

Set VITALS_POSTGIS_URL, or defaults to
postgresql://renderer:renderer@18.220.206.190:5432/osm

Run with: pytest test_vitals_osm_features.py -v
"""

import os
import pytest
from sqlalchemy import create_engine, text

POSTGIS_URL = os.getenv(
    "VITALS_POSTGIS_URL",
    "postgresql://renderer:renderer@18.220.206.190:5432/gis",
)

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(POSTGIS_URL)
    yield eng
    eng.dispose()

class TestVitalsOSMFeatures:

    def test_classify_highway_function_exists(self, engine):
        q = "SELECT vitals.classify_highway('residential') AS res"
        with engine.connect() as conn:
            result = conn.execute(text(q)).fetchone()
        assert result and result.res == 'highway'

    def test_query_features_in_polygon(self, engine):
        # Very tiny polygon; will just test function exists, not data coverage
        small_poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = (
            "SELECT * FROM vitals.query_features_in_polygon(:poly) LIMIT 1"
        )
        with engine.connect() as conn:
            try:
                conn.execute(text(q), {"poly": small_poly}).fetchone()
            except Exception as e:
                pytest.fail(f"Function call failed: {e}")

    def test_bounding_box_4326(self, engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.bounding_box_4326(:poly)"
        with engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly}).fetchone()
        assert row is not None

    def test_haversine_distance_m(self, engine):
        q = "SELECT vitals.haversine_distance_m(0, 0, 0, 1) AS d"
        with engine.connect() as conn:
            row = conn.execute(text(q)).fetchone()
        assert row and row.d > 0

    def test_offset_point_by_meters(self, engine):
        q = "SELECT * FROM vitals.offset_point_by_meters(0, 0, 1000, 0)"
        with engine.connect() as conn:
            row = conn.execute(text(q)).fetchone()
        assert isinstance(row.new_lat, float) and isinstance(row.new_lon, float)

    def test_grid_tile_polygons(self, engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.grid_tile_polygons(:poly, :tilesz) LIMIT 1"
        with engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly, "tilesz": 60}).fetchone()
        assert row is not None

    def test_get_tile_counts_4326(self, engine):
        poly = "POLYGON((0 0,1 0,1 1,0 1,0 0))"
        q = "SELECT * FROM vitals.get_tile_counts_4326(:poly, :tilesz) LIMIT 1"
        with engine.connect() as conn:
            row = conn.execute(text(q), {"poly": poly, "tilesz": 60}).fetchone()
        assert row is not None