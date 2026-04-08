#!/bin/bash
set -euo pipefail
export PGPASSWORD="renderer"

# ── If the command is "import", just delegate to upstream as-is ──
if [ "${1:-}" = "import" ]; then
    exec /run.sh import
fi

# ── If the command is "run", start upstream then apply custom SQL ──
if [ "${1:-}" = "run" ]; then
    # Start the upstream run.sh in the background
    /run.sh run &
    UPSTREAM_PID=$!

    # Wait for PostgreSQL to accept connections (up to 120 seconds)
    echo "[VITALS] Waiting for PostgreSQL to be ready..."
    for i in $(seq 1 120); do
        if pg_isready -h localhost -U renderer -d gis >/dev/null 2>&1; then
            echo "[VITALS] PostgreSQL is ready."
            break
        fi
        sleep 1
    done

    # Check if a marker exists to avoid re-applying SQL on every restart
    MARKER=$(psql -h localhost -U renderer -d gis -tAc \
        "SELECT 1 FROM information_schema.schemata WHERE schema_name = 'vitals';" 2>/dev/null || echo "")

    if [ "$MARKER" != "1" ]; then
        echo "[VITALS] Applying vitals_osm_features.sql ..."
        psql -h localhost -U renderer -d gis \
            -f /docker-entrypoint-initdb.d/vitals_osm_features.sql
        echo "[VITALS] Custom SQL applied successfully."
    else
        echo "[VITALS] VITALS schema already exists, skipping SQL init."
    fi

    # Bring upstream back to foreground
    wait $UPSTREAM_PID
fi

# Fallback: pass through any other command
exec "$@"