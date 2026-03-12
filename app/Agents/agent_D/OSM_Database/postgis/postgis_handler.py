import os
from pathlib import Path

from sqlalchemy import MetaData, Table, and_, create_engine, func, or_, select, text
from sqlalchemy.exc import OperationalError
from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import Point, Polygon
from shapely import wkt as shapely_wkt


engine = None
metadata = None
planet_osm_polygon = None


def _get_postgis_url() -> str:
    """Return a Postgres connection URL.

    Defaults to the common OpenStreetMap tile-server creds (`renderer`/`gis`).
    Override via env vars to match your deployment.
    """
    for key in ("VITALS_POSTGIS_URL", "POSTGIS_URL", "DATABASE_URL"):
        value = os.getenv(key)
        if value:
            return value
    return "postgresql://renderer:renderer@localhost:5432/gis"


def _sql_file_path() -> Path:
    # Go up from postgis/ to OSM_Database/ then into sql/
    return Path(__file__).resolve().parent.parent / "sql" / "vitals_tile_grid.sql"


def _vitals_tile_function_exists(conn) -> bool:
    # conn: SQLAlchemy Connection
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
    """Install the SQL in TerrainPreProcessing/sql into the connected DB.

    This is opt-in (set env `VITALS_AUTO_INSTALL_TILE_SQL=1`).
    Returns True if the function exists or was installed successfully.
    """
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

    # Use a raw DB-API cursor so the full file (multiple statements, $$ blocks)
    # is executed as-is.
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
    """Convert [(lat, lon), ...] into WKT POLYGON in EPSG:4326."""
    if not polygon_points:
        raise ValueError("polygon_points is required")
    # Shapely expects (x, y) = (lon, lat)
    lon_lat = [(lon, lat) for (lat, lon) in polygon_points]
    poly = Polygon(lon_lat)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly.wkt


def query_tile_counts_4326(polygon_points, tile_size_m=60):
    """
    Calls vitals.get_tile_counts_4326(...) in Postgres to generate a grid and counts.

    Returns a list of dict rows:
      {
        'tile_polygon': shapely Polygon (EPSG:4326),
        'centroid': shapely Point (EPSG:4326),
        'counts': {'building': int, 'water': int, 'highway': int, 'pedestrian_path': int},
        'total_count': int
      }
    """
    global engine
    try:
        engine = create_engine(_get_postgis_url()) if engine is None else engine
    except OperationalError as e:
        print(f"Error connecting to PostGIS database: {e}")
        return None

    # Optional: auto-install SQL helper functions into the DB.
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
        results.append({
            "x_idx": int(getattr(r, "x_idx", 0) or 0),
            "y_idx": int(getattr(r, "y_idx", 0) or 0),
            "tile_polygon": tile_poly,
            "centroid": centroid,
            "counts": counts,
            "total_count": total,
        })
    return results
def postgis_load_rtree(rtree_index, results):
    for idx, result in enumerate(results):
        geom = result.get("geometry")
        if geom is None:
            continue
        rtree_index.insert(idx, geom.bounds, obj=result)


def create_bounding_box(polygon_points):
    # Define the bounding box coordinates (longitude, latitude)
    # Create a Shapely polygon
    bounding_box = Polygon(polygon_points)

    # Convert to WKT for GeoAlchemy2
    bounding_box_wkt = from_shape(bounding_box, srid=4326)
    transformed_bbox = func.ST_Transform(bounding_box_wkt, 3857)
    return transformed_bbox

def query_osm_features_all(tag_filters, polygon_points, base_columns=None):
    polygon_features = query_osm_features_advanced(tag_filters, polygon_points, base_columns, table_name="planet_osm_polygon")
    line_features = query_osm_features_advanced(tag_filters, polygon_points, base_columns, table_name="planet_osm_line")
    combined_features = polygon_features + line_features
    return combined_features

def query_osm_features_advanced(tag_filters, polygon_points, base_columns=None, table_name="planet_osm_polygon"):
    # Dynamically select the table based on the provided table_name.
    global engine, metadata
    try:
        engine = create_engine(_get_postgis_url()) if engine is None else engine
        metadata = MetaData(schema="public") if metadata is None else metadata
        osm_table = Table(table_name, metadata, autoload_with=engine)
    except OperationalError as e:
        print(f"Error connecting to PostGIS database: {e}")
        return None
            
    base_columns = base_columns or ["osm_id", "way"]
    selected_columns = []
    for col in base_columns:
        if col not in osm_table.c:
            continue
        if col == "way":
            # Return geometry in EPSG:4326 to keep the Python side minimal.
            selected_columns.append(func.ST_Transform(osm_table.c.way, 4326).label("way"))
        else:
            selected_columns.append(osm_table.c[col])
    filters = []
    
    for tag, condition in tag_filters.items():
        if tag in osm_table.c:
            if tag not in base_columns:
                selected_columns.append(osm_table.c[tag])
            if condition is True:
                filters.append(osm_table.c[tag].isnot(None))
            else:
                filters.append(osm_table.c[tag] == condition)
        else:
            print(f"Warning: '{tag}' is not a column in {table_name}.")
    
    spatial_filter = None
    if polygon_points:
        bbox = create_bounding_box(polygon_points)
        spatial_filter = func.ST_Intersects(osm_table.c.way, bbox)
    
    stmt = select(*selected_columns)
    if filters:
        final_query = and_(spatial_filter, or_(*filters)) if spatial_filter is not None else or_(*filters)
        stmt = stmt.where(final_query)
    else:
        return []
    
    with engine.connect() as conn:
        results = conn.execute(stmt).fetchall()
    
    info = []
    for result in results:
        shapely_geom = to_shape(result.way)
        feature = {
            'osm_id': result.osm_id,
            'geometry': shapely_geom,
            **{key: result._mapping[key] for key in tag_filters if key in result._mapping}
        }
        # Optionally mark the source
        feature["source"] = table_name
        info.append(feature)
    return info



def query_osm_features(tag_filters, polygon_points, base_columns=None):
    global engine, metadata, planet_osm_polygon
    # Set up your engine; adjust the connection string as needed.
    try:
        engine = create_engine(_get_postgis_url()) if engine is None else engine

        # Create a MetaData instance and reflect the table. Note: no columns are hardcoded.
        metadata = MetaData(schema="public") if metadata is None else metadata
        planet_osm_polygon = Table("planet_osm_polygon", metadata, autoload_with=engine) if planet_osm_polygon is None else planet_osm_polygon
    except OperationalError as e:
        # Catch database connection errors
        print(f"Error connecting to PostGIS database: {e}")
        engine = None
        metadata = None
        planet_osm_polygon = None
        return None
            
    """
    Query the table dynamically based on runtime tag_filters.
    
    :param tag_filters: dict where keys are tag names and values indicate the filter:
                        - If value is True, only include rows where that column is not NULL.
                        - Otherwise, filter for rows equal to the provided value.
    :param base_columns: list of column names that you always want included (e.g., primary key).
    :return: List of rows matching the criteria, with only the requested columns.
    """
    # If you have base columns that should always be returned (like 'osm_id', 'way'),
    # include them. If not, set to empty list.
    base_columns = base_columns or ["osm_id", "way"]

    # Start with the base columns. Only add those that exist in the table.
    selected_columns = []
    for col in base_columns:
        if col not in planet_osm_polygon.c:
            continue
        if col == "way":
            selected_columns.append(func.ST_Transform(planet_osm_polygon.c.way, 4326).label("way"))
        else:
            selected_columns.append(planet_osm_polygon.c[col])
    
    filters = []
    
    # Process the provided tag_filters
    for tag, condition in tag_filters.items():
        if tag in planet_osm_polygon.c:
            # Only add the tag column to the SELECT clause if not already in base_columns.
            if tag not in base_columns:
                selected_columns.append(planet_osm_polygon.c[tag])
            # Build filtering conditions based on the condition value.
            if condition is True:
                filters.append(planet_osm_polygon.c[tag].isnot(None))
            else:
                filters.append(planet_osm_polygon.c[tag] == condition)
        else:
            # Optionally handle the case where the tag isn't in the table.
            print(f"Warning: '{tag}' is not a column in the table.")
    
     # If a bounding box is provided, add a spatial filter.
    spatial_filter = None
    if polygon_points:
        bbox = create_bounding_box(polygon_points)
        # Ensure that both geometries are in the same SRID (here, 3857).
        spatial_filter = func.ST_Intersects(planet_osm_polygon.c.way, bbox)

    # Build the SELECT statement with only the desired columns.
    stmt = select(*selected_columns)

    if filters:

        final_query = and_(spatial_filter,or_(*filters)) if spatial_filter is not None else or_(*filters)
        stmt = stmt.where(final_query)
    else:
        return []
    
    # Execute the query and return results.
    with engine.connect() as conn:
        results = conn.execute(stmt).fetchall()

    info = []
    for result in results:
        shapely_geom = to_shape(result.way)
        start = {
            'osm_id': result.osm_id,
            'geometry': shapely_geom,
            **{key: result._mapping[key] for key in tag_filters}  # Get all search_tags dynamically
        }
        info.append(start)
        #print(start)  # Debugging/logging purposes
    return info
