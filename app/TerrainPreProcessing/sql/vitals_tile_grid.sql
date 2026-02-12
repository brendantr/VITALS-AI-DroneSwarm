-- Creates PostGIS-side grid + counts for the mission polygon.
-- This moves the expensive spatial joins + aggregation out of Python.

CREATE SCHEMA IF NOT EXISTS vitals;

-- Helper: classify OSM 'highway' tag into the same buckets used in Python.
-- (Matches TerrainPreProcessing/query_disambiguation.py intent)

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
    ELSE 'highway'  -- default unknowns to road, consistent with current Python
  END;
$$;

-- Main: build a square grid (tile_size_m meters) covering the polygon bbox,
-- keep only tiles that intersect the polygon, and count OSM features per tile.
--
-- Returns tiles in EPSG:4326 (lon/lat) for direct use in Shapely/GUI.
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
