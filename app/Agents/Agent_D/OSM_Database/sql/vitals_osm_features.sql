-- =============================================================================
-- vitals_osm_features.sql
-- Moves remaining Python spatial operations into PostGIS.
-- Depends on: vitals_tile_grid.sql (for the vitals schema)
-- =============================================================================

-- Ensure the vitals schema exists (idempotent)
CREATE SCHEMA IF NOT EXISTS vitals;

-- ---------------------------------------------------------------------------
-- 1. vitals.query_features_in_polygon
--    Replaces: postgis_handler.py → query_osm_features_all()
--              postgis_handler.py → query_osm_features_advanced()
--              postgis_handler.py → create_bounding_box()
--              postgis_handler.py → transform_geometry_3857_to_4326()
--              postgis_handler.py → postgis_load_rtree()
--
--    Returns buildings, water, and highways within a WKT polygon (EPSG:4326)
--    with geometries already transformed to 4326. No Python R-tree needed —
--    PostGIS GiST index handles spatial lookups.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION vitals.query_features_in_polygon(
    polygon_wkt_4326 text
)
RETURNS TABLE (
    osm_id       bigint,
    feature_type text,       -- 'building', 'water', 'highway'
    tag_value    text,        -- the actual tag value (e.g., 'yes', 'river', 'residential')
    geom_wkt_4326 text        -- geometry as WKT in EPSG:4326
)
LANGUAGE sql STABLE
AS $$
    WITH mission AS (
        SELECT ST_Transform(ST_GeomFromText(polygon_wkt_4326, 4326), 3857) AS geom_3857
    )
    -- Buildings (from polygon table)
    SELECT
        p.osm_id,
        'building'::text AS feature_type,
        p.building AS tag_value,
        ST_AsText(ST_Transform(p.way, 4326)) AS geom_wkt_4326
    FROM public.planet_osm_polygon p, mission m
    WHERE p.building IS NOT NULL
      AND ST_Intersects(p.way, m.geom_3857)

    UNION ALL

    -- Water (from polygon table)
    SELECT
        p.osm_id,
        'water'::text,
        COALESCE(p.water, p."natural") AS tag_value,
        ST_AsText(ST_Transform(p.way, 4326))
    FROM public.planet_osm_polygon p, mission m
    WHERE (p.water IS NOT NULL OR p."natural" = 'water')
      AND ST_Intersects(p.way, m.geom_3857)

    UNION ALL

    -- Highways (from line table)
    SELECT
        l.osm_id,
        vitals.classify_highway(l.highway) AS feature_type,
        l.highway AS tag_value,
        ST_AsText(ST_Transform(l.way, 4326))
    FROM public.planet_osm_line l, mission m
    WHERE l.highway IS NOT NULL
      AND ST_Intersects(l.way, m.geom_3857);
$$;


-- ---------------------------------------------------------------------------
-- 2. vitals.bounding_box_4326
--    Replaces: terrain_CostMap.py → find_extreme_coordinates()
--
--    Given a polygon WKT in EPSG:4326, returns the bounding box extremes.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION vitals.bounding_box_4326(
    polygon_wkt_4326 text
)
RETURNS TABLE (
    min_lat  double precision,
    max_lat  double precision,
    min_lon  double precision,
    max_lon  double precision,
    width_m  double precision,
    height_m double precision
)
LANGUAGE sql IMMUTABLE
AS $$
    WITH poly AS (
        SELECT ST_GeomFromText(polygon_wkt_4326, 4326) AS geom
    ),
    env AS (
        SELECT ST_Envelope(geom) AS bbox, geom FROM poly
    )
    SELECT
        ST_YMin(bbox)  AS min_lat,
        ST_YMax(bbox)  AS max_lat,
        ST_XMin(bbox)  AS min_lon,
        ST_XMax(bbox)  AS max_lon,
        -- Width (east-west) in meters at the midpoint latitude
        ST_Distance(
            ST_SetSRID(ST_MakePoint(ST_XMin(bbox), (ST_YMin(bbox)+ST_YMax(bbox))/2.0), 4326)::geography,
            ST_SetSRID(ST_MakePoint(ST_XMax(bbox), (ST_YMin(bbox)+ST_YMax(bbox))/2.0), 4326)::geography
        ) AS width_m,
        -- Height (north-south) in meters
        ST_Distance(
            ST_SetSRID(ST_MakePoint((ST_XMin(bbox)+ST_XMax(bbox))/2.0, ST_YMin(bbox)), 4326)::geography,
            ST_SetSRID(ST_MakePoint((ST_XMin(bbox)+ST_XMax(bbox))/2.0, ST_YMax(bbox)), 4326)::geography
        ) AS height_m
    FROM env;
$$;


-- ---------------------------------------------------------------------------
-- 3. vitals.haversine_distance_m
--    Replaces: terrain_CostMap.py → haversine()
--              terrain_CostMap.py → rectangle_side_lengths()
--
--    Returns the great-circle distance in meters between two lat/lon points.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION vitals.haversine_distance_m(
    lat1 double precision, lon1 double precision,
    lat2 double precision, lon2 double precision
)
RETURNS double precision
LANGUAGE sql IMMUTABLE
AS $$
    SELECT ST_Distance(
        ST_SetSRID(ST_MakePoint(lon1, lat1), 4326)::geography,
        ST_SetSRID(ST_MakePoint(lon2, lat2), 4326)::geography
    );
$$;


-- ---------------------------------------------------------------------------
-- 4. vitals.offset_point_by_meters
--    Replaces: terrain_CostMap.py → add_meters_to_latitude()
--              terrain_CostMap.py → add_meters_to_longitude()
--
--    Offsets a lat/lon point by dx_m (east) and dy_m (north) meters.
--    Returns the new lat/lon.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION vitals.offset_point_by_meters(
    lat double precision,
    lon double precision,
    dx_m double precision,    -- meters east  (negative = west)
    dy_m double precision     -- meters north (negative = south)
)
RETURNS TABLE (new_lat double precision, new_lon double precision)
LANGUAGE sql IMMUTABLE
AS $$
    WITH projected AS (
        SELECT ST_Transform(ST_SetSRID(ST_MakePoint(lon, lat), 4326), 3857) AS pt_3857
    ),
    shifted AS (
        SELECT ST_Transform(
            ST_Translate(pt_3857, dx_m, dy_m),
            4326
        ) AS pt_4326
        FROM projected
    )
    SELECT
        ST_Y(pt_4326) AS new_lat,
        ST_X(pt_4326) AS new_lon
    FROM shifted;
$$;


-- ---------------------------------------------------------------------------
-- 5. vitals.grid_tile_polygons
--    Replaces: terrain_queries.py → fill_grid_data() grid geometry construction
--
--    Generates the grid tile polygons (without counts) for a mission polygon.
--    Useful when you just need the tile geometry for visualization or intersection
--    checks without the overhead of counting features.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION vitals.grid_tile_polygons(
    polygon_wkt_4326 text,
    tile_size_m integer DEFAULT 60
)
RETURNS TABLE (
    x_idx        integer,
    y_idx        integer,
    tile_wkt_4326 text,
    centroid_lon double precision,
    centroid_lat double precision,
    in_searcharea boolean
)
LANGUAGE sql STABLE
AS $$
    WITH
    mission AS (
        SELECT ST_GeomFromText(polygon_wkt_4326, 4326) AS geom_4326
    ),
    mission_3857 AS (
        SELECT ST_Transform(geom_4326, 3857) AS geom_3857,
               geom_4326
        FROM mission
    ),
    bounds AS (
        SELECT
            ST_XMin(ST_Envelope(geom_3857)) AS xmin,
            ST_YMin(ST_Envelope(geom_3857)) AS ymin,
            ST_XMax(ST_Envelope(geom_3857)) AS xmax,
            ST_YMax(ST_Envelope(geom_3857)) AS ymax,
            geom_3857,
            geom_4326
        FROM mission_3857
    ),
    grid AS (
        SELECT
            (gx.xi - 1)::int AS x_idx,
            (gy.yi - 1)::int AS y_idx,
            ST_MakeEnvelope(gx.x, gy.y, gx.x + tile_size_m, gy.y + tile_size_m, 3857) AS tile_3857,
            geom_3857 AS mission_3857,
            geom_4326 AS mission_4326
        FROM bounds,
            generate_series(xmin, xmax, tile_size_m) WITH ORDINALITY AS gx(x, xi),
            generate_series(ymin, ymax, tile_size_m) WITH ORDINALITY AS gy(y, yi)
    )
    SELECT
        x_idx,
        y_idx,
        ST_AsText(ST_Transform(tile_3857, 4326)),
        ST_X(ST_Transform(ST_Centroid(tile_3857), 4326)),
        ST_Y(ST_Transform(ST_Centroid(tile_3857), 4326)),
        ST_Intersects(ST_Transform(tile_3857, 4326), mission_4326) AS in_searcharea
    FROM grid;
$$;

-- ---------------------------------------------------------------------------
-- 6. vitals.get_tile_counts_4326
--    Replaces: terrain_queries.py → fill_grid_data() feature counting
--    Combines the grid tile generation with counting OSM features in each tile.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION vitals.classify_highway(highway_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN highway_value IS NULL OR length(trim(highway_value)) = 0 THEN 'unknown'
    WHEN lower(highway_value) IN (
      'motorway','trunk','primary','secondary','tertiary',
      'residential','unclassified','service','living_street'
    ) THEN 'highway'
    WHEN lower(highway_value) IN (
      'footway','path','track','bridleway','pedestrian','cycleway'
    ) THEN 'pedestrian_path'
    ELSE 'highway'
  END;
$$;

CREATE OR REPLACE FUNCTION vitals.get_tile_counts_4326(
  polygon_wkt_4326 text,
  tile_size_m integer DEFAULT 60
)
RETURNS TABLE (
  x_idx integer,
  y_idx integer,
  tile_wkt_4326 text,
  centroid_lon double precision,
  centroid_lat double precision,
  building_count integer,
  water_count integer,
  highway_count integer,
  pedestrian_path_count integer
)
LANGUAGE sql
STABLE
AS $$
WITH
  mission AS (
    SELECT ST_GeomFromText(polygon_wkt_4326, 4326) AS geom_4326
  ),
  mission_3857 AS (
    SELECT ST_Transform(geom_4326, 3857) AS geom_3857
    FROM mission
  ),
  bbox AS (
    SELECT ST_Envelope(geom_3857) AS env_3857
    FROM mission_3857
  ),
  bounds AS (
    SELECT
      ST_XMin(env_3857) AS xmin,
      ST_YMin(env_3857) AS ymin,
      ST_XMax(env_3857) AS xmax,
      ST_YMax(env_3857) AS ymax,
      (SELECT geom_3857 FROM mission_3857) AS mission_geom_3857
    FROM bbox
  ),
  grid AS (
    SELECT
      (gx.xi - 1)::int AS x_idx,
      (gy.yi - 1)::int AS y_idx,
      ST_MakeEnvelope(gx.x, gy.y, gx.x + tile_size_m, gy.y + tile_size_m, 3857) AS tile_3857,
      mission_geom_3857
    FROM bounds,
      generate_series(bounds.xmin, bounds.xmax, tile_size_m) WITH ORDINALITY AS gx(x, xi),
      generate_series(bounds.ymin, bounds.ymax, tile_size_m) WITH ORDINALITY AS gy(y, yi)
  ),
  tiles AS (
    SELECT x_idx, y_idx, tile_3857
    FROM grid
    WHERE ST_Intersects(tile_3857, mission_geom_3857)
  )
SELECT
  x_idx,
  y_idx,
  ST_AsText(ST_Transform(tile_3857, 4326)) AS tile_wkt_4326,
  ST_X(ST_Transform(ST_Centroid(tile_3857), 4326)) AS centroid_lon,
  ST_Y(ST_Transform(ST_Centroid(tile_3857), 4326)) AS centroid_lat,

  (SELECT COUNT(*)::int
   FROM public.planet_osm_polygon p
   WHERE p.building IS NOT NULL
     AND ST_Intersects(p.way, tile_3857)) AS building_count,

  (SELECT COUNT(*)::int
   FROM public.planet_osm_polygon p
   WHERE p.water IS NOT NULL
     AND ST_Intersects(p.way, tile_3857)) AS water_count,

  (SELECT COUNT(*)::int
   FROM public.planet_osm_line l
   WHERE l.highway IS NOT NULL
     AND vitals.classify_highway(l.highway) = 'highway'
     AND ST_Intersects(l.way, tile_3857)) AS highway_count,

  (SELECT COUNT(*)::int
   FROM public.planet_osm_line l
   WHERE l.highway IS NOT NULL
     AND vitals.classify_highway(l.highway) = 'pedestrian_path'
     AND ST_Intersects(l.way, tile_3857)) AS pedestrian_path_count

FROM tiles;
$$;