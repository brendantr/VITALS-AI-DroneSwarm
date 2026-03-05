"""
Integration tests for TerrainPreProcessing against the live PostGIS DB.

Run:  cd app && pytest Tests/test_terrain.py -v
"""

import os
import pytest
from sqlalchemy import create_engine, text

from TerrainPreProcessing.terrain_queries import create_search_area


POSTGIS_URL = os.getenv(
    "VITALS_POSTGIS_URL",
    "postgresql://renderer:renderer@localhost:5432/gis",
)


def _has_us_data():
    try:
        engine = create_engine(POSTGIS_URL)
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ST_YMin(ST_Transform(ST_SetSRID(ST_Extent(way),3857),4326)) as min_lat,
                       ST_YMax(ST_Transform(ST_SetSRID(ST_Extent(way),3857),4326)) as max_lat
                FROM planet_osm_polygon
            """)).fetchone()
        engine.dispose()
        if row is None or row.min_lat is None:
            return False
        return float(row.min_lat) < 40 and float(row.max_lat) > 20
    except Exception:
        return False


# Skip every test in this file if we don't have US data
pytestmark = pytest.mark.skipif(
    not _has_us_data(),
    reason="PostGIS not running or no US-region data imported",
)

# UCF area — same polygon used in the original test.py
UCF_POLYGON = (
    (28.6055263, -81.2037652),
    (28.6053378, -81.1950105),
    (28.5973877, -81.1945813),
    (28.5971993, -81.2038939),
)


class TestCreateSearchArea:

    def test_search_area_returns_grid(self):
        search_tags = {"building": True, "water": True}
        rtree, grid, viable = create_search_area(
            UCF_POLYGON, search_tags, useOSMX=False
        )
        assert rtree is not None, "rtree_index is None"
        assert grid is not None, "grid is None"
        assert viable is not None, "viable_positions is None"
        assert len(grid) > 0, "grid has no rows"
        assert len(grid[0]) > 0, "grid has no columns"
        assert len(viable) > 0, "no viable grid positions found"

    def test_grid_tiles_have_counts(self):
        search_tags = {"building": True, "water": True}
        _, grid, _ = create_search_area(UCF_POLYGON, search_tags, useOSMX=False)
        total = sum(tile.total_count for row in grid for tile in row if tile.in_searcharea)
        assert total > 0, "All grid tiles have zero features — data may be missing"