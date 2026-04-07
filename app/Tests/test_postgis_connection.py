"""
Tests that verify the PostGIS-backed OSM database is reachable
and has the expected data imported.

Run: cd app && pytest Tests/test_postgis_connection.py -v
"""

import pytest
from sqlalchemy import text


pytestmark = pytest.mark.docker


class TestPostGISConnection:

    def test_database_reachable(self, postgis_engine):
        with postgis_engine.connect() as conn:
            result = conn.execute(text("SELECT 1 AS ok")).fetchone()
        assert result.ok == 1

    def test_osm_tables_exist(self, postgis_engine):
        expected = {"planet_osm_polygon", "planet_osm_line", "planet_osm_point", "planet_osm_roads"}
        with postgis_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename LIKE 'planet_osm%'"
            )).fetchall()
        actual = {r.tablename for r in rows}
        assert expected.issubset(actual), f"Missing tables: {expected - actual}"

    def test_polygon_table_has_data(self, postgis_engine):
        with postgis_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) AS n FROM planet_osm_polygon")).fetchone()
        assert count.n > 0, "planet_osm_polygon is empty - PBF import may have failed"

    def test_line_table_has_data(self, postgis_engine):
        with postgis_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) AS n FROM planet_osm_line")).fetchone()
        assert count.n > 0, "planet_osm_line is empty - PBF import may have failed"

    def test_required_columns_exist(self, postgis_engine):
        required = {"osm_id", "way", "building", "water", "highway"}
        with postgis_engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'planet_osm_polygon'"
            )).fetchall()
        actual = {r.column_name for r in rows}
        missing = required - actual
        assert not missing, f"Missing columns in planet_osm_polygon: {missing}"


@pytest.mark.usdata
class TestGeographicRegion:

    def test_not_luxembourg(self, postgis_engine):
        with postgis_engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    ST_YMin(ST_Transform(ST_SetSRID(ST_Extent(way),3857),4326)) as min_lat,
                    ST_YMax(ST_Transform(ST_SetSRID(ST_Extent(way),3857),4326)) as max_lat
                FROM planet_osm_polygon
            """)).fetchone()
        is_luxembourg = (49.0 < float(row.min_lat) < 51.0) and (49.0 < float(row.max_lat) < 51.0)
        assert not is_luxembourg, (
            f"Data looks like Luxembourg (lat {row.min_lat:.1f}-{row.max_lat:.1f}). "
            "Re-import with florida-latest.osm.pbf or us-south-latest.osm.pbf."
        )

    def test_florida_area_has_buildings(self, postgis_engine):
        with postgis_engine.connect() as conn:
            row = conn.execute(text("""
                SELECT ST_YMin(ST_Transform(ST_SetSRID(ST_Extent(way),3857),4326)) as min_lat
                FROM planet_osm_polygon
            """)).fetchone()
            if row is None or float(row.min_lat) > 40:
                pytest.skip("No US-region data imported yet")

            count = conn.execute(text("""
                SELECT count(*) AS n FROM planet_osm_polygon
                WHERE building IS NOT NULL
                AND ST_Intersects(
                    way,
                    ST_Transform(ST_MakeEnvelope(-81.21, 28.59, -81.19, 28.61, 4326), 3857)
                )
            """)).fetchone()
        assert count.n > 0, "No buildings found near UCF - wrong PBF region?"
