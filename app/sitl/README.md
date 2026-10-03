# VITALS SITL baseline (`app/sitl/`)

## Purpose and scope

An isolated, headless simulation path for **one** ArduCopter SITL virtual quad plus
MAVProxy, running in Docker on an Apple Silicon Mac.

Its only job is to give VITALS a MAVLink endpoint to talk to. **This is not
real-aircraft validation**, and a working simulator does **not** prove that VITALS
itself is working.

All SITL configuration is contained in three files in this directory:
`Dockerfile`, `entrypoint.sh`, `docker-compose.sitl.yml`. This workflow starts only `sitl/docker-compose.sitl.yml`; it does not start the
repository’s primary Compose services (`database`, `agent-b`, `agent-c`, or
`vitals-gcs`). Do not use the repository’s full Compose profile as a shortcut.

## What is verified

Recorded baseline:

- Branch `feature/vitals-sitl`, base commit `d90ab56225d1a5819301498db0d071fa2f009ffe`
- Host: Apple Silicon Mac, ARM64/aarch64
- Docker Engine 29.7.2, Compose v5.4.0

**Verified by actual run.** The image built successfully and the simulator ran.
Observed startup evidence:

- SITL listener up; MAVProxy started
- MAVProxy detected vehicle 1:1
- ArduCopter V4.6.3, frame QUAD/PLUS
- 1397 parameters received
- `ArduPilot Ready`
- GPS/EKF initialization completed

**Verified host connectivity.** From the Mac host, using `app/sitl/.venv-sitl-test`
with pinned `pymavlink==2.4.50`, the test printed:

```
PASS: heartbeat system=1 component=1 type=2
```

Configured values:

| Setting | Value |
|---|---|
| Home | `28.6013158,-81.2020057,25,0` |
| Model | `quad` |
| Published endpoint | `tcp:127.0.0.1:14550` (Mac loopback only) |
| Raw SITL TCP 5760 | container-internal, **not** published |

**Not verified:** the 25 m home altitude is an unverified simulation estimate, not
measured local terrain elevation. It shifts reported MSL only; mission waypoints are
relative-altitude.

## Environment map

Docker and the Mac's Python environments are separate things. Keep them separate.

- **Docker** runs the simulated aircraft and MAVProxy. Nothing about it depends on
  any Mac Python environment.
- **`app/sitl/.venv-sitl-test`** is the one existing host-side verification
  environment. It is intentionally limited to the MAVLink test dependency, and its
  only purpose is to confirm the published TCP endpoint is reachable from the Mac.
- **The Mac's global pyenv Python** was used only for a Tk smoke test. It is *not* a
  VITALS environment and should not receive broad project dependencies.
- **A full native-Mac VITALS GUI environment does not exist yet.** If one is later
  approved, it should be a single clearly named project-level environment (for
  example `app/.venv-vitals`) rather than several ad hoc ones. That path is a
  proposal only — `app/.venv-vitals` does not exist.

## Start and validate SITL

Run from the `app` directory:

```bash
docker compose -f sitl/docker-compose.sitl.yml up
```

Watch for these startup markers in that terminal, ending with `ArduPilot Ready`:

```
SITL listener up
MAVProxy started
MAVProxy detected vehicle 1:1
ArduCopter V4.6.3
Frame: QUAD/PLUS
1397 parameters received
ArduPilot Ready
```

Then, in a second terminal, confirm the Mac host can reach the endpoint:

```bash
cd sitl && ./.venv-sitl-test/bin/python - <<'PY'
from pymavlink import mavutil
v = mavutil.mavlink_connection("tcp:127.0.0.1:14550", mavlink_version="2.0")
h = v.wait_heartbeat(timeout=15)
print(f"PASS: heartbeat system={h.get_srcSystem()} component={h.get_srcComponent()} type={h.type}")
PY
```

Expected output:

```
PASS: heartbeat system=1 component=1 type=2
```

## Stop SITL

Press **Ctrl+C** in the terminal running Compose.

Graceful Ctrl+C is expected to terminate the simulator cleanly. Compose reporting
**exit code 143** after a user-requested signal is the expected result (143 = SIGTERM)
and is **not** a crash.

Do not prune Docker images or build cache while this simulator work is active.
Storage cleanup requires an explicit review of measured disk usage and approval
first.

## Next validation boundary

The next milestone is **VITALS connection only**: prove that VITALS can open its
native Mac Tk GUI and that its existing Connect action receives the SITL heartbeat.
**This has not yet been done.**

What is already verified toward it: a native Mac Tk smoke test passed using
`/Users/architek/.pyenv/versions/3.9.5/bin/python3`, printing
`PASS: Tk initialized and closed`.

What must happen first: the dependency/import footprint has to be evaluated, because
`missionState.py` eagerly imports the GUI, terrain, path planning, LangGraph, OpenCV,
and `ComputerVision.objectDetection`. The currently active global Python lacks most
VITALS dependencies — including `pymavlink`, `tkintermapview`, `ollama`, `cv2`,
`numpy`, the geospatial libraries, `torch`, and `ultralytics` — so **do not run
`missionState.py` from global Python.**

Setting up a full VITALS environment is a future reviewed step. No install command
for it is documented here on purpose.

A narrow Dispatcher-only test is **optional and future/reviewed**. If it happens, it
should reuse the existing `sitl/.venv-sitl-test` rather than adding another small
virtual environment.

## Safety and non-goals

- **Never connect a physical aircraft during simulator work.**
- Do not start the repository's existing full Compose profile as a shortcut.
- Do not alter Jetson-targeted files or Agent B lockfiles to make the Mac simulation
  path work.
- A successful heartbeat or GUI connection is **not** proof of: mission upload,
  arming, takeoff, waypoint progression, return-to-launch, terrain functionality,
  computer vision, Agent B/C, LLM functionality, or real-hardware readiness.
- A **separate review gate is required** before any mission upload, flight-control
  test, or return-to-launch work.
