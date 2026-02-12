# TerrainPreProcessing SQL (PostGIS)

This folder contains SQL you can install into your PostGIS database so the **grid generation + feature counting** happens in PostgreSQL instead of Python.

## What you get

Installing [vitals_tile_grid.sql](vitals_tile_grid.sql) creates:

- `schema vitals`
- `vitals.classify_highway(text) -> text`
- `vitals.get_tile_counts_4326(polygon_wkt_4326 text, tile_size_m int)`

`vitals.get_tile_counts_4326` returns one row per tile intersecting the mission polygon, with:

- `x_idx`, `y_idx` (tile indices)
- `tile_wkt_4326` (tile polygon in lon/lat)
- `centroid_lon`, `centroid_lat`
- counts for `building`, `water`, and `highway` split into `highway` vs `pedestrian_path`

Python then rebuilds the existing `Tile[][]` grid from these rows.

## Install the SQL into Postgres

### Option A: using Docker (typical tile-server / PostGIS container)

1. Find the container name/ID:

- `docker ps`

2. Exec `psql` inside the container and run the SQL file.

If you are in the repo root (so the file path resolves), run:

- `docker exec -i <container> psql -U renderer -d gis < VITALS-AI-DroneSwarm/app/TerrainPreProcessing/sql/vitals_tile_grid.sql`

Notes:
- If your DB user/db differs, replace `renderer`/`gis`.
- On Windows PowerShell, input redirection (`< file.sql`) works; if it doesn’t in your setup, use Option B.

### Option B: run from psql on your host

If you have `psql` installed locally and the database port is exposed (usually 5432):

- `psql -h localhost -p 5432 -U renderer -d gis -f VITALS-AI-DroneSwarm/app/TerrainPreProcessing/sql/vitals_tile_grid.sql`

## Quick sanity check

In `psql`:

- `SELECT vitals.classify_highway('footway');`
- `SELECT * FROM vitals.get_tile_counts_4326('POLYGON((-81.2039 28.6055, -81.1950 28.6053, -81.1946 28.5974, -81.2039 28.5972, -81.2039 28.6055))', 60) LIMIT 5;`

The second query expects WKT in EPSG:4326 where coordinates are `(lon lat)`.

## How the Python code uses this

- If the app falls back to PostGIS (no internet) or you set `useOSMX=False`,
  [TerrainPreProcessing/terrain_queries.py](../terrain_queries.py) will try `query_tile_counts_4326()`.
- If the SQL function is installed, Python uses the DB-returned tiles/counts.
- If not installed, it automatically falls back to the old Python counting path.
