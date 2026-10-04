# VITALS-AI-DroneSwarm — Architecture & Maintainability Audit

| | |
|---|---|
| **Audited branch** | `feature/sitl-new-working` |
| **Audited commit** | `6ff440225e1f7ec1908b5f4ecc0c623092d2ab8e` — "Verify simulation-mode state construction" |
| **Base of comparison** | `fd236b01` (last non-SITL ancestor), `main` @ `d90ab562` |
| **Audit date** | 2026-10-04 |
| **Method** | Read-only inspection of the committed object tree via `git show` / `git ls-tree` / `git grep <commit>`. No files modified, no services started, no flight commands issued, no packages installed. |
| **Author** | Claude (Opus 5), commissioned architecture review |

> **Working-tree note.** The repository was checked out on `feature/vitals-sitl` during this audit. Every finding below was read from the `6ff44022` object tree, not from the on-disk working copy.

---

> ## ⚠️ REDACTION NOTICE
>
> Two live credentials were found hard-coded in tracked source. **Their values are redacted in this document** so that publishing this report does not create an additional copy of them.
>
> | Secret | Where it still lives in plaintext | Status |
> |---|---|---|
> | AWS API Gateway key (EC2 start/stop) | `app/missionState.py:38`, `app/toggle_osm.py:7` | **Redacted here. Rotate at the source.** |
> | PostGIS password for `18.220.206.190` | `app/Agents/Agent_D/OSM_Database/postgis/postgis_handler.py:20`, `app/Tests/conftest.py:11` | **Redacted here. Rotate at the source.** |
>
> Redaction in this document does **not** remediate the exposure. Both secrets remain in the source files and in full git history. See Risk #1.

---

## A. Executive Summary

VITALS is a PyQt6 desktop GCS whose entire runtime is assembled inside one 1,069-line module, `app/missionState.py`. That module is the application: it is the data model, the thread supervisor, the Agent-B process launcher, the Agent-D client, the CV pipeline, and the `__main__` entry point. Everything downstream of it — MAVLink I/O, mission upload, RTL — lives in a single clean-ish `app/Dispatcher/Dispatcher.py` (597 lines) that is genuinely the system's load-bearing component and has **zero test coverage**.

**The SITL branch is good work and is safe.** Its entire application-code delta is two files: a 30-line guarded change in `missionState.py` and a new 16-line `app/run_sim.py`. Both are gated on `sim_only` / `VITALS_SIM_ONLY`, both default to off, and `Dispatcher.py` is untouched. The live-drone path at `6ff44022` is byte-identical to its base commit. `app/sitl/` is a self-contained, well-reasoned Docker harness with real process supervision. **Verdict: it isolates simulation without weakening live-drone functionality.**

**But simulation does not yet work end-to-end, for five concrete reasons:**

1. `missionState.py:15` imports `PerceptionProcessing.YoloDetector` from the `vision-edge` submodule *before* the sim guard at line 20 — so sim mode still requires the submodule, torch, and ultralytics.
2. `self.agent_d = None` in sim mode (`missionState.py:236`), but `addMissionPolygon()` (line 680) calls `self.agent_d.ingest_message()` unguarded. Drawing a mission polygon raises `AttributeError` inside a Qt slot.
3. `Dispatcher.wait_for_arming()` (line 550) reads `self.master.recv_match()` from a second thread while `receive_packets()` drains the same connection at ~1 kHz. Takeoff very likely times out after 60 s.
4. The "Send Waypoints" debug button passes an **integer** where a waypoint list is expected (`MapPage.get_debug_waypoints()` → `Dispatcher.upload_mission()` → `waypoints.insert(...)`).
5. `app/sitl/mac-venv-vitals-main.freeze.txt` was ported byte-identical from the `main` branch and contains **no PyQt6** — it is a Tk-era environment snapshot that cannot run this branch's GUI.

**Repository hygiene is the single largest mechanical problem.** 76.8 MB of the 78.7 MB tracked tree (97.6%) is generated artifacts: MAVLink telemetry logs, mission POI images, and an osmnx Overpass cache. `.gitignore` already names most of them — they were committed before the rules landed and were never untracked. `.git` is 608 MB.

**Two items need attention today, independent of any refactor:** a live AWS API Gateway key is committed in plaintext in two files, and `.github/workflows/main.yml` starts a cloud EC2 instance on *every push* with a stop step that does not run on failure.

---

## B. System-Context Diagram

```mermaid
graph TB
    subgraph Host["Operator Workstation (macOS / Windows)"]
        subgraph App["VITALS Desktop Application"]
            RUN["run_sim.py<br/>(sim entry)"]
            MAIN["missionState.py __main__<br/>(real entry)"]
            MS["missionState<br/>Drone / POI / mission orchestration<br/>1069 LOC"]
            GUI["GUI.GUI<br/>PyQt6 controller + _Invoker"]
            PAGES["HomePage / MapPage<br/>DebugDialog / SettingsDialog"]
            LEAF["LeafletMap<br/>QWebEngineView + QWebChannel"]
            DISP["Dispatcher<br/>pymavlink, 2 asyncio loops"]
            JOBS["models.jobs<br/>Job / JobQueue"]
            CV["vision-edge submodule<br/>PerceptionProcessing.YoloDetector"]
            LC["LangGraph.langChainMain<br/>ollama tool-calling"]
            AD["Agents.Agent_D<br/>in-process singleton"]
        end
        AB["Agent B subprocess<br/>uvicorn :8081 HTTP + :9000 TCP<br/>spawned by missionState"]
        OLL["ollama daemon<br/>llama3.2 / llava"]
    end

    subgraph Docker["Docker (local)"]
        SITL["vitals-sitl container<br/>ArduCopter 4.6.3 + MAVProxy<br/>tcpin 0.0.0.0:14550"]
    end

    subgraph Cloud["External / Cloud"]
        EC2["OSM EC2 18.220.206.190<br/>PostGIS :5432 + tile server :8080"]
        AWS["AWS API Gateway<br/>EC2 start/stop lambda"]
        CDN["unpkg.com<br/>leaflet 1.9.4 js/css"]
        DNS["8.8.8.8:53<br/>connectivity probe"]
    end

    RUN -->|"VITALS_SIM_ONLY=1"| MS
    MAIN -->|"toggle_database('start')"| AWS
    MAIN --> MS
    MS --> GUI
    MS --> DISP
    MS --> JOBS
    MS --> CV
    MS --> LC
    MS -.->|"skipped when sim_only"| AD
    MS -.->|"skipped when sim_only"| AB
    GUI --> PAGES --> LEAF
    LEAF --> CDN
    LEAF --> DNS
    LEAF -->|"tiles"| EC2
    AD -->|"SQLAlchemy / osmnx"| EC2
    LC -->|"RAG query :8081"| AB
    LC --> OLL
    AB -->|"detections poll 2s"| MS

    DISP <-->|"MAVLink 2.0"| SITL
    DISP <-->|"serial 57600 / UDP 14550"| RADIO["Physical aircraft<br/>RFD900x / QGC forward"]

    classDef sim fill:#1b4332,stroke:#52b788,color:#fff
    classDef real fill:#5c1a1a,stroke:#e07a5f,color:#fff
    classDef cloud fill:#2d3142,stroke:#8d99ae,color:#fff
    class SITL,RUN sim
    class RADIO real
    class EC2,AWS,CDN,DNS cloud
```

---

## C. Runtime-Mode Matrix

| Capability | Real drone (`python missionState.py`) | SITL (`python run_sim.py`) | Full AI/terrain workflow |
|---|---|---|---|
| **Entry point** | `missionState.py:1050` `__main__` | `run_sim.py` | `missionState.py` `__main__` |
| **`VITALS_SIM_ONLY`** | unset | `"1"` (set before imports) | unset |
| **AWS EC2 auto-start** | ✅ `toggle_database('start')` fires | ❌ skipped | ✅ |
| **Agent D (in-process)** | ✅ imported + singleton | ❌ `None`, imports skipped | ✅ |
| **Agent B subprocess** | ✅ uvicorn spawned on :8081 | ❌ skipped | ✅ |
| **Detection poll thread** | ✅ 2 s poll of :8081 | ❌ not started | ✅ |
| **Health poll thread** | ✅ pings :8081 + PostGIS | ❌ not started | ✅ |
| **MAVLink connect** | serial → TCP 14450 → **TCP 14550** → UDP | identical list, **unchanged** | identical |
| **GUI "Simulation" button** | available (detection-point mode) | available | available |
| **Heartbeat / live telemetry** | ✅ | ✅ *(verified by SITL README)* | ✅ |
| **Mission polygon → search plan** | ✅ | ❌ **crashes** — `agent_d` is `None` | ✅ |
| **Manual detection points** | ✅ | ❌ caught exception, no-op | ✅ |
| **Debug "Add Test Job"** | ✅ uses hard-coded UCF waypoints | ✅ **only working upload path** | ✅ |
| **Debug "Send Waypoints"** | ❌ passes int, not list | ❌ same | ❌ |
| **Arm (debug button)** | ✅ `arducopter_arm()` | ✅ | ✅ |
| **Takeoff (debug button)** | ⚠️ 60 s RC-arm wait, racy | ⚠️ same race, no RC in SITL | ⚠️ |
| **Return to launch** | ✅ `set_mode_send(…, 6)` | ✅ | ✅ |
| **Vision detection (real)** | ✅ via Agent B TCP from Jetson | ❌ Agent B not running | ✅ |
| **Vision detection (simulated)** | ❌ `detectionPoints` never populated | ❌ same | ❌ |
| **Map tiles** | EC2 if internet, else `localhost:8080` | same | same |
| **Leaflet JS itself** | ⚠️ always from `unpkg.com` | ⚠️ same | ⚠️ |
| **Heavy deps still required** | all | torch, ultralytics, cv2, PyQt6, ollama | all |
| **Deps *not* required** | — | osmnx, geopandas, shapely, rtree, sqlalchemy, psycopg2, chromadb, sentence-transformers, fastapi, pyarrow | — |

---

## D. Dependency & Startup Map

### D.1 Import-time side effects (executed before any user action)

| # | Location | Effect | Confidence |
|---|---|---|---|
| 1 | `missionState.py:1-2` | `matplotlib.use('QtAgg')` — global backend mutation at import | high |
| 2 | `missionState.py:11-13` | `sys.path.insert(0, app/vision-edge/src)` — path mutation | high |
| 3 | `missionState.py:15` | `from PerceptionProcessing.YoloDetector import YoloDetector` — **not guarded by sim mode**; pulls torch + ultralytics | high |
| 4 | `missionState.py:20-27` | Conditional Agent D import — the only sim guard in the import block | high |
| 5 | `Agents/Agent_D/agent_entry.py:11` | `_SERVICE = AgentDService()` — module-level singleton construction | high |
| 6 | `Agents/Agent_D/main.py:12` | `service = AgentDService()` — a **second**, independent singleton | high |
| 7 | `agent_C/api/main.py:30` | `app = FastAPI(...)` + `@app.on_event("startup")` starts worker + outbox publisher | high |
| 8 | `GUI/Widgets/LeafletMap.py:15-18` | `EC2_TILE_URL` resolved from env at import | high |

### D.2 Constructor-time side effects

| Location | Effect |
|---|---|
| `Dispatcher.__init__` (`:30-41`) | Creates a second asyncio loop and starts `mission_thread` **before any connection exists** |
| `missionState.__init__:234` | Constructs `Dispatcher` unconditionally (even in sim mode) — harmless, `connect()` is lazy |
| `missionState.__init__:236` | `get_agent_d_service()` unless `sim_only` |
| `missionState.__init__:258` | `subprocess.Popen(uvicorn …)` unless `sim_only` — **spawns a network service from a constructor** |
| `missionState.__init__:261-271` | Starts two daemon polling threads unless `sim_only` |
| `LeafletMap.__init__` (~`:366`) | `has_internet()` → opens a socket to `8.8.8.8:53` with 3 s timeout |

### D.3 Thread / event-loop topology

| Thread | Loop | Owner | Touches |
|---|---|---|---|
| Main (Qt) | `QApplication.exec()` | `GUI.run()` | All widgets |
| `dispatcherThread` | `missionState.loop` | `run_asyncio_loop()` | `Dispatcher.receive_packets()` → `master.recv_match()` |
| `mission_thread` | `Dispatcher.loop` | `_run_mission_loop()` | `upload_mission`, `takeoff`, **`wait_for_arming()` → `master.recv_match()`** |
| `_detection_poll_thread` | — | daemon | HTTP :8081, Agent D ingest, `gui.addDetectedPOI()` (blocks 30 s on main thread) |
| `_health_poll_thread` | — | daemon | HTTP :8081, psycopg2 to EC2 |
| `ThreadPoolExecutor` (ad hoc) | — | `handle_image_detection` | ollama call, then `.result()` — **blocks the caller** |

> **Two threads call `recv_match()` on the same non-thread-safe `mavutil` connection.** See Risk #2.

### D.4 Environment variables (complete, as of `6ff44022`)

| Variable | Read at | Default | Notes |
|---|---|---|---|
| `VITALS_SIM_ONLY` | `missionState.py:20` | unset | **New on this branch.** Only import-level switch |
| `VITALS_POSTGIS_URL` / `POSTGIS_URL` / `DATABASE_URL` | `postgis_handler.py:16-20`, `Tests/conftest.py:15` | `postgresql://renderer:[REDACTED]@18.220.206.190:5432/gis` | hard-coded fallback |
| `VITALS_AUTO_INSTALL_TILE_SQL` | `postgis_handler.py:42` | `"0"` | off |
| `VITALS_POSTGIS_CONNECT_TIMEOUT` | `conftest.py:19` | `3` | |
| `TILE_SERVER_URL` | `LeafletMap.py:15` | `http://18.220.206.190:8080/tile/...` | |
| `VITALS_SCHEMA_ROOT` | `agent_b_service.py:40` | `BASE_DIR/schemas` — **wrong since the move** | see Risk #6 |
| `VITALS_CHROMA_PATH`, `VITALS_PARQUET_DIR`, `VITALS_INGEST_DEDUPE_DB`, `VITALS_DEBUG_META`, `VITALS_EMBED_MODEL`, `VITALS_RERANK_MODEL`, `VITALS_CHROMA_COLLECTION`, `VITALS_MAX_RERANK_K`, `VITALS_MISSION_ID` | Agent B | various | all under wrong `BASE_DIR` |
| `VITALS_TCP_ENABLED/HOST/PORT/BATCH_SIZE/BATCH_TIMEOUT` | `tcp_listener.py:24-33` | `0.0.0.0:9000` | |
| `AGENT_D_AGENT_C_URL`, `AGENT_C_PUBLISH_URL`, `AGENT_C_MESSAGES_URL`, `AGENT_D_AGENT_B_INGEST_URL`, `AGENT_B_BASE_URL`, `AGENT_D_TIMEOUT_S`, `AGENT_B_TIMEOUT_S`, `AGENT_C_API_KEY`, `AGENT_D_AGENT_C_API_KEY` | `Agent_D/service.py:116-129` | `None`/empty | egress disabled by default |
| `VITALS_API_KEY` | `toggle_osm.py:7` | **imported but unused** — `API_KEY` is hard-coded on line 7 | |
| `SITL_HOME`, `SITL_MODEL`, `SITL_SPEEDUP`, `SITL_INSTANCE`, `MAVPROXY_TCP_PORT`, `ARDUCOPTER_BIN`, `SITL_DEFAULTS`, `RUN_DIR` | `sitl/entrypoint.sh` | documented | clean |

**There is no environment variable for the MAVLink endpoint.** `Dispatcher.connect()` (`:48-104`) hard-codes a fixed probe list in both platform branches. This is the single highest-leverage configuration gap in the codebase.

### D.5 Hard-coded endpoints (non-SITL)

| Path | Value |
|---|---|
| `missionState.py:37-38` | AWS API Gateway URL + **plaintext API key** *(value redacted in this report)* |
| `toggle_osm.py:6-7` | the same URL + the same key (duplicated) *(value redacted in this report)* |
| `missionState.py:276` | `OSM_HOST = "18.220.206.190"` — no env override (inconsistent with `postgis_handler`) |
| `missionState.py:278, 404`; `langChainMain.py:6` | `http://localhost:8081` ×3 |
| `missionState.py:345` | uvicorn bound to `0.0.0.0:8081` |
| `postgis_handler.py:20`; `conftest.py:11` | `renderer:[REDACTED]@18.220.206.190:5432/gis` |
| `LeafletMap.py:18, 89-90, 370` | EC2 tiles; **unpkg.com CDN**; `localhost:8080` |
| `Utils/check_internet.py:6` | `8.8.8.8:53` |
| `Dispatcher.py:50-64` | 4–6 MAVLink targets, platform-dependent |

---

## E. Execution Path Traces

### (a) SITL GUI connection and heartbeat — **works**

```
run_sim.py:3          os.environ["VITALS_SIM_ONLY"] = "1"
run_sim.py:5-6        import GUI, missionState    ← still loads torch/ultralytics (Risk #1)
run_sim.py:9-11       GUI() → missionState(gui, sim_only=True) → gui.link_mission_state()
HomePage.start_simulation()        gui.isSimulation = True; show_map_page()
GUI.show_map_page:87               os.makedirs("missions/<ts>")   ← lowercase; see Risk #9
MapPage connect_button → GUI.call_mavlink_connection:137
missionState.connect_to_mavlink:614 → Dispatcher.connect():48
  Dispatcher.connect:58             glob /dev/cu.usbserial*, /dev/cu.usbmodem*   ← probed FIRST
  Dispatcher.connect:60             + tcp:14450 (5 s timeout) → tcp:14550 ✅
  Dispatcher.connect:81-99          store sys/comp id; request_data_stream_send(ALL, 4 Hz)
missionState:617-619               start dispatcherThread → receive_packets()
Dispatcher.receive_packets:135     HEARTBEAT → missionState.updateDroneStatus → addDrone → gui.addDrone
Dispatcher.receive_packets:144     GLOBAL_POSITION_INT → updateDronePosition → GUI._Invoker → map centers
```

**Expected latency:** ~5 s (one failed `tcp:14450` probe) with no USB serial attached; longer per attached serial device. **Confidence: high.**

### (b) Minimal mission upload and waypoint progress — **only one viable route**

```
MapPage.open_debug_popup:530 → DebugDialog          ← visible only when gui.isSimulation (MapPage:693)
  "Add Test Job" → GUI.call_create_test_job:357
    → missionState.test_add_job:784   use_waypoints ∈ {1,2,3} selects a hard-coded UCF preset
    → Job(...) → Drone.addJob → Drone.setActiveJob:115
    → missionState.send_waypoints:751 → Dispatcher.send_mission:220
        stop_current_mission:270   set_mode GUIDED(4); wait_for_mode; mission_clear_all_send
        upload_mission:293         insert home waypoint at seq 0; mission_count_send
        handle_mission_request:340 ← per-seq MISSION_REQUEST → send_waypoint:352 (mission_item_int_send)
        handle_mission_ack:390     MAV_MISSION_ACCEPTED → start_mission:236
        start_mission:236          if system_status==3 → takeoff() [see (c) blocker]
                                   else set_mode AUTO(3); set_max_velocity; MAV_CMD_MISSION_START
  progress: MISSION_ITEM_REACHED → handle_reached_waypoint → Drone.setLastWaypoint → GUI.updateJobs
  completion: MISSION_CURRENT.mission_state==5 → handle_mission_state_update → setJobComplete
```

- **"Send Waypoints" is broken** (Risk #4) — `get_debug_waypoints()` returns `int`.
- **Polygon→search-plan route is unavailable in sim mode** (Risk #3) — `agent_d is None`.
- `Drone.setActiveJob:115-122` has an off-by-one: `range(last_waypoint, len(waypoints))` indexing `waypoints[i-1]` drops the final waypoint on resume. **Confidence: medium** (resume path, not exercised by the happy path).

### (c) Return to launch — **works, simplest path in the system**

```
GUI.call_return_to_launch:331 → missionState.return_to_launch:757 → Dispatcher.return_to_launch:516
  guard: if not self.master → log and return
  self.master.mav.set_mode_send(drone_id, MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, 6)   # RTL
```

Also reachable via `missionState.call_drone_home:853` (sets `available=False` first), `end_mission:899` (all drones), and `on_search_traversal_complete:887`. **No ack is awaited and no mode confirmation is checked** — fire-and-forget. **Confidence: high.**

### (d) Real-drone connection and telemetry — **unchanged by this branch**

Identical to (a) except: `missionState.__main__:1051` calls `toggle_database('start')` (AWS EC2 spin-up) before constructing the GUI; `sim_only=False` so Agent B spawns and both poll threads start; `Dispatcher.connect()` finds `/dev/cu.usbserial*` at 57600 baud (RFD900x) on the first probe. Telemetry fan-out is the same `receive_packets` → `missionState` → `GUI._Invoker` → Qt main thread chain.

---

## F. File & Directory Classification

Legend: **CE** Core/essential · **RD** Real-drone only · **SIM** SITL/student only · **OPT** Optional feature · **DEV** Dev/test infra · **GEN** Generated artifact · **LEG** Legacy/uncertain

| Path | Class | Size/LOC | Evidence | Confidence |
|---|---|---|---|---|
| `app/missionState.py` | **CE** | 1069 | Entry point + model + orchestrator | high |
| `app/Dispatcher/Dispatcher.py` | **CE** | 597 | Sole MAVLink implementation | high |
| `app/GUI/` (GUI, Pages, Widgets, Entities, theme) | **CE** | ~2,270 | Only UI | high |
| `app/models/jobs/{job,job_queue}.py` | **CE** | 145 | Imported by `missionState:34-35` | high |
| `app/Utils/coordinate_estimation.py` | **CE** | 100 | `calculate_distance_between_points` used in POI dedupe | high |
| `app/Utils/check_internet.py` | **CE** | 11 | Tile-server selection | high |
| `app/run_sim.py` | **SIM** | 16 | New sim entry | high |
| `app/sitl/{Dockerfile,entrypoint.sh,docker-compose.sitl.yml}` | **SIM** | 433 | Self-contained harness | high |
| `app/sitl/README.md` | **SIM / stale** | 154 | Describes Tk GUI + `ComputerVision.objectDetection`, both absent here | high |
| `app/sitl/mac-venv-vitals-main.freeze.txt` | **LEG** | 92 | No PyQt6 → `main`-branch snapshot | high |
| `app/Agents/Agent_D/{service,agent_entry}.py` | **OPT** | 688 | Guarded out in sim mode | high |
| `app/Agents/Agent_D/CostMaps/{pathing/path,pathing_CostMap,terrain_CostMap}.py` | **OPT** | 1,076 | Imported only by Agent D service | high |
| `app/Agents/Agent_D/OSM_Database/` | **OPT** | ~800 + SQL | PostGIS/osmnx terrain | high |
| `app/Agents/Agent_D/Visualizer/visualization.py` | **OPT** | 1000 | `showPathVisualization` only | high |
| `app/Agents/Agent_D/Visualizer/visualizationsave.py` | **LEG** | 399 | No importer found | medium |
| `app/Agents/Agent_D/Visualizer/disambiguation.py` | **LEG** | 29 | No importer found | medium |
| `app/Agents/Agent_D/CostMaps/pathing/testing/pathing_visualization_demo.py` | **DEV** | **1957** | Largest .py in repo; standalone demo | high |
| `app/Agents/Agent_D/CostMaps/pathing/testing/*.gif` | **GEN** | 837 KB | Simulation render output | high |
| `app/Agents/Agent_D/schemas/acpV0.1/` | **LEG** | 496 | v0.1 superseded by `app/schemas/acp/v0.2/`; no importer | medium-high |
| `app/Agents/Agent_D/main.py` | **LEG** | 28 | FastAPI app no compose service builds | medium |
| `app/Agents/agent_B/` | **OPT (RD)** | ~1,490 | Real detection ingest from Jetson | high |
| `app/Agents/agent_C/` | **OPT** | ~1,000 | No caller in app code | high |
| `app/Agents/agents_common/schema_validator.py` | **CE-for-agents** | 234 | Used by Agent B + D | high |
| `app/Agents/agents_tools/` | **DEV** | 922 | E2E harnesses, datastore wipe | high |
| `app/LangGraph/langChainMain.py` | **OPT** | 180 | Chat sidebar + image captioning | high |
| `app/LangGraph/{langChaintest,langGraphMain}.py` | **LEG** | 154 | Need `langchain_core`/`langgraph` — **not in requirements.txt**; no importer | high |
| `app/schemas/{acp,mcp,agentb.api}/` | **CE-for-agents** | 12 files | Runtime-validated | high |
| `app/Tests/` (4 files) | **DEV** | 895 | Agent D + PostGIS only | high |
| `app/pytest.ini` | **DEV** | 6 | `testpaths = Tests` | high |
| `app/Dockerfile` | **LEG** | 68 | **No compose service references it** | high |
| `app/docker-compose.yml` | **LEG** | 51 | Pulls `gersh01/*` images; `agent-a` no longer exists in repo | high |
| `app/Agents/Agent_D/OSM_Database/docker-compose.yml` | **OPT** | 24 | Port 5432 collides with the above | high |
| `app/test_container.sh` | **DEV** | 87 | CI-invoked | high |
| `app/test_get.py` | **LEG/dead** | 38 | Imports deleted `TerrainPreProcessing.*` | high |
| `app/toggle_osm.py` | **RD** | 37 | Duplicate of `missionState.toggle_database` | high |
| `app/assets/*.png` (6) | **CE** | 345 KB | Icons loaded at runtime | high |
| `app/vision-edge` (submodule) | **CE (unconditionally)** | gitlink | `missionState.py:15` | high |
| `app/jetson-containers` (submodule) | **LEG/broken** | gitlink | **Not declared in `.gitmodules`** | high |
| `app/mav.tlog`, `app/mav.tlog.raw` | **GEN** | **38.2 MB** | MAVLink session logs | high |
| `app/mav.parm` | **GEN** | 1037 lines | Parameter dump | high |
| `app/cache/*.json` (59) | **GEN** | **8.5 MB** | Overpass API responses (osmnx cache) | high |
| `app/missions/**/*.jpg` (41) | **GEN** | **30.1 MB** | Mission POI captures; `.gitignore` already lists `app/missions/` | high |
| `app/__pycache__/`, `app/models/jobs/__pycache__/` | **GEN** | 44 KB | `.pyc`, already in `.gitignore` | high |
| `CDR_GUI.md` | **DEV/doc** | 526 | Design-review deck; accurate history | high |
| `JOB_REFACTORING_DOCUMENTATION.md` | **DEV/doc** | 105 | Accurate | high |
| `app/README.md` | **CE/doc, stale** | 33 | Only install doc; no SITL, Docker, submodule, or Agent B | high |
| `.github/workflows/main.yml` | **DEV** | 86 | See Risk #5 | high |

---

## G. Artifact & Repository Hygiene Report

**Tracked tree: 78.7 MB / 246 files. Generated artifacts: 76.8 MB = 97.6%. `.git` pack: 607.6 MB.**

### Safe to remove with high confidence (untrack; keep on disk)

| Target | Size | Evidence | Risk | Validation |
|---|---|---|---|---|
| `app/mav.tlog`, `app/mav.tlog.raw` | 38.2 MB | pymavlink session logs; no code reads `mav.tlog` | none | `git grep -n "mav\.tlog"` → 0 hits |
| `app/missions/**` (41 jpg) | 30.1 MB | `.gitignore` already lists `app/missions/` and `*.jpg`; created at runtime by `GUI.show_map_page:87` | none | Run a mission; dir is recreated |
| `app/cache/*.json` (59) | 8.5 MB | Overpass payloads; osmnx default `./cache`; `.gitignore` has `*.json` + schema exceptions | none | Delete, run a terrain query, confirm refill |
| `app/__pycache__/`, `app/models/jobs/__pycache__/` | 44 KB | `.pyc` for py3.13 while Dockerfile pins 3.11 | none | `git rm -r --cached`; imports unaffected |
| `app/mav.parm` | 1,037 lines | Parameter dump, no reader | none | `git grep "mav.parm"` → 0 hits |
| `.../pathing/testing/pathing_simulation_*.gif` | 837 KB | Render output of the adjacent demo | none | Re-run `pathing_visualization_demo.py` |

### Candidates requiring validation

| Target | Evidence | Risk if removed | Validation test |
|---|---|---|---|
| `app/test_get.py` | Imports `TerrainPreProcessing.terrain_queries` / `.visualization` — **directory deleted on this branch** | none functionally; **but** the `test_` prefix means a root-level `pytest` run collects it and errors at import | `cd app && python -c "import test_get"` → `ModuleNotFoundError` |
| `app/Dockerfile` | No `build:` directive anywhere in either compose file; ARM64 branch installs a hand-maintained list missing PyQt6/fastapi/shapely; `CMD python3 missionState.py` launches a GUI headless | loses a (currently non-functional) container path | `docker compose config` → confirm no service references it |
| `app/docker-compose.yml` `agent-a` service | `app/Agent_A` removed in `35001677` | none | `git log --diff-filter=D -- 'app/Agent_A*'` |
| `app/Agents/Agent_D/schemas/acpV0.1/` | Superseded by `app/schemas/acp/v0.2/`; no importer | breaks nothing found | `git grep -n "acpV0\.1\|acp_A\|acp_B\|acp_C"` |
| `app/LangGraph/{langChaintest,langGraphMain}.py` | Require `langchain_core`/`langgraph`, absent from `requirements.txt`; `LangGraph/__init__.py` is empty | loses experimental scaffolding | `python -c "import LangGraph.langGraphMain"` → `ModuleNotFoundError` |
| `app/Agents/Agent_D/Visualizer/{visualizationsave,disambiguation}.py` | No importer found | may be a manual tool | `git grep -n "visualizationsave\|disambiguation"` |
| `missionState.POI` class (`:211-219`) | Never instantiated — `MapPage.add_poi:476` constructs `GUI.Entities.POI.POI` | none | `git grep -n "POI("` → only MapPage:476 |
| `GUI/Entities/Job.Job` | Never imported; only `JobWaypoint` is | none | `git grep -n "Entities.Job"` → one import, `JobWaypoint` only |
| `models/jobs/job.JobWaypoint` | Never imported, **and broken** — calls `map_widget.set_marker()`, which `LeafletMap` does not define (it has `add_marker`) | none | `git grep -n "set_marker"` |
| `Dispatcher.mission_item` class (`:11-23`) | Never instantiated | none | `git grep -n "mission_item\b"` |
| `Dispatcher.__main__` (`:596-597`) | `Dispatcher()` takes a required arg; calls misspelled `recieve_packets()` | none | `python Dispatcher/Dispatcher.py` → `TypeError` |
| `Dispatcher.clear_mission` (`:402`) | Body is `self.master.target_system = drone_id` — no clear is sent; no caller | none | `git grep -n "clear_mission"` |
| `app/jetson-containers` gitlink | Absent from `.gitmodules` | clones already get an empty dir | `git submodule status` → not listed |

### Must preserve

`app/sitl/{Dockerfile,entrypoint.sh,docker-compose.sitl.yml}` · `app/schemas/**` (runtime-validated, and `.gitignore` carries explicit `!app/schemas/**/*.json` negations) · `app/assets/*.png` (explicit `!app/assets/*.png` negation; loaded by `HomePage`, `GUI`, `LeafletMap`) · `app/Agents/Agent_D/OSM_Database/sql/vitals_osm_features.sql` · `app/Tests/**` · `Dispatcher.py` in its entirety.

### Duplicates and inconsistencies

| Finding | Locations |
|---|---|
| AWS key + endpoint duplicated verbatim | `missionState.py:37-38`; `toggle_osm.py:6-7` |
| `toggle_database()` implemented twice, identically | `missionState.py:302-330`; `toggle_osm.py:9-30` |
| PostGIS DSN hard-coded twice | `postgis_handler.py:20`; `Tests/conftest.py:11` |
| `JobWaypoint` defined twice, incompatible attribute names | `GUI/Entities/Job.py:9` (`waypointNum`/`marker_id`) vs `models/jobs/job.py:6` (`waypoint_num`/`marker`) |
| `Job` defined twice, unrelated shapes | `GUI/Entities/Job.py:1`; `models/jobs/job.py:16` |
| `POI` defined twice | `missionState.py:211` (dead); `GUI/Entities/POI.py:11` (live) |
| `Drone` defined twice (model vs view — intentional but unnamed) | `missionState.py:40`; `GUI/Entities/Drone.py:6` |
| Port 5432 published by two compose files | `app/docker-compose.yml`; `Agent_D/OSM_Database/docker-compose.yml` |
| Missing `__init__.py` (implicit namespace packages) | `app/Agents/`, `app/models/`, `app/models/jobs/`, `app/Tests/`, `app/Agents/agent_B/storage/`, `.../CostMaps/pathing/`, `.../pathing/testing/`, `.../schemas/acpV0.1/`, `app/Agents/agents_tools/agent_b/` |
| `.dockerignore` omits the 77 MB of artifacts | `app/.dockerignore` excludes only `__pycache__`; `mav.tlog*`, `missions/`, `cache/`, `vision-edge/` all enter the build context |

### Obsolete documentation

| Doc | Problem |
|---|---|
| `app/README.md` | Says run `python missionState.py` + configure Mission Planner. No mention of `run_sim.py`, SITL, Docker, PostGIS, Agent B, or the required `vision-edge` submodule init. **This is the only install doc a student will find.** |
| `app/sitl/README.md` | Byte-identical port from `feature/vitals-sitl`. References `feature/vitals-sitl`/`d90ab562`, "native Mac Tk GUI", `tkintermapview`, and `ComputerVision.objectDetection` — none of which exist at `6ff44022` |
| `app/sitl/mac-venv-vitals-main.freeze.txt` | 92 pins including `customtkinter`, `tkintermapview`, **no PyQt6** |
| `requirements.txt:17-18` | Still pins `tkintermapview` and `customtkinter`; the only reference left is a docstring at `LeafletMap.py:3` |
| `CDR_GUI.md` | Accurate as history — keep, but mark as a point-in-time artifact |

---

## H. Dangerous Coupling

| # | Coupling | Location | Why it blocks independent simulation |
|---|---|---|---|
| 1 | Unconditional `vision-edge` import | `missionState.py:11-15` | Sim mode still needs the submodule + torch + ultralytics. Placed *above* the sim guard at line 20 |
| 2 | MAVLink endpoint not configurable | `Dispatcher.py:50-64` | No way to pin the app to SITL; serial is probed first, so an attached radio wins over the simulator |
| 3 | `agent_d` nullable but dereferenced unguarded | `missionState.py:236` vs `:681, 950, 1008` | Polygon → `AttributeError` |
| 4 | `Interactive_Visualization = None` in sim mode | `missionState.py:26` vs `:692` | "View Path Plan" → `TypeError` |
| 5 | Network service spawned from a constructor | `missionState.py:258` | `subprocess.Popen(uvicorn …)` binds `0.0.0.0:8081` as a side effect of object construction |
| 6 | DNS probe during widget construction | `LeafletMap.py:~366` → `check_internet.py:6` | 3 s stall on an air-gapped machine |
| 7 | CDN dependency in the map | `LeafletMap.py:89-90` | Leaflet itself always loads from `unpkg.com`; the offline branch only swaps *tiles*, so the map is blank offline |
| 8 | Module-level service singletons | `agent_entry.py:11`, `Agent_D/main.py:12` | Import = construction; two independent instances if both are loaded |
| 9 | Two "simulation" flags with different meanings | `gui.isSimulation` (mission type) vs `missionState.sim_only` (dependency skip) | `run_sim.py` sets only the latter; the Debug Menu's visibility depends on the former |
| 10 | Blocking cross-thread call | `GUI.addDetectedPOI:232` | Worker thread blocks up to 30 s on a `threading.Event` serviced by the Qt main thread |

**Dynamic imports** (all benign, all local, all inside functions): `MapPage.py:497, 587-588` (matplotlib Qt backend), `GUI.py:302-303` (`QMenu`/`QCursor`), `LeafletMap.py:~367` (`check_internet`), `missionState.py:87` (`import time` inside `updatePosition`), `_poll_service_health:275` (`import psycopg2`). No `importlib`, no `__import__`, no `eval`-based loading anywhere.

---

## I. Top Risks & Technical Debt (ranked by impact × confidence)

> ### Risk #1 — Live AWS API Gateway key committed in plaintext
>
> `app/missionState.py:37-38`, `app/toggle_osm.py:6-7` — a 40-character API key *(value redacted in this report; read it at either source line)* against an `execute-api.us-east-2.amazonaws.com` endpoint. Grants EC2 start/stop. Present in the full git history, so removal from HEAD is insufficient.
>
> `toggle_osm.py:3` imports `os` and the comment on line 7 says *"It is safer to use os.getenv('VITALS_API_KEY')"* — the intent was recorded and never acted on.
>
> A second credential of the same class sits in `postgis_handler.py:20` and `Tests/conftest.py:11`: the PostGIS DSN for `18.220.206.190` *(password redacted here)*.
>
> **Confidence: high. Risk if changed: none (env var is a drop-in). Validation:** `VITALS_API_KEY=… python toggle_osm.py start` returns the same `[+] Success`. **Rotate both credentials regardless of what the code does.**

> ### Risk #2 — Concurrent `recv_match()` on one `mavutil` connection
>
> `Dispatcher.wait_for_arming:550` reads `self.master.recv_match(type="HEARTBEAT", blocking=False)` from `mission_thread`, while `receive_packets:128` drains the same connection from `dispatcherThread` at ~1 kHz (`asyncio.sleep(0.001)`). `wait_for_mode:560` documents this exact hazard and avoids it by reading cached `drone.custom_mode`; `wait_for_arming` was never updated.
>
> Order-of-magnitude: ~2 polls/s vs ~1000/s ⇒ roughly 0.2% capture odds per heartbeat, ~11% over the 60 s window ⇒ **takeoff aborts ~9 times in 10**. It also steals telemetry frames from the main consumer. `mavutil` connections are not thread-safe.
>
> **Confidence: high (race), medium-high (the 60 s abort is the dominant outcome). Risk if changed: low** — mirror `wait_for_mode` and read a cached armed flag set in `receive_packets`. **Validation:** connect to SITL, click Arm then Takeoff; assert `wait_for_arming` returns in <2 s and that `GLOBAL_POSITION_INT` updates never stall.

> ### Risk #3 — Sim mode cannot plan a mission: `agent_d` is `None` but dereferenced
>
> `missionState.py:236` sets `self.agent_d = None` when `sim_only`. Unguarded dereferences: `addMissionPolygon:681`, `_sync_agent_d_session:950`, `register_manual_detection_points:1008`, `_poll_agent_b_detections:462`, `handle_image_detection:~963`.
>
> Call path: `MapPage.start_creating_polygon:333` → `GUI.sendMissionPolygon:154` → `addMissionPolygon` → `AttributeError` raised inside a Qt slot with no `sys.excepthook` installed. PyQt ≥5.5 routes unhandled slot exceptions to `excepthook` and then aborts — **expect process termination, not a caught error**.
>
> `finish_adding_detection_points:316` *does* catch it, but `GUI.call_start_mission:379-383` continues anyway into `startSearchMission()` → `deployInitialPaths()` with an empty `drone_search_destinations` ⇒ zero waypoints, silent no-op.
>
> **Confidence: high on the `AttributeError`; medium-high on process abort. Risk if changed: low** — a null-object `AgentD` stub preserves real-mode behavior exactly. **Validation:** `python run_sim.py`, choose Simulation, place GCS, draw a 3-point polygon; the app must stay up and report "terrain planning unavailable in simulation mode".

> ### Risk #4 — "Send Waypoints" debug button passes an `int` where a list is required
>
> `MapPage.get_debug_waypoints:547-555` returns `int(text)`. `GUI.call_send_waypoints:321-324` forwards it to `missionState.send_waypoints:751` → `Dispatcher.send_mission:220` → `upload_mission:293` → **`waypoints.insert(0, …)` at line 316** → `AttributeError: 'int' object has no attribute 'insert'`. Raised inside a coroutine scheduled by `run_coroutine_threadsafe`, so it surfaces only as an unretrieved-task warning: **the button silently does nothing**.
>
> The same getter feeds `call_create_test_job` (which *wants* an int selector) and `call_investigate_poi` (which wants a POI id) — one widget serving three incompatible contracts.
>
> **Confidence: high. Risk if changed: low. Validation:** click "Send Waypoints" against SITL; expect `MISSION_COUNT` on the wire.

> ### Risk #5 — CI starts cloud infrastructure on every push and can leave it running
>
> `.github/workflows/main.yml` runs `python toggle_osm.py start` (line ~62) on `on: push` for **all branches**. The final `Stop OSM-Dev server` step (line ~84) lacks `if: always()`, while `docker compose down` directly above it has it. Any failure in `pytest -v ./app/Tests/` leaves the EC2 instance running.
>
> Secondary: the "Build Docker Compose services" step is a no-op — no service in `app/docker-compose.yml` has a `build:` key, so CI pulls `gersh01/*` images and never compiles repository code. `pytest` is invoked from the repo root while `pytest.ini` (with `pythonpath = .`) lives in `app/`, so `rootdir`/`pythonpath` resolution differs from local runs.
>
> **Confidence: high. Risk if changed: low** — add `if: always()`. **Validation:** force a test failure on a branch; confirm the stop step still executes.

> ### Risk #6 — Agent B's `BASE_DIR` was not updated when the package moved
>
> `agent_b_service.py:38`: `BASE_DIR = Path(__file__).resolve().parents[1]  # .../app`. The file moved from `app/agent_b/` to `app/Agents/agent_B/` in this branch's history, so `parents[1]` now resolves to **`app/Agents`**, not `app`. Consequences: default `VITALS_SCHEMA_ROOT` → `app/Agents/schemas` (does not exist); Chroma → `app/Agents/agent_b/chroma_data`; Parquet → `app/Agents/agent_b/data/lake/events`. `.gitignore`'s `app/agent_b/data/` rule no longer matches, so **runtime data can become trackable**.
>
> `missionState._start_agent_b:339` sets `VITALS_SCHEMA_ROOT` explicitly, which masks the schema half of the bug when launched from the GUI — but not when Agent B is run standalone per `Start_Agent_B.txt`.
>
> **Related, Linux-only:** that same launcher runs `uvicorn agent_b.agent_b_service:app` with `cwd=app/Agents`, but the directory is `agent_B`. This resolves on case-insensitive macOS and **fails on Linux/CI**.
>
> **Confidence: high. Risk if changed: medium** — changing `BASE_DIR` relocates existing Chroma/Parquet stores; migrate or re-ingest. **Validation:** `cd app/Agents && python -c "from pathlib import Path; print(Path('agent_B/agent_b_service.py').resolve().parents[1])"`.

> ### Risk #7 — No test covers MAVLink, mission upload, RTL, or `missionState`
>
> `app/Tests/` holds 4 files (895 lines), all Agent D / PostGIS, two of which skip without a reachable database (`conftest.require_reachable_postgis`). The safety-critical surface — `Dispatcher` (597 lines) and `missionState` (1069 lines) — has none. Every Stage-3 refactor below is therefore unverifiable today.
>
> **Confidence: high. Risk: this is the gating constraint on the whole roadmap.**

> ### Risk #8 — The map requires public internet even in "offline" mode
>
> `LeafletMap.py:89-90` loads `leaflet.css` and `leaflet.js` from `https://unpkg.com/leaflet@1.9.4/`. The `has_internet()` branch at line 370 only switches the **tile** URL. With no internet the tile fallback is selected and the library never loads ⇒ blank map.
>
> **Confidence: high. Risk if changed: low** — vendor Leaflet into `app/assets/` and inline it like `_load_qwebchannel_js()` already does. **Validation:** disable networking, launch, confirm the basemap renders against a local tile server.

> ### Risk #9 — `Missions/` vs `missions/` case collision
>
> `GUI.show_map_page:87` creates `missions/<id>`; `missionState.addPOI:832` and `handle_image_detection:983,995` write `Missions/<id>/POIs/...`; `GUI/Entities/POI.py:75` reads `./Missions/<id>/POIs/<id>/`. Identical on default macOS APFS, **two separate trees on Linux** ⇒ POI images written where the viewer never looks.
>
> **Confidence: high. Risk if changed: low. Validation:** on a case-sensitive volume, run a detection and confirm one directory.

> ### Risk #10 — Latent crashes on paths that are currently unreachable
>
> - `missionState.py:987` calls `poi.target_found(drone_id)`; `GUI/Entities/POI.POI` defines only `__init__`, `_on_marker_click`, `open_popup`. Fires once `positive_flags >= 3`.
> - `missionState.send_poi_investigate:759-760` calls `self.dispatcher.send_poi_investigate(...)`; **`Dispatcher` has no such method**. Currently has no caller.
> - `missionState.setDetectionPoints:1001` is never called ⇒ `self.detectionPoints` is permanently `[]` ⇒ the proximity-triggered simulated-detection block at `:661-670` is **unreachable**, and `trigger_image_detection:920` points at `ComputerVision/temp/…`, a directory deleted on this branch (`GUI.call_simulate_image_detection:349` uses a third, also-missing path, `./temp/…`).
> - `postgis_handler._sql_file_path:24` returns `sql/vitals_tile_grid.sql`; the tree ships `sql/vitals_osm_features.sql`. Gated behind `VITALS_AUTO_INSTALL_TILE_SQL`, default off.
>
> **Confidence: high on each. Risk: none today; these are tripwires for whoever re-enables the feature.**

> ### Risk #11 — `Drone.setActiveJob` resume off-by-one
>
> `missionState.py:115-122`: `for i in range(self.active_job.last_waypoint, len(self.active_job.waypoints)): payload.append(self.active_job.waypoints[i-1])` — shifts the window down by one and drops the last waypoint. Only on job resume after a pause.
>
> **Confidence: medium-high (clear off-by-one; not exercised by the happy path). Risk if changed: medium** — resume semantics are untested. **Validation:** pause a 5-waypoint job at wp 3, resume, assert the uploaded set is wp 3,4,5.

> ### Risk #12 — `run_sim.py` can still connect to a physical aircraft
>
> `Dispatcher.connect:58-64` probes `/dev/cu.usbserial*` and `/dev/cu.usbmodem*` **before** `tcp:127.0.0.1:14550`. `run_sim.py` adds no guard. This directly contradicts `app/sitl/README.md`'s own rule — *"Never connect a physical aircraft during simulator work."* The README states the rule; nothing enforces it.
>
> **Confidence: high. Risk if changed: low** — honor `VITALS_SIM_ONLY` in `connect()` and restrict the probe list to loopback TCP. **Validation:** attach a USB serial device, run `run_sim.py`, assert the log shows only `tcp:127.0.0.1:…` targets.

---

## J. SITL Branch Assessment

**Topology.** `feature/sitl-new-working` forks from `edec7148` and carries the full `new-working` lineage. It contains every commit in `main` except the merge commit `d90ab562` itself. Five commits are unique to it:

```
ba37034e  sitl: port Docker ArduCopter SITL harness onto new-working
3d89ebe4  Add simulation mode to skip Agent B and OSM polling
190547d5  Add simulation-only GUI launcher
9c9b8e12  Skip Agent D imports in simulation mode
6ff44022  Verify simulation-mode state construction
```

**Application-code delta: 2 files.** `git diff fd236b01 6ff44022 -- . ':(exclude)app/sitl'` touches only `app/missionState.py` (+30/−16) and adds `app/run_sim.py` (+16). `Dispatcher.py`, all of `GUI/`, `models/`, and every agent are untouched.

**Does it weaken live-drone functionality? No.** Every change is behind `sim_only` (a keyword argument defaulting to `False`) or `VITALS_SIM_ONLY == "1"` (unset by default). `missionState.__main__` is unchanged and still calls `toggle_database('start')`, spawns Agent B, and starts both poll threads. One import line was *narrowed* — `plot_search_area, plot_advanced, plot_postGIS_data, plot_drone_paths` were dropped from the `visualization` import — and none of those four symbols appear anywhere else in `missionState.py`. The real-drone path is behaviorally identical to its base.

**Does it isolate simulation? Partially — three gaps.**

1. **Import isolation is incomplete.** The sim guard sits at line 20, but `vision-edge`/`YoloDetector` is imported at line 15 and `cv2`/`matplotlib`/`ollama` unconditionally. Sim mode skips osmnx, geopandas, shapely, rtree, sqlalchemy, psycopg2, chromadb, sentence-transformers, fastapi, and pyarrow — a real win — but still needs torch + ultralytics + PyQt6-WebEngine.
2. **Null-pointer isolation is absent.** Setting `agent_d = None` without a null object leaves five unguarded dereferences (Risk #3). The guard removes the *import*, not the *dependency*.
3. **Transport isolation is absent.** `VITALS_SIM_ONLY` has no effect on `Dispatcher.connect()` (Risk #12).

**The harness itself is the strongest artifact in the repository.** `sitl/entrypoint.sh` identifies and defends against the precise failure mode that matters — MAVProxy outliving a dead `arducopter`, keeping :14550 answering with zero heartbeats so `wait_heartbeat()` blocks forever while every port probe reports healthy. It solves this with PID-tracked supervision plus `restart: "no"`, uses `ss -ltnH` specifically to avoid consuming a SITL connection slot, and documents why `--non-interactive` beats `--daemon`. `docker-compose.sitl.yml` uses a distinct project `name:` so it provably cannot start the main stack, publishes only `127.0.0.1:14550`, and keeps 5760 container-internal. Pins are explicit (`Copter-4.6.3`, `MAVProxy==1.8.75`). Unverified estimates are labeled as estimates. **Keep this and adopt its documentation standard elsewhere.**

**Two stale carry-overs** from the byte-identical port (`git diff feature/vitals-sitl 6ff44022 -- app/sitl` is empty):

- `sitl/README.md` cites `feature/vitals-sitl` / `d90ab562` and describes a Tk GUI, `tkintermapview`, and `ComputerVision.objectDetection` — none of which exist at `6ff44022`.
- `sitl/mac-venv-vitals-main.freeze.txt` has `customtkinter==6.0.0`, `tkintermapview==1.30`, and **no PyQt6** across its 92 pins. A student following it gets an environment that cannot import this branch's GUI.

---

## K. Staged Roadmap

Each stage is behavior-preserving and independently revertible. Stages 1–4 are gated on Stage 0's inventory.

### Stage 0 — Documentation and inventory only *(Days 1–10, no code changes)*

- Rewrite `app/README.md`: three launch modes, `git submodule update --init --recursive`, required services per mode.
- Regenerate `app/sitl/mac-venv-vitals-main.freeze.txt` against a PyQt6 env, or delete it and document the dependency set instead. Update `sitl/README.md` to this branch's stack and commit.
- Publish the env-var table (§D.4) and the hard-coded-endpoint table (§D.5) as `docs/CONFIGURATION.md`.
- **Out-of-band, not a documentation task: rotate the AWS API Gateway key and the PostGIS password now.**
- Add `if: always()` to the CI stop step. One line; prevents a recurring cloud spend.

**Exit:** a new student reaches a SITL heartbeat from the README alone.

### Stage 1 — Remove or relocate unquestionably generated artifacts *(Days 10–20)*

- `git rm --cached` the six "safe to remove" rows in §G: `mav.tlog`, `mav.tlog.raw`, `mav.parm`, `app/cache/`, `app/missions/`, both `__pycache__/`, the pathing GIF. **≈77 MB off the working tree.**
- Add the missing `.gitignore` rules: `app/cache/`, `*.tlog`, `*.tlog.raw`, `*.parm`.
- Extend `app/.dockerignore` to exclude `missions/`, `cache/`, `*.tlog*`, `vision-edge/`.
- Fix the dangling `app/jetson-containers` gitlink: declare it in `.gitmodules` or `git rm --cached` it.
- Defer history rewrite (`git-filter-repo`) — 608 MB of pack is tolerable; a rewrite invalidates every outstanding branch and is not worth it mid-semester. **Caveat:** if the exposed credentials must be purged from history rather than merely rotated, that decision forces the rewrite — sequence it deliberately.

**Exit:** `git ls-tree -r --long HEAD | awk '{s+=$4} END {print s}'` < 3 MB; `git status` clean after a full mission run.

### Stage 2 — Configuration and mode separation *(Days 20–45)*

- **`app/config.py`** — one resolver, env-overridable, defaults preserving today's values exactly: `VITALS_MAVLINK_TARGETS`, `VITALS_AGENT_B_URL`, `VITALS_OSM_HOST`, `VITALS_POSTGIS_URL`, `TILE_SERVER_URL`, `VITALS_API_KEY`.
- **Make `Dispatcher.connect()` configurable** and honor sim mode: when `VITALS_SIM_ONLY`, restrict the probe list to loopback TCP (Risk #12). Keep the current list as the real-mode default.
- **Null-object Agent D** — `NullAgentDService` returning empty sessions, injected when `sim_only`, replacing `None` (Risk #3). Same for `Interactive_Visualization`.
- **Guard the vision import** — move `YoloDetector` behind a lazy accessor so `VITALS_SIM_ONLY` skips torch (Risk #1 in §A's list / Coupling #1).
- De-duplicate `toggle_database` — delete the copy in `missionState.py`, import from `toggle_osm`, read the key from env.
- Fix Agent B `BASE_DIR` (`parents[1]` → `parents[2]`) and rename `agent_B` → `agent_b` for Linux (Risk #6).
- Normalize `Missions/` → `missions/` in all five sites (Risk #9).

**Exit:** `VITALS_SIM_ONLY=1 python run_sim.py` in a venv with **no** torch/osmnx/psycopg2 reaches a SITL heartbeat, draws a polygon without crashing, and never opens a non-loopback socket (verify with `lsof -i -p <pid>`).

### Stage 3 — Extract and test core MAVLink mission-control interfaces *(Days 45–75)*

- **Characterization tests first, against the current `Dispatcher`,** using a fake `mavutil` that records sends and replays canned messages: connect/heartbeat, full upload handshake (`MISSION_COUNT` → n×`MISSION_REQUEST` → `MISSION_ACK`), waypoint progress, RTL, mode transitions. These must pass *before* anything moves.
- Fix Risk #2 (`wait_for_arming` reads cached state, mirroring `wait_for_mode`), Risk #4 (typed waypoint payload from the debug dialog; split the overloaded `get_debug_waypoints` into three getters), Risk #11 (resume off-by-one) — each with a regression test written first.
- Extract `MavlinkTransport` (connect / send / receive) from `MissionProtocol` (upload state machine) from `VehicleCommands` (arm / takeoff / RTL / land / set-speed). Keep `Dispatcher` as a thin façade so `missionState` is untouched.
- Delete confirmed-dead `Dispatcher` members: `mission_item`, `clear_mission`, `ack`, the `__main__` block.
- Add a SITL smoke job to CI (`docker compose -f sitl/docker-compose.sitl.yml up -d`, assert heartbeat, upload 3 waypoints, assert `MISSION_ACK`, RTL, tear down).

**Exit:** the full SITL mission path — connect → arm → takeoff → upload → waypoint progress → RTL — runs green in CI, and the same suite passes against the pre-refactor `Dispatcher`.

### Stage 4 — Optional modules as plugins *(Days 75–90+)*

- Define a `MissionServices` protocol (terrain planning, detection ingest, LLM chat, visualization) with a null implementation per service; `sim_only` selects nulls, real mode selects live ones. Retires the scattered `if sim_only` checks.
- Move Agent B out of `missionState.__init__` into an explicit supervisor started by the entry point, not by a constructor.
- Promote `app/Agents/agent_C` and `app/Agents/Agent_D` to installable packages with their own `pyproject.toml` (Agent C already has one), so `requirements.txt` splits into `core` / `agents` / `vision` extras.
- Vendor Leaflet into `app/assets/` (Risk #8).
- Retire: `app/Dockerfile`, the `agent-a` compose service, `app/test_get.py`, `acpV0.1/`, `langChaintest.py`, `langGraphMain.py` — each only after its §G validation test confirms zero importers.

**Exit:** `pip install -e .` with no extras + `run_sim.py` flies a SITL mission. `pip install -e .[agents,vision]` restores today's full behavior.

### Milestone summary

| Milestone | Ends | Deliverable | Gate |
|---|---|---|---|
| **M1 — Day 10** | Stage 0 | Accurate docs; credentials rotated; CI stop fixed | Student reaches heartbeat from README |
| **M2 — Day 20** | Stage 1 | ~77 MB untracked | Tree < 3 MB; clean `git status` post-mission |
| **M3 — Day 45** | Stage 2 | Config layer; sim runs without heavy deps | Lightweight venv flies SITL; loopback-only sockets |
| **M4 — Day 75** | Stage 3 | Tested, decomposed MAVLink core | SITL mission green in CI |
| **M5 — Day 90+** | Stage 4 | Plugin boundaries; dead code retired | Core-only install flies SITL |

---

## L. Questions That Cannot Be Answered From Code

**Security / operations**

1. Has the AWS API Gateway key been rotated since it was committed? What else can that Gateway reach besides EC2 start/stop, and is the repo public?
2. Is `18.220.206.190` (PostGIS on :5432, tiles on :8080) internet-reachable, and is that intended? Who owns and pays for it?
3. Is the EC2 instance expected to be running continuously, or is `toggle_osm.py` the only lifecycle control? How often has CI left it running?

**SITL and the student workflow**

4. Was the `app/sitl/` harness ever built and run on `feature/sitl-new-working`, or only on `feature/vitals-sitl`? The README records a verified run against `d90ab562` only.
5. Should students run the GUI natively on the host, or is a containerized GUI planned? This decides between the three options enumerated in `docker-compose.sitl.yml:62-68`.
6. Is the `justinUCF/vitals-vision-edge` submodule publicly cloneable by students? If not, sim mode cannot import `missionState` at all today.
7. How many simulated aircraft are needed? `_agent_d_context` assumes `max(len(drones), 4)` and the debug dialog says "Target Drone ID (1-4)", but the harness runs exactly one instance.
8. Is `tcp:127.0.0.1:14550` the intended SITL endpoint, or should SITL move to a distinct port so it can never be confused with QGroundControl forwarding on the same address?

**Intent and ownership**

9. Was the RC-arm-then-takeoff flow (`Dispatcher.takeoff:421-446`, with its printed "ARM using RC transmitter" banner) a deliberate safety interlock for real flight? If so, SITL needs an explicit bypass rather than a bug fix.
10. Is the `detectionPoints` proximity-trigger path (`missionState:661-670`, fed only by the never-called `setDetectionPoints:1001`) intentionally retired in favor of the Agent D route, or was it orphaned during the Agent D migration?
11. Are `Agent_D/Visualizer/visualizationsave.py` and `disambiguation.py` manual analysis tools, or leftovers?
12. Is `app/Dockerfile` meant to be revived (no compose service builds it, and its ARM64 branch cannot run the PyQt6 GUI), or superseded by the `gersh01/*` images?
13. Who builds and publishes `gersh01/vitals-gcs`, `gersh01/agent-a|b|c|d`? Which commits are they built from? `agent-a` no longer exists in this repo.
14. Is `feature/vitals-sitl` or `feature/sitl-new-working` the intended merge candidate? They are divergent SITL ports onto different bases, with identical `app/sitl/` contents.
15. Is Agent C (`app/Agents/agent_C/`, ~1,000 lines, no caller in application code) active work, or parked? Same for the Jetson TRT-LLM client it targets.
16. What is the real target OS for deployment? Several defects (Agent B `agent_b`/`agent_B`, `Missions`/`missions`) are invisible on macOS and fatal on Linux.
17. Is there a flight-test log or acceptance checklist recording which of mission upload, arming, takeoff, waypoint progression, and RTL have been confirmed on real hardware? `sitl/README.md` is explicit that none of them are proven by the simulator, and the code carries no evidence either way.

---

*End of report.*
