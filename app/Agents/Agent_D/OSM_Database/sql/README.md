# Agent D OSM SQL

This SQL moves tile grid generation and terrain feature counting into PostGIS.

## Install

1. Start your OSM tile/PostGIS container.
2. Run:

```bash
docker exec -i <container_name> psql -U renderer -d gis < app/Agent/Agent_D/OSM_Database/sql/vitals_tile_grid.sql
```

## Optional auto-install

Set:

- `VITALS_AUTO_INSTALL_TILE_SQL=1`
- `VITALS_POSTGIS_URL=postgresql://renderer:renderer@localhost:5432/gis` (or your URL)

Then Agent D will auto-install the SQL function if missing.
