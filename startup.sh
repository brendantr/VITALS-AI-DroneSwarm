#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate

OSM_DIR="app/Agents/Agent_D/OSM_Database"

cleanup() {
    echo ""
    echo "[VITALS] Stopping OSM Services..."
    (cd "$OSM_DIR" && sudo docker compose down)
}

trap cleanup EXIT INT TERM

echo "[VITALS] Starting OSM services..."
(cd "$OSM_DIR" && sudo docker compose up -d)

echo "[VITALS] Running missionState..."

python app/missionState.py