from sqlalchemy import Column, String, BigInteger
from geoalchemy2 import Geometry
from sqlalchemy.orm import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import HSTORE
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from sqlalchemy import and_,or_
from shapely.geometry import Polygon
from geoalchemy2.shape import from_shape
from sqlalchemy import select, func, or_
import geopandas as gpd
import numpy as np
import matplotlib.colors as mcolors
from sqlalchemy import create_engine, MetaData, Table, select
from geoalchemy2.shape import to_shape
from sqlalchemy import create_engine, MetaData, Table
from sqlalchemy.exc import OperationalError
from shapely.geometry import Point, Polygon, MultiPolygon, LineString
from pyproj import Transformer


engine = None
metadata = None
planet_osm_polygon = None

def transform_geometry_3857_to_4326(geometry):
    # Create a transformer from EPSG:3857 to EPSG:4326
    transformer = Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True)

    if isinstance(geometry, Point):
        # Transform a single point
        lon, lat = transformer.transform(geometry.x, geometry.y)
        return Point(lon, lat)

    elif isinstance(geometry, Polygon):
        # Transform a polygon (only exterior)
        transformed_coords = [transformer.transform(x, y) for x, y in geometry.exterior.coords]
        return Polygon(transformed_coords)

    elif isinstance(geometry, MultiPolygon):
        # Transform each polygon inside a MultiPolygon
        transformed_polygons = [
            Polygon([transformer.transform(x, y) for x, y in polygon.exterior.coords])
            for polygon in geometry.geoms
        ]
        return MultiPolygon(transformed_polygons)
    elif isinstance(geometry, LineString):
        transformed_coords = [transformer.transform(x, y) for x, y in geometry.coords]
        return LineString(transformed_coords)
    else:
        raise TypeError(f"Input geometry must be a Point, Polygon, or MultiPolygon, got: {type(geometry)}")



def postgis_load_rtree(rtree_index, results):
    for idx, result in enumerate(results):
        result["geometry"] = transform_geometry_3857_to_4326(result["geometry"])
        rtree_index.insert(idx, result["geometry"].bounds, obj = result)


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
        engine = create_engine('postgresql://renderer:renderer@localhost:5432/gis') if engine is None else engine
        metadata = MetaData(schema="public") if metadata is None else metadata
        osm_table = Table(table_name, metadata, autoload_with=engine)
    except OperationalError as e:
        print(f"Error connecting to PostGIS database: {e}")
        return None
            
    base_columns = base_columns or ["osm_id", "way"]
    selected_columns = [osm_table.c[col] for col in base_columns if col in osm_table.c]
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
        engine = create_engine('postgresql://renderer:renderer@localhost:5432/gis') if engine is None else engine

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
    selected_columns = [planet_osm_polygon.c[col] for col in base_columns if col in planet_osm_polygon.c]
    
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
