import matplotlib
matplotlib.use('QtAgg')

import os
import sys
import random
import requests
from datetime import datetime, timezone

# Add vision-edge submodule to Python path (hyphenated dir name can't be imported directly)
_vision_edge_src = os.path.join(os.path.dirname(__file__), "vision-edge", "src")
if _vision_edge_src not in sys.path:
    sys.path.insert(0, _vision_edge_src)

from PerceptionProcessing.YoloDetector import YoloDetector
from GUI.GUI import GUI
from Dispatcher import Dispatcher
import asyncio
import threading
from Agents.Agent_D.agent_entry import get_service as get_agent_d_service
from Agents.Agent_D.service import AgentDError
from Agents.Agent_D.Visualizer.visualization import plot_search_area, plot_advanced, plot_postGIS_data, plot_drone_paths
from Agents.Agent_D.Visualizer.visualization import Interactive_Visualization
from LangGraph import langChainMain
import concurrent.futures
import subprocess
import time as _time
from Utils import coordinate_estimation
import cv2
from models.jobs.job_queue import JobQueue
from models.jobs.job import Job

API_ENDPOINT = "https://ikh1sc3052.execute-api.us-east-2.amazonaws.com/default/"
API_KEY = "uLvKjXwS1B0uAXh7Uteu6dOJWyCerhx5GW2lrZ64"

class Drone:
    drone_id = None
    system_status = None
    custom_mode = None
    latitude = None # Note: this is not a float, it is a int with 7 decimal places
    longitude = None # Note: this is not a float, it is a int with 7 decimal places
    altitude = None # millimeters above sea level
    relative_altitude = None # millimeters above home
    heading = None # degrees
    vx = None # cm per second
    vy = None # cm per second
    vz = None # cm per second
    roll = None  # Roll angle in degrees
    pitch = None  # Pitch angle in degrees
    yaw = None  # Yaw angle in degrees
    home_latitude = None # Note: this is not a float, it is a int with 7 decimal places
    home_longitude = None # Note: this is not a float, it is a int with 7 decimal places
    jobQueue = None
    active_job = None
    last_mission_state = None
    available = True
    operatingAltitude = 10 # meters
    maxVelocity = 10.0 # m/s
    visionModel = "rf3v1.pt"

    def __init__(self, missionState, drone_id, system_status, operatingAltitude):
        self.missionState = missionState
        self.drone_id = drone_id
        self.system_status = system_status
        self.operatingAltitude = operatingAltitude
        self.jobQueue = JobQueue()
        self.position_history = []
        self._last_history_time = 0

    #SETTERS
    def updatePosition(self, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz):
        self.latitude = latitude
        self.longitude = longitude
        self.altitude = altitude
        self.relative_altitude = relative_altitude
        self.heading = heading
        self.vx = vx
        self.vy = vy
        self.vz = vz

        has_valid_gps_fix = latitude not in (None, 0) and longitude not in (None, 0)
        if self.home_latitude is None and has_valid_gps_fix:
            self.home_latitude = latitude
            self.home_longitude = longitude
        # Record position every 2 seconds for mission report
        import time
        now = time.time()
        if now - self._last_history_time >= 2:
            self._last_history_time = now
            self.position_history.append((latitude, longitude))
        self.missionState.gui.updateDronePosition(self.drone_id, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz)

    def updateTelemetry(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw
        self.missionState.gui.updateDroneTelemetry(self.drone_id, roll, pitch, yaw)

    def updateStatus(self, system_status, custom_mode=None):
        self.system_status = system_status
        if custom_mode is not None:
            self.custom_mode = custom_mode
        self.missionState.gui.updateDroneStatus(self.drone_id, system_status)
    
    def addJob(self, job):
        if self.active_job is None and self.available:
            self.setActiveJob(job)
        elif self.available and self.active_job is not None and (int(job.job_priority) - self.active_job.job_priority) > 3:
            # if the new job has a higher priority than the active job, pause the active job
            self.setActiveJob(job)
        else:
            self.jobQueue.add_job(job)
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())

    def setActiveJob(self, job):
        if self.active_job is not None:
            self.pauseJob()
        job.job_status = "loading"
        self.active_job = job
        waypoint_payload = []
        # append waypoints from last waypoint to the end of the list
        if self.active_job.last_waypoint > 1:
            for i in range(self.active_job.last_waypoint, len(self.active_job.waypoints)):
                waypoint_payload.append(self.active_job.waypoints[i- 1])
        else:
            waypoint_payload = self.active_job.waypoints
        # send the waypoints to the drone
        self.missionState.send_waypoints(self.drone_id, waypoint_payload)
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
    
    def updateJobStatus(self, status):
        self.active_job.job_status = status
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
    
    def pauseJob(self):
        self.active_job.job_status = "paused"
        self.jobQueue.add_job(self.active_job)
        self.active_job = None
        self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
    
    def setJobRunning(self):
        if self.active_job is not None:
            self.active_job.job_status = "Running"
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
        
    
    def setJobComplete(self):
        if self.active_job is not None:
            print(f"Completing job {self.active_job.job_id}")  # Debugging
            completed_job_type = self.active_job.job_type
            self.active_job.job_status = "Completed"
            self.active_job = None
            if self.available and not self.jobQueue.is_empty():
                next_job = self.jobQueue.get_next_job()
                print(f"Next job: {next_job.job_id}")  # Debugging
                self.setActiveJob(next_job)  # Ensure it's using the new job
            elif self.available and self.jobQueue.is_empty() and completed_job_type == "Initial Search":
                self.missionState.on_search_traversal_complete(self.drone_id)
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
    
    def setJobFailedUpload(self):
        if self.active_job is not None and self.active_job.upload_try_count < 3:
            self.active_job.job_status = "Failed Upload"
            self.missionState.send_waypoints(self.drone_id, self.active_job.waypoints)
            self.active_job.upload_try_count += 1
        else:
            self.active_job.job_status = "Failed Upload"
            self.active_job = None
            if not self.jobQueue.is_empty():
                next_job = self.jobQueue.get_next_job()
                self.setActiveJob(next_job)
    
    def setLastWaypoint(self, waypoint):
        if self.active_job is not None:
            self.active_job.last_waypoint = waypoint
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
            
    def setDroneUnavailable(self):
        self.available = False
        #  push active job to the back of the queue
        if self.active_job is not None:
            self.jobQueue.add_job(self.active_job)
            self.active_job = None
            self.missionState.gui.updateJobs(self.drone_id, self.active_job, self.jobQueue.list_jobs())
    
    def setDroneAvailable(self):
        self.available = True
        #  if there is a job in the queue, set it as the active job
        if not self.jobQueue.is_empty():
            next_job = self.jobQueue.get_next_job()
            self.setActiveJob(next_job)
    
    def set_operatingAltitude(self, altitude):
        self.operatingAltitude = altitude

        



    #GETTERS
    def get_home(self):
        return (self.home_latitude, self.home_longitude, )
    
    def get_operatingAltitude(self):
        return self.operatingAltitude

class POI:
    def __init__(self, lat, lon, name, desc, poi_status, poi_type):
        self.lat = lat
        self.lon = lon
        self.name = name
        self.desc = desc
        self.poi_status = poi_status
        self.poi_type = poi_type
        self.poi_target_at_location = False


class missionState:

    def __init__(self, gui):
        self.drones = []
        self.pois = []
        self.gcs_location = None  # Global Control Station location (latitude, longitude)
        
        self.missionPolygon = None
        self.mavLinkConnected = False
        self.gui = gui
        self.loop = asyncio.new_event_loop()
        self.dispatcher = Dispatcher.Dispatcher(self)
        self.jobIDCounter = 100
        self.agent_d = get_agent_d_service()
        self.missionID = "mission-local"
        # TEST VALUES
        self.mission_waypoints = [(28.6013158, -81.2020057, 10, 0 ), (28.6031200, -81.1993369, 10, 0) , (28.6004825, -81.1942729, 10, 0)]
        self.mission_waypoints2  = [(28.6000236, -81.1988032, 10, 2)]
        self.mission_waypoints3 = [(28.5991587, -81.1985403, 10, 0 ), (28.6014194, -81.2027675, 10, 0)]

        #for simulation purposes
        self.detectionPoints = []
        self.visualization_ready = False
        self.missionGrid = None
        self.viable_grid_positions = None
        self.rtree = None
        self.drone_search_destinations = {}
        self.agent_d_last_result = None

        # Start Agent B microservice as a background process
        self._agent_b_proc = self._start_agent_b()

        # Poll Agent B for new detections and forward to Agent D for costmap updates
        self._detection_poll_stop = threading.Event()
        self._detection_poll_thread = threading.Thread(
            target=self._poll_agent_b_detections, daemon=True
        )
        self._detection_poll_thread.start()

        # Health-check thread for service status indicators
        self._health_poll_thread = threading.Thread(
            target=self._poll_service_health, daemon=True
        )
        self._health_poll_thread.start()

    def _poll_service_health(self):
        """Background thread: pings Agent B and OSM DB, updates GUI status dots."""
        import psycopg2
        OSM_HOST = "18.220.206.190"
        OSM_PORT = 5432
        AGENT_B_HEALTH = "http://localhost:8081/health"
        POLL_INTERVAL = 10

        _time.sleep(3)  # Wait for GUI to initialize

        while not self._detection_poll_stop.is_set():
            # Check Agent B
            agent_b_up = False
            try:
                resp = requests.get(AGENT_B_HEALTH, timeout=2)
                agent_b_up = resp.status_code == 200
            except Exception:
                pass

            # Check OSM PostGIS
            osm_up = False
            try:
                conn = psycopg2.connect(
                    host=OSM_HOST, port=OSM_PORT,
                    dbname="gis", user="renderer", password="renderer",
                    connect_timeout=3,
                )
                conn.close()
                osm_up = True
            except Exception:
                pass

            self.gui.updateServiceStatus(agent_b_up, osm_up)
            self._detection_poll_stop.wait(POLL_INTERVAL)

    @staticmethod
    def toggle_database(action):
        """Sends a start/stop command to the VITALS OSM EC2 instance."""

        headers = {
                "x-api-key": API_KEY,
                "Content-Type": "application/json"
        }

        payload = {"action": action.lower()}

        try:
            print(f"[*] Sending {action.upper()} request to OSM Database...")
            response = requests.post(API_ENDPOINT, json=payload, headers=headers)

            if response.status_code == 200:
                result = response.json()
                print(f"[+] Success: {result.get('status', 'Command executed')}")
            else:
                print(f"[-] Error {response.status_code}: {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"[-] Connection failed: {e}")

    def _start_agent_b(self):
        """Launch Agent B (FastAPI + TCP listener) as a background subprocess."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        agents_dir = os.path.join(app_dir, "Agents")
        schema_root = os.path.join(app_dir, "schemas")

        env = os.environ.copy()
        env["VITALS_SCHEMA_ROOT"] = schema_root

        try:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn",
                 "agent_b.agent_b_service:app",
                 "--host", "0.0.0.0", "--port", "8081",
                 "--log-level", "warning"],
                cwd=agents_dir,
                env=env,
            )
            print(f"[+] Agent B started (PID {proc.pid}) — HTTP :8081, TCP :9000")
            return proc
        except Exception as e:
            print(f"[-] Failed to start Agent B: {e}")
            return None

    def _stop_agent_b(self):
        """Terminate Agent B subprocess."""
        if self._agent_b_proc and self._agent_b_proc.poll() is None:
            self._agent_b_proc.terminate()
            try:
                self._agent_b_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._agent_b_proc.kill()
            print("[+] Agent B stopped")

    def _resolve_detecting_drone(self, det: dict):
        """Find the Drone object that produced this detection based on uav_id/instance."""
        uav_id = (det.get("payload") or {}).get("uav_id") or ""
        instance = (det.get("source") or {}).get("instance") or ""
        drone_hint = uav_id or instance
        for drone in self.drones:
            if str(drone.drone_id) in drone_hint:
                return drone
        # Fallback: return first drone
        return self.drones[0] if self.drones else None

    def _resolve_drone_geo(self, det: dict) -> dict:
        """Look up the real GPS position of the drone that made this detection."""
        # Identify which drone from the MCP message
        uav_id = (det.get("payload") or {}).get("uav_id") or ""
        instance = (det.get("source") or {}).get("instance") or ""
        drone_hint = uav_id or instance  # e.g. "UAV_1" or "drone-1"

        for drone in self.drones:
            drone_id_str = str(drone.drone_id)
            if drone_id_str in drone_hint and drone.latitude and drone.longitude:
                return {
                    "lat": drone.latitude / 1e7,
                    "lon": drone.longitude / 1e7,
                }
        # Fallback: return first drone with a valid fix
        for drone in self.drones:
            if drone.latitude and drone.longitude:
                return {
                    "lat": drone.latitude / 1e7,
                    "lon": drone.longitude / 1e7,
                }
        return {}

    def _poll_agent_b_detections(self):
        """Background thread: polls Agent B for new MCP.Detection messages,
        corrects geo with real drone telemetry, updates Agent B's stored record,
        and forwards to Agent D for costmap updates."""
        AGENT_B_BASE = "http://localhost:8081"
        POLL_INTERVAL = 2
        last_ts = ""
        seen_event_ids = set()

        _time.sleep(5)  # Wait for Agent B to start

        while not self._detection_poll_stop.is_set():
            try:
                resp = requests.get(
                    f"{AGENT_B_BASE}/detections/recent",
                    params={"since": last_ts}, timeout=3,
                )
                if resp.status_code != 200:
                    self._detection_poll_stop.wait(POLL_INTERVAL)
                    continue

                all_messages = resp.json().get("detections", [])

                # Separate captions from detections and index captions by corr_id
                captions_by_corr = {}
                for msg in all_messages:
                    if msg.get("type") == "MCP.Caption":
                        cid = msg.get("corr_id")
                        if cid:
                            captions_by_corr[cid] = (msg.get("payload") or {}).get("caption", "")

                for det in all_messages:
                    if det.get("type") != "MCP.Detection":
                        continue
                    event_id = det.get("event_id")
                    if not event_id or event_id in seen_event_ids:
                        continue
                    seen_event_ids.add(event_id)

                    # Correct geo using live drone telemetry
                    real_geo = self._resolve_drone_geo(det)
                    if real_geo:
                        try:
                            requests.post(
                                f"{AGENT_B_BASE}/detections/update-geo",
                                json={"event_id": event_id, "geo": real_geo},
                                timeout=3,
                            )
                        except Exception:
                            pass
                        det["geo"] = real_geo

                    if not det.get("corr_id"):
                        det["corr_id"] = self.missionID

                    geo = det.get("geo") or {}
                    lat = geo.get("lat")
                    lon = geo.get("lon")
                    label = (det.get("payload") or {}).get("label", "unknown")

                    # Build description: prefer VLM caption, fall back to detection text
                    caption = captions_by_corr.get(det.get("corr_id", ""), "")
                    description = caption or det.get("text", f"{label} detected by vision-edge")

                    # Forward to Agent D for costmap update
                    try:
                        result = self.agent_d.ingest_message(det)
                        self.agent_d_last_result = result
                        self._sync_agent_d_session()
                        print(f"[Agent D] Detection registered: {label} at ({lat}, {lon})")
                    except Exception:
                        pass  # Session not ready or detection outside grid

                    # Create POI on map if we have valid coordinates
                    if lat is not None and lon is not None:
                        # Check for nearby existing POI (within 40m)
                        duplicate = False
                        for poi in self.pois:
                            if coordinate_estimation.calculate_distance_between_points(
                                lat, lon, poi.lat, poi.lon
                            ) < 40:
                                poi.positive_flags += 1
                                duplicate = True
                                break
                        if not duplicate:
                            poi_id = self.gui.addDetectedPOI(lat, lon, f"Detected: {label}", description)
                            if poi_id is not None:
                                # Identify and pause the detecting drone
                                detecting_drone = self._resolve_detecting_drone(det)
                                if detecting_drone:
                                    # Pause current search job and circle the POI (LOITER_TURNS)
                                    if detecting_drone.active_job:
                                        detecting_drone.pauseJob()
                                    orbit_waypoint = [(lat, lon, int(detecting_drone.operatingAltitude), 2)]
                                    orbit_job = Job(f"Circling POI {poi_id}", "pending", orbit_waypoint, self, 6)
                                    detecting_drone.addJob(orbit_job)

                                # Notify user via chat and wait for response
                                drone_label = f"Drone {detecting_drone.drone_id}" if detecting_drone else "A drone"
                                drone_id_str = str(detecting_drone.drone_id) if detecting_drone else "?"
                                self.gui.create_system_chat_message(
                                    f"{label.capitalize()} detected at ({lat:.6f}, {lon:.6f}). "
                                    f"{drone_label} is circling the POI. "
                                    f"Say 'send drone {drone_id_str} to investigate poi {poi_id}' "
                                    f"or 'continue drone {drone_id_str}'."
                                )

                    ts = det.get("ts", "")
                    if ts > last_ts:
                        last_ts = ts

            except requests.exceptions.ConnectionError:
                pass  # Agent B not up yet
            except Exception as exc:
                print(f"[Detection poll] Error: {exc}")

            self._detection_poll_stop.wait(POLL_INTERVAL)

    def reset_for_new_mission(self):
        """Reset missionState for a new mission while preserving MAVLink connection."""
        self.pois = []
        self.detectionPoints = []
        self.visualization_ready = False
        self.missionPolygon = None
        self.missionGrid = None
        self.rtree = None
        self.viable_grid_positions = None
        self.drone_search_destinations = {}
        self.gcs_location = None
        self.agent_d_last_result = None
        # Reset all drone state for new mission
        for drone in self.drones:
            drone.position_history = []
            drone._last_history_time = 0
            drone.available = True
            drone.active_job = None
            drone.last_mission_state = None
            drone.jobQueue = JobQueue()

    def _current_drone_geo(self, drone):
        lat = None
        lon = None
        if drone.latitude not in (None, 0) and drone.longitude not in (None, 0):
            lat = drone.latitude / 1e7 if abs(drone.latitude) > 90 else drone.latitude
            lon = drone.longitude / 1e7 if abs(drone.longitude) > 180 else drone.longitude
        elif drone.home_latitude not in (None, 0) and drone.home_longitude not in (None, 0):
            lat = drone.home_latitude / 1e7 if abs(drone.home_latitude) > 90 else drone.home_latitude
            lon = drone.home_longitude / 1e7 if abs(drone.home_longitude) > 180 else drone.home_longitude
        return lat, lon

    def _agent_d_context(self):
        drones = []
        for drone in self.drones:
            lat, lon = self._current_drone_geo(drone)
            drones.append({"drone_id": drone.drone_id, "lat": lat, "lon": lon})
        return {"drones": drones, "num_drones": max(len(drones), 4)}

    def _build_agent_d_search_intent(self, polygon):
        return {
            "schema": "acp.v0.2",
            "event_id": f"search-{self.missionID}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "ACP.Intent",
            "corr_id": self.missionID,
            "idempotency_key": f"search-area-{self.missionID}",
            "source": {"system": "VITALS", "component": "GUIAdapter", "instance": "desktop"},
            "target": {"component": "AgentD", "instance": "agentd-core"},
            "payload": {
                "intent_kind": "SearchArea",
                "priority": 50,
                "area": {
                    "polygon_wgs84": [
                        {"lat": float(lat), "lon": float(lon)}
                        for lat, lon in polygon
                    ]
                },
            },
        }

    def _build_agent_d_poi_intent(self, lat, lon):
        suffix = len(self.pois) + 1
        return {
            "schema": "acp.v0.2",
            "event_id": f"poi-{self.missionID}-{suffix}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "ACP.Intent",
            "corr_id": self.missionID,
            "idempotency_key": f"gui-poi-{self.missionID}-{suffix}",
            "source": {"system": "VITALS", "component": "GUIAdapter", "instance": "desktop"},
            "target": {"component": "AgentD", "instance": "agentd-core"},
            "payload": {
                "intent_kind": "InvestigatePoint",
                "priority": 80,
                "point": {"lat": float(lat), "lon": float(lon)},
                "rationale": "GUI manual detection point",
            },
        }

    def _build_agent_d_detection_message(self, lat, lon, label, confidence, drone_id):
        return {
            "schema": "mcp.v0.2",
            "event_id": f"det-{self.missionID}-{drone_id}-{int(abs(lat) * 1000000)}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": "MCP.Detection",
            "corr_id": self.missionID,
            "idempotency_key": f"vision-detection-{self.missionID}-{drone_id}-{int(abs(lat) * 1000000)}",
            "source": {"system": "VITALS", "component": "AgentA", "instance": f"drone-{drone_id}"},
            "geo": {"lat": float(lat), "lon": float(lon)},
            "payload": {"label": str(label), "confidence": float(confidence)},
            "text": f"{label} detected at {lat:.6f},{lon:.6f}",
        }

    def _sync_agent_d_session(self):
        session = self.agent_d.get_session(self.missionID)
        if session is None:
            return None
        self.missionGrid = session.grid
        self.viable_grid_positions = session.viable_grid_positions
        self.rtree = session.rtree
        self.missionPolygon = session.polygon_wgs84
        self.drone_search_destinations = session.centroid_paths
        self.visualization_ready = True
        return session

    def connect_to_mavlink(self):
        if self.mavLinkConnected:
            print("Already connected to MAVLink")
            return True
        success = self.dispatcher.connect()
        if success:
            self.dispatcherThread = threading.Thread(target=self.run_asyncio_loop, daemon=True)
            self.dispatcherThread.start()
            self.mavLinkConnected = True
            print("Connected to MAVLink")
            return True
        else:
            print("Failed to connect to MAVLink")
            self.mavLinkConnected = False
            return False

    
    def run_asyncio_loop(self):
        """Runs the asyncio event loop in a separate thread for the dispatcher."""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.dispatcher.receive_packets())

    def addDrone(self, drone_id, system_status):
        self.drones.append(Drone(self, drone_id, system_status, 20 + (5 * len(self.drones))))
        self.drones.sort(key=lambda x: x.drone_id)
        self.gui.addDrone(drone_id, system_status)

    def updateDronePosition(self, drone_id, latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is None:
            self.addDrone(drone_id, 0)
            drone = next((d for d in self.drones if d.drone_id == drone_id), None)

        if drone is not None:
            drone.updatePosition(latitude, longitude, altitude, relative_altitude, heading, vx, vy, vz)
            #check if drone is within 20 meters of the target detection points
            # Skip detection if drone is unavailable (RTL) or actively investigating a POI
            if self.detectionPoints and drone.available and (drone.active_job is None or not drone.active_job.job_type.startswith("Investigate POI")):
                for point in self.detectionPoints:
                    distance = coordinate_estimation.calculate_distance_between_points(
                        latitude / 1e7, longitude / 1e7,
                        point["lat"], point["lon"]
                    )
                    if distance < 20:  # If within 20 meters and the flag is less than 3
                        print(f"Drone {drone_id} is within 20 meters of detection point {point['lat']}, {point['lon']} num_hits: {point['num_hits']} roll: {drone.roll}")
                        if point["num_hits"] < 1 or (point["num_hits"] <= 3 and abs(drone.roll) > 0.1):  # If the flag is less than 1 or if the drone is pitching significantly
                            point["num_hits"] += 1  # Increment the flag for this detection point
                            self.trigger_image_detection(drone_id)
                        


    def updateDroneTelemetry(self, drone_id, roll, pitch, yaw):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.updateTelemetry(roll, pitch, yaw)

    def addMissionPolygon(self, polygon):
        result = self.agent_d.ingest_message(
            self._build_agent_d_search_intent(polygon),
            context=self._agent_d_context(),
        )
        self.agent_d_last_result = result
        self._sync_agent_d_session()

    def showPathVisualization(self):
        """Launch the path visualization on-demand. Returns the matplotlib figure."""
        if not self.visualization_ready:
            print("Visualization not ready - polygon not yet created")
            return None

        self._visualization = Interactive_Visualization(self)
        fig = self._visualization.initalize_plot(
            self.rtree, self.missionGrid, self.missionPolygon, {
                "building": (1, 0, 0, 1.0),
                "water": (0.0, 0.0, 1.0, 1.0),
                "highway": {
                    "highway": (1.0, 0.65, 0.0, 1.0),
                    "pedestrian_path": (0.4, 0.8, 0.4, 1.0)
                }
            },
            show_grid=True,
            polygon_darkening_factor=0,
            drone_paths=self.drone_search_destinations
        )
        return fig

    def doPathPlanning(self):
        self._sync_agent_d_session()

    def deployInitialPaths(self):
        for drone in self.drones:
            converted_waypoints = []
            planned_path = (self.drone_search_destinations or {}).get(drone.drone_id, [])
            for coord in planned_path:
                converted_waypoints.append((coord.y, coord.x, drone.operatingAltitude, 0))
            if converted_waypoints:
                self.create_job("Initial Search", converted_waypoints, 1, drone.drone_id)


    def startSearchMission(self):
        self.deployInitialPaths()



    def getMissionPolygon(self):
        return self.missionPolygon

    def updateDroneStatus(self, drone_id, system_status, custom_mode=None):
        # check if drone exists yet
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is None:
            self.addDrone(drone_id, system_status)
        else:
            drone.updateStatus(system_status, custom_mode)
    
    def getDrones(self):
        return self.drones
    
    def get_drone(self, drone_id):
        return next((d for d in self.drones if d.drone_id == drone_id), None)

    def arm_mission(self, drone_id):
        self.dispatcher.arm_drone(drone_id)
    
    def takeoff_mission(self, drone_id):
        self.dispatcher.takeoff(drone_id, 10)
    
    def send_waypoints(self, drone_id, waypoints):

        print("Sending waypoints")
        self.dispatcher.send_mission(drone_id, waypoints)
    
    def return_to_launch(self, drone_id):
        self.dispatcher.return_to_launch(drone_id)
    
    def send_poi_investigate(self, drone_id, waypoint):
        self.dispatcher.send_poi_investigate(drone_id, waypoint)
    
    def send_mission_list_request(self, drone_id):
        self.dispatcher.request_mission_list(drone_id)
    
    def handle_reached_waypoint(self, drone_id, waypoint):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.setLastWaypoint(waypoint)
    
    def handle_mission_state_update(self, drone_id, mission_state):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            if mission_state == 5:
                if drone.last_mission_state != 5: # this ensures that the drone is not already in the state
                    drone.setJobComplete()
            drone.last_mission_state = mission_state
            
    def create_job(self, job_type, waypoints, job_priority, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            job = Job(job_type, "pending", waypoints, self, job_priority)
            drone.addJob(job)
    
    def test_add_job(self, drone_id, use_waypoints):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            if use_waypoints == 1:
                job = Job("Automated Path", "pending", self.mission_waypoints, self, 1)
                drone.addJob(job)
            elif use_waypoints == 2:
                job = Job("Investigate Point", "pending", self.mission_waypoints2, self, 5)
                drone.addJob(job)
            elif use_waypoints == 3:
                job = Job("User Path", "pending", self.mission_waypoints3, self, 5)
                drone.addJob(job)
            
    
    def get_drone(self, drone_id):
        return next((d for d in self.drones if d.drone_id == drone_id), None)
    
    def getDrones(self):
        """returns drone list in a readable format for llm"""
        drone_list = []
        for drone in self.drones:
            drone_list.append({
                "drone_id": drone.drone_id,
                "system_status": drone.system_status,
                "latitude": drone.latitude,
                "longitude": drone.longitude,
                "altitude": drone.altitude,
                "relative_altitude": drone.relative_altitude,
                "heading": drone.heading,
                "vx": drone.vx,
                "vy": drone.vy,
                "vz": drone.vz
            })
        return drone_list
    def getPOIs(self):
        """returns poi list in a readable format for llm"""
        poi_list = []
        for poi in self.pois:
            poi_list.append({
                "lat": poi.lat,
                "lon": poi.lon,
                "name": poi.name,
                "id": poi.id,
            })
        return poi_list
    
    def addPOI(self, poi):
        #create POI directory in mission folder
        os.makedirs(f"Missions/{self.missionID}/POIs/{poi.id}", exist_ok=True)
        self.pois.append(poi)
        self.gui.addPOI(poi)

    
    def create_poi_investigate_job(self, poi_id, drone_id, priority = 5):
        print(f"Creating POI investigate job for drone {drone_id} and poi {poi_id}")
    
        poi = next((p for p in self.pois if p.id == int(poi_id)), None)
        print(f"POI: {poi}")
        if poi is not None:
            drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
            if drone is not None:
                job = Job(f"Investigate POI {poi.id} ", "pending", [(poi.lat, poi.lon, int(drone.operatingAltitude), 2)], self, priority)
                drone.addJob(job)
    
    def call_drone_home(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
        if drone is not None:
            drone.setDroneUnavailable()
            self.dispatcher.return_to_launch(int(drone_id))
    
    def resume_drone_mission(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
        if drone is not None:
            # Cancel the circling job (if active) and pick up the next queued job
            if drone.active_job and drone.active_job.job_type.startswith("Circling POI"):
                drone.setJobComplete()
            elif not drone.available:
                drone.setDroneAvailable()

    def get_mission_report_data(self):
        """Return planned and actual paths for each drone."""
        report = []
        for drone in self.drones:
            planned = []
            for coord in (self.drone_search_destinations or {}).get(drone.drone_id, []):
                planned.append((coord.y, coord.x))  # (lat, lon)
            # Convert position history from 1e7 int format if needed
            actual = []
            for lat, lon in drone.position_history:
                if abs(lat) > 90 or abs(lon) > 180:
                    actual.append((lat / 1e7, lon / 1e7))
                else:
                    actual.append((lat, lon))
            report.append({
                'drone_id': drone.drone_id,
                'planned': planned,
                'actual': actual
            })
        return report

    def on_search_traversal_complete(self, drone_id):
        """Called when a drone finishes its Initial Search path with no jobs left."""
        print(f"Drone {drone_id} has completed search traversal.")
        self.call_drone_home(drone_id)
        self.gui.create_system_chat_message(
            f"Drone {drone_id} has finished traversing its search path and is returning to launch."
        )

    def repeat_search_traversal(self, drone_id):
        """Re-deploy the initial search path for a specific drone."""
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            if self.drone_search_destinations and drone.drone_id in self.drone_search_destinations:
                converted_waypoints = []
                for coord in self.drone_search_destinations[drone.drone_id]:
                    converted_waypoints.append((coord.y, coord.x, drone.operatingAltitude, 0))
                self.create_job("Initial Search", converted_waypoints, 1, drone_id)

    def land_drone(self, drone_id):
        """Land the drone immediately at current location."""
        drone = next((d for d in self.drones if d.drone_id == int(drone_id)), None)
        if drone is not None:
            drone.setDroneUnavailable()
            self.dispatcher.land_drone(int(drone_id))
    
    def end_mission(self):
        for drone in self.drones:
            self.call_drone_home(drone.drone_id)
        self.gui.enter_mission_ended_state()
    
    def set_missionID(self, id):
        self.missionID = str(id)
    
    def get_missionID(self):
        return self.missionID
    
    def trigger_image_detection(self, drone_id):
        random_img_id = random.randint(1,5)
        image_path = f"ComputerVision/temp/drone_testing{random_img_id}.jpg"  # Simulated image path for testing
        self.handle_image_detection(drone_id, image_path)
    
    def handle_image_detection(self, drone_id, image_path):
        # Run the LLM in a separate thread to prevent UI freezing
        def process_image():
            result = langChainMain.give_image_description(image_path)
            return result.content  # Extract the description

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(process_image)
            description = future.result()  # Wait for the result in a non-blocking way

        detections, image = YoloDetector.detect_from_path(image_path, True)
        if detections is None or len(detections) == 0:
            print("No objects detected in the image.")
            return
        else:
            # Now process the estimated position
            drone = next((d for d in self.drones if d.drone_id == drone_id), None)
            if drone is None:
                return
            
            
            
            estimated_lat, estimated_lon = coordinate_estimation.estimate_position( 
                drone.latitude / 1e7, 
                drone.longitude / 1e7, 
                drone.altitude / 1000, 
                -10, 
                0, 
                90,  # Assuming a FOV of 90 degrees for simplicity
                960,  # x coordinate in the image (center)
                540,  # y coordinate in the image (center)
                drone.heading,
                image_width=1920,
                image_height=1080
            )

            try:
                detection_result = self.agent_d.ingest_message(
                    self._build_agent_d_detection_message(
                        estimated_lat,
                        estimated_lon,
                        detections[0].class_name,
                        detections[0].confidence,
                        drone_id,
                    )
                )
            except AgentDError as exc:
                self.gui.create_system_chat_message(
                    f"Agent D rejected a vision detection from drone {drone_id}: {exc}"
                )
                return

            self.agent_d_last_result = detection_result
            self._sync_agent_d_session()

            # Check if the detected POI already exists within 20 meters
            for poi in self.pois:
                if coordinate_estimation.calculate_distance_between_points(estimated_lat, estimated_lon, poi.lat, poi.lon) < 40:
                    os.makedirs(f"Missions/{self.missionID}/POIs/{poi.id}", exist_ok=True)
                    cv2.imwrite(f"Missions/{self.missionID}/POIs/{poi.id}/{os.path.basename(image_path)}", image)
                    poi.positive_flags += 1
                    if poi.positive_flags >= 3:
                        poi.target_found(drone_id)  # Mark the POI as found if it has enough positive flags
                        
                    return

            # If no existing POI, create a new one
            poi_id = self.gui.addDetectedPOI(estimated_lat, estimated_lon, "Detected POI", description)

            # Store image in POI directory
            os.makedirs(f"Missions/{self.missionID}/POIs/{poi_id}", exist_ok=True)
            cv2.imwrite(f"Missions/{self.missionID}/POIs/{poi_id}/{os.path.basename(image_path)}", image)
    
    def set_gcs_location(self, coordinates_tuple):
        self.gcs_location = coordinates_tuple

    def setDetectionPoints(self, points):
        self.detectionPoints = points

    def register_manual_detection_points(self, points):
        for point in points:
            lat = float(point["lat"])
            lon = float(point["lon"])
            result = self.agent_d.ingest_message(self._build_agent_d_poi_intent(lat, lon))
            self.agent_d_last_result = result
            self.gui.map_page.add_poi(lat, lon, "Manual POI", "GUI detection point")
        self._sync_agent_d_session()

    def  get_drone_operatingAltitude(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            return drone.get_operatingAltitude()
        else:
            return None
    
    def  set_drone_operatingAltitude(self, drone_id, altitude):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.set_operatingAltitude(altitude)
            self.gui.updateDroneOperatingAltitude(drone_id, altitude)
        else:
            return None
    
    def set_drone_maxVelocity(self, drone_id, velocity):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.maxVelocity = velocity
            print(f"Drone {drone_id} max velocity set to {velocity} m/s")
            if self.mavLinkConnected:
                self.dispatcher.set_max_velocity(drone_id, velocity)

    def get_drone_vision_model(self, drone_id):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            return drone.visionModel
        else:
            return None
    def set_drone_vision_model(self, drone_id, model):
        drone = next((d for d in self.drones if d.drone_id == drone_id), None)
        if drone is not None:
            drone.visionModel = model
            self.gui.updateDroneVisionModel(drone_id, model)
        else:
            return None
    def remove_poi_investigate_job(self, droneID):
        drone = next((d for d in self.drones if d.drone_id == droneID), None)
        if drone is not None and drone.active_job is not None:
            if drone.active_job.job_type.startswith("Investigate POI"):
                print(f"Removing job {drone.active_job.job_id} for drone {droneID}")
                drone.setJobComplete()
        
        

if __name__ == "__main__":
    missionState.toggle_database('start')
    
    gui = GUI()
    missionState = missionState(gui)
    gui.link_mission_state(missionState)
    
    try:
        gui.run()
    finally:
        missionState._detection_poll_stop.set()
        missionState._stop_agent_b()
