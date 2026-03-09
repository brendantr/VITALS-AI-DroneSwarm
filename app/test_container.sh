#!/usr/bin/env bash

# Robust Docker Compose test script for the app stack.
# - Resolves paths from the script location (cwd-agnostic)
# - Uses modern `docker compose -f` with explicit compose file
# - Builds, starts, checks status, optional DB health, and tears down

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

echo "Testing Docker Compose setup..."
echo "Compose file: $COMPOSE_FILE"

# Validate compose file exists
if [ ! -f "$COMPOSE_FILE" ]; then
    echo "ERROR: Compose file not found at $COMPOSE_FILE" >&2
    exit 1
fi

# Check Docker is available
if ! docker info > /dev/null 2>&1; then
    echo "ERROR: Docker is not running or not accessible" >&2
    exit 1
fi

echo "Docker version:"; docker version || true
echo "Docker Compose version:"; docker compose version || true

echo "Building services..."
docker compose -f "$COMPOSE_FILE" build

echo "Starting services..."
docker compose -f "$COMPOSE_FILE" up -d

echo "Waiting for services to start..."
sleep 15

echo "Checking service status..."
SERVICES=$(docker compose -f "$COMPOSE_FILE" ps --services)
if [ -z "$SERVICES" ]; then
    echo "ERROR: No services found in compose file" >&2
    docker compose -f "$COMPOSE_FILE" logs || true
    docker compose -f "$COMPOSE_FILE" down || true
    exit 1
fi

FAILED_SERVICES=""
for service in $SERVICES; do
    cid=$(docker compose -f "$COMPOSE_FILE" ps -q "$service")
    if [ -z "$cid" ]; then
        echo "Service $service has no container ID" >&2
        FAILED_SERVICES="$FAILED_SERVICES $service"
        continue
    fi
    state=$(docker inspect -f '{{.State.Status}}' "$cid")
    echo "- $service ($cid) status: $state"
    if [ "$state" != "running" ]; then
        FAILED_SERVICES="$FAILED_SERVICES $service"
    fi
done

if [ -n "$FAILED_SERVICES" ]; then
    echo "ERROR: The following services failed to start:$FAILED_SERVICES" >&2
    docker compose -f "$COMPOSE_FILE" logs || true
    docker compose -f "$COMPOSE_FILE" down || true
    exit 1
fi

# Optional: Postgres health check if a `database` service exists
if echo "$SERVICES" | grep -q '^database$'; then
    echo "Running Postgres health check..."
    db_cid=$(docker compose -f "$COMPOSE_FILE" ps -q database)
    if [ -n "$db_cid" ] && docker exec "$db_cid" pg_isready -q; then
        echo "Postgres is ready."
    else
        echo "WARNING: Postgres is not ready" >&2
        docker compose -f "$COMPOSE_FILE" logs database || true
    fi
fi

echo "SUCCESS: All Docker Compose services are running correctly"

echo "Stopping services..."
docker compose -f "$COMPOSE_FILE" down

echo "Test completed successfully"