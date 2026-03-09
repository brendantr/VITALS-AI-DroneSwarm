from __future__ import annotations

import os
from pathlib import Path

from shapely import wkt as shapely_wkt
from shapely.geometry import Point, Polygon
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


engine = None


def _get_postgis_url() -> str:
    for key in ("VITALS_POSTGIS_URL", "POSTGIS_URL", "DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value
    return "postgresql://renderer:renderer@localhost:5432/gis"


def _sql_file_path() -> Path:
    return Path(__file__).resolve().parent.parent / "sql" / "vitals_tile_grid.sql"


def _vitals_tile_function_exists(conn) -> bool:
    exists_sql = text(
        """
        SELECT 1
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'vitals'
          AND p.proname = 'get_tile_counts_4326'
        LIMIT 1;
        """
    )
    return conn.execute(exists_sql).first() is not None


def ensure_vitals_tile_sql_installed() -> bool:
    if os.getenv("VITALS_AUTO_INSTALL_TILE_SQL", "0") not in ("1", "true", "TRUE", "yes", "YES"):
        return False

    global engine
    try:
        engine = create_engine(_get_postgis_url()) if engine is None else engine
    except OperationalError as e:
        print(f"Error connecting to PostGIS database: {e}")
        return False

    with engine.connect() as conn:
        if _vitals_tile_function_exists(conn):
            return True

    sql_path = _sql_file_path()
    if not sql_path.exists():
        print(f"Missing SQL file: {sql_path}")
        return False

    sql_text = sql_path.read_text(encoding="utf-8")
    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        try:
            cur.execute(sql_text)
        finally:
            cur.close()
        raw_conn.commit()
    except Exception as e:
        try:
            raw_conn.rollback()
        except Exception:
            pass
        print(f"Failed to install vitals tile SQL: {e}")
        return False
    finally:
        raw_conn.close()

    with engine.connect() as conn:
        return _vitals_tile_function_exists(conn)


def _polygon_points_to_wkt_4326(polygon_points):
    if not polygon_points:
        raise ValueError("polygon_points is required")
    lon_lat = [(lon, lat) for (lat, lon) in polygon_points]
    poly = Polygon(lon_lat)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly.wkt


def query_tile_counts_4326(polygon_points, tile_size_m=60):
    global engine
    try:
        engine = create_engine(_get_postgis_url()) if engine is None else engine
    except OperationalError as e:
        print(f"Error connecting to PostGIS database: {e}")
        return None

    ensure_vitals_tile_sql_installed()

    polygon_wkt = _polygon_points_to_wkt_4326(polygon_points)
    sql = text(
        """
        SELECT
            x_idx,
            y_idx,
            tile_wkt_4326,
            centroid_lon,
            centroid_lat,
            building_count,
            water_count,
            highway_count,
            pedestrian_path_count
        FROM vitals.get_tile_counts_4326(:polygon_wkt, :tile_size_m);
        """
    )

    with engine.connect() as conn:
        rows = conn.execute(sql, {"polygon_wkt": polygon_wkt, "tile_size_m": int(tile_size_m)}).fetchall()

    results = []
    for r in rows:
        tile_poly = shapely_wkt.loads(r.tile_wkt_4326)
        centroid = Point(float(r.centroid_lon), float(r.centroid_lat))
        counts = {
            "building": int(r.building_count or 0),
            "water": int(r.water_count or 0),
            "highway": int(r.highway_count or 0),
            "pedestrian_path": int(r.pedestrian_path_count or 0),
        }
        total = sum(counts.values())
        results.append(
            {
                "x_idx": int(getattr(r, "x_idx", 0) or 0),
                "y_idx": int(getattr(r, "y_idx", 0) or 0),
                "tile_polygon": tile_poly,
                "centroid": centroid,
                "counts": counts,
                "total_count": total,
            }
        )
    return results
