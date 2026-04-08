FROM overv/openstreetmap-tile-server

# ── Copy the PBF file into the image so it's always available ──
# Place your .osm.pbf file next to this Dockerfile before building,
# or adjust the path accordingly.
COPY florida-260407.osm.pbf /data/region.osm.pbf

# ── Copy custom VITALS SQL to run after import ──
COPY sql/vitals_osm_features.sql /docker-entrypoint-initdb.d/vitals_osm_features.sql

# ── Custom entrypoint wrapper that:
#    1. Delegates to the upstream entrypoint (import + run)
#    2. Applies VITALS SQL after PostgreSQL is ready
COPY entrypoint-wrapper.sh /entrypoint-wrapper.sh

RUN echo "localhost:5432:gis:renderer:renderer" > /root/.pgpass && chmod 600 /root/.pgpass

RUN chmod +x /entrypoint-wrapper.sh

ENTRYPOINT ["/entrypoint-wrapper.sh"]