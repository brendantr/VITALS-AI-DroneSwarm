#!/usr/bin/env bash
#
# VITALS SITL entrypoint -- Tier 1 process supervision.
#
# THE FAILURE MODE THIS GUARDS AGAINST
# ------------------------------------
# MAVProxy is a *client* of SITL (--master tcp:127.0.0.1:5760) but a *server* for
# VITALS (--out tcpin:0.0.0.0:14550). If arducopter dies, MAVProxy survives, keeps
# the 14550 listener open, still completes VITALS' TCP handshake -- and delivers
# zero heartbeats. Dispatcher.wait_heartbeat() then blocks forever while every
# port-level check reports "healthy". A dead simulator must never look alive.
#
# Tier 1 answer: both processes are tracked PIDs under one supervisor. Whichever
# exits first, we log which one and why, tear down the sibling, and exit non-zero.
# Combined with `restart: "no"` in docker-compose.sitl.yml, a SITL crash leaves an
# unambiguous `Exited (n)` container instead of a zombie answering on 14550.
#
# Tier 1 catches PROCESS DEATH. It does NOT catch a wedged-but-alive SITL (process
# up, heartbeats stopped) -- that needs a MAVLink data-plane probe, which was
# deliberately deferred out of this phase along with any extra internal port.

set -Eeuo pipefail

log() { printf '[sitl-entrypoint] %s\n' "$*"; }

ARDUCOPTER_BIN="${ARDUCOPTER_BIN:-/opt/ardupilot/build/sitl/bin/arducopter}"
SITL_DEFAULTS="${SITL_DEFAULTS:-/opt/ardupilot/Tools/autotest/default_params/copter.parm}"

# Home = VITALS mission preset 1 (missionState.py:238). 25 m alt is a simulation
# estimate, not verified terrain elevation.
SITL_HOME="${SITL_HOME:-28.6013158,-81.2020057,25,0}"
SITL_MODEL="${SITL_MODEL:-quad}"
SITL_SPEEDUP="${SITL_SPEEDUP:-1}"
SITL_INSTANCE="${SITL_INSTANCE:-0}"
MAVPROXY_TCP_PORT="${MAVPROXY_TCP_PORT:-14550}"

# ArduPilot instance N listens on 5760 + 10*N. Container-internal only.
SITL_MASTER_PORT=$(( 5760 + 10 * SITL_INSTANCE ))

RUN_DIR="${RUN_DIR:-/sitl-run}"
mkdir -p "$RUN_DIR/mavproxy"
cd "$RUN_DIR"

SITL_PID=""
MAVPROXY_PID=""

# Stop a PID politely, then forcibly. Never fails the script.
stop_pid() {
    local name="$1" pid="$2"
    [[ -n "$pid" ]] || return 0
    kill -0 "$pid" 2>/dev/null || return 0
    log "stopping $name (pid $pid)"
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 50); do
        kill -0 "$pid" 2>/dev/null || return 0
        sleep 0.1
    done
    log "$name (pid $pid) did not exit on SIGTERM; sending SIGKILL"
    kill -KILL "$pid" 2>/dev/null || true
}

teardown() {
    stop_pid mavproxy "$MAVPROXY_PID"
    stop_pid arducopter "$SITL_PID"
}

on_signal() {
    log "received shutdown signal; tearing down"
    teardown
    exit 143
}
trap on_signal INT TERM

if [[ ! -x "$ARDUCOPTER_BIN" ]]; then
    log "FATAL: arducopter binary not found or not executable at $ARDUCOPTER_BIN"
    exit 127
fi
if [[ ! -f "$SITL_DEFAULTS" ]]; then
    log "FATAL: SITL default params not found at $SITL_DEFAULTS"
    exit 127
fi

log "arducopter : $ARDUCOPTER_BIN"
log "home       : $SITL_HOME  (lat,lon,alt_m,heading -- alt is a simulation estimate)"
log "model      : $SITL_MODEL   speedup: $SITL_SPEEDUP   instance: $SITL_INSTANCE"
log "master     : tcp:127.0.0.1:$SITL_MASTER_PORT  (container-internal, not published)"
log "serving    : tcpin:0.0.0.0:$MAVPROXY_TCP_PORT  (published to Mac host loopback only)"

"$ARDUCOPTER_BIN" \
    -S \
    -I"$SITL_INSTANCE" \
    --model "$SITL_MODEL" \
    --speedup "$SITL_SPEEDUP" \
    --defaults "$SITL_DEFAULTS" \
    --home "$SITL_HOME" &
SITL_PID=$!
log "arducopter started (pid $SITL_PID)"

# Wait for SITL's master listener before starting MAVProxy; MAVProxy errors out if
# its --master target refuses the connection, which would trip the supervisor on a
# pure startup race. `ss` inspects the listening socket WITHOUT connecting, so this
# probe cannot consume the connection slot MAVProxy needs.
log "waiting for SITL listener on port $SITL_MASTER_PORT"
SITL_READY=0
for _ in $(seq 1 120); do
    if ! kill -0 "$SITL_PID" 2>/dev/null; then
        wait "$SITL_PID" 2>/dev/null || true
        log "FATAL: arducopter exited during startup, before its listener came up"
        exit 1
    fi
    if ss -ltnH 2>/dev/null | grep -qE "[:.]${SITL_MASTER_PORT}[[:space:]]"; then
        SITL_READY=1
        break
    fi
    sleep 0.5
done

if [[ "$SITL_READY" -ne 1 ]]; then
    log "FATAL: SITL listener on port $SITL_MASTER_PORT did not appear within ~60s"
    teardown
    exit 1
fi
log "SITL listener is up"

# --non-interactive (not --daemon): --daemon detaches and would break PID tracking,
# which is the whole basis of Tier 1 supervision.
mavproxy.py \
    --master "tcp:127.0.0.1:$SITL_MASTER_PORT" \
    --out "tcpin:0.0.0.0:$MAVPROXY_TCP_PORT" \
    --non-interactive \
    --state-basedir "$RUN_DIR/mavproxy" &
MAVPROXY_PID=$!
log "mavproxy started (pid $MAVPROXY_PID)"

log "supervising both processes; first exit tears down the container"

# Block until EITHER child exits. `wait -n` with no PID args waits on any job, which
# keeps this portable across bash versions.
set +e
wait -n
FIRST_STATUS=$?
set -e

if ! kill -0 "$SITL_PID" 2>/dev/null; then
    log "arducopter (pid $SITL_PID) EXITED first, status $FIRST_STATUS -- the simulator is dead"
    log "tearing down mavproxy so port $MAVPROXY_TCP_PORT cannot answer without a simulator behind it"
elif ! kill -0 "$MAVPROXY_PID" 2>/dev/null; then
    log "mavproxy (pid $MAVPROXY_PID) EXITED first, status $FIRST_STATUS -- VITALS has no MAVLink server"
    log "tearing down arducopter"
else
    log "a supervised child reported exit status $FIRST_STATUS; tearing down both"
fi

teardown

# Always non-zero: reaching this point means the simulator is no longer serving.
if [[ "$FIRST_STATUS" -eq 0 ]]; then
    log "exiting 1 (a child exited cleanly, but the simulator is still gone)"
    exit 1
fi
log "exiting $FIRST_STATUS"
exit "$FIRST_STATUS"
