from datetime import datetime
import os
import sys
import threading

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QIcon

from GUI.theme import DARK_THEME
from GUI.Entities.Job import JobWaypoint
from GUI.Pages.HomePage import HomePage
from GUI.Pages.MapPage import MapPage


class _Invoker(QObject):
    """Thread-safe invoker: emits a signal to run a callable on the main thread."""
    _sig = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self._sig.connect(self._call, Qt.ConnectionType.QueuedConnection)

    def _call(self, fn):
        fn()

    def invoke(self, fn):
        self._sig.emit(fn)


class GUI:
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setStyleSheet(DARK_THEME)

        self.window = QMainWindow()
        self.window.setWindowTitle("VITALS DESKTOP APP")
        self.window.resize(1280, 720)

        # Thread-safe invoker for MAVLink callbacks
        self._invoker = _Invoker()

        # Try to set window icon
        icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "lockheed_martin_logo.png")
        if os.path.exists(icon_path):
            self.window.setWindowIcon(QIcon(icon_path))

        # State
        self.choosing_gcs_location = False
        self.gcs_location = None
        self.gcs_marker_id = None

        self.currentJobWaypoints = []
        self.currentJobPath = None

        self.isSimulation = False
        self.missionStarted = False
        self.has_centered_on_drone = False

        self.detection_points = []
        self.detection_point_marker_ids = []
        self.isAddingDetectionPoints = False

        # Page stack
        self.stack = QStackedWidget()
        self.window.setCentralWidget(self.stack)

        # Create pages
        self.home_page = HomePage(self)
        self.map_page = MapPage(self)

        self.stack.addWidget(self.home_page)   # index 0
        self.stack.addWidget(self.map_page)    # index 1

        # Show home page initially
        self.stack.setCurrentIndex(0)

    # ── Page navigation ───────────────────────────────────

    def show_home_page(self):
        self.stack.setCurrentIndex(0)

    def show_map_page(self):
        currentDateTime = datetime.now()
        print("Current date and time:", currentDateTime)
        mission_id = currentDateTime.strftime('%Y-%m-%d_%H-%M-%S')
        os.makedirs(f"missions/{mission_id}", exist_ok=True)

        # Reset state for new mission
        self.reset_for_new_mission()
        self.missionState.reset_for_new_mission()
        self.map_page.reset_for_new_mission()

        self.missionState.set_missionID(mission_id)
        self.stack.setCurrentIndex(1)
        self.create_system_chat_message(
            f"Welcome to VITALS! I am your AI assistant. Please connect to mavlink "
            f"with the button on the left sidebar to start the mission. Your mission ID is {mission_id}."
        )

    def reset_for_new_mission(self):
        """Reset GUI state for a new mission."""
        self.missionStarted = False
        self.has_centered_on_drone = False
        self.choosing_gcs_location = False
        self.isAddingDetectionPoints = False

        # Clear detection point markers from map
        for marker_id in self.detection_point_marker_ids:
            self.map_page.map_widget.remove_marker(marker_id)
        self.detection_points = []
        self.detection_point_marker_ids = []

        # Clear GCS marker from map
        if self.gcs_marker_id is not None:
            self.map_page.map_widget.remove_marker(self.gcs_marker_id)
            self.gcs_marker_id = None
        self.gcs_location = None

    # ── App lifecycle ─────────────────────────────────────

    def run(self):
        self.window.show()
        sys.exit(self.app.exec())

    def link_mission_state(self, missionState):
        self.missionState = missionState

    # ── MAVLink connection ────────────────────────────────

    def call_mavlink_connection(self):
        success = self.missionState.connect_to_mavlink()
        if success:
            print("Connected to Mavlink successfully.")
            self.map_page.connect_button.setEnabled(False)
            self.map_page.connect_button.setText("Connected")
            self.map_page.place_gcs_button.setEnabled(True)
            self.create_system_chat_message(
                "Connected to Mavlink successfully. Please place the GCS location using the 'Place GCS' button."
            )
        else:
            print("Failed to connect to Mavlink.Callback")

    # ── Polygon ───────────────────────────────────────────

    def get_polygon_points(self):
        return self.map_page.get_polygon_points()

    def sendMissionPolygon(self, polygon_points):
        self.missionState.addMissionPolygon(polygon_points)

    # ── Drone updates (called from MAVLink thread → marshalled to main thread) ──

    def updateDronePosition(self, drone_id, lat, lon, altitude, relative_altitude, heading, vx, vy, vz):
        def _do():
            _lat, _lon = lat, lon
            if abs(_lat) > 90 or abs(_lon) > 180:
                _lat = _lat / 1e7
                _lon = _lon / 1e7

            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                drone.setPosition(_lat, _lon, altitude, relative_altitude, heading, vx, vy, vz)

                if not self.has_centered_on_drone and _lat != 0 and _lon != 0:
                    print(f"DEBUG: Centering map on drone {drone_id} at ({_lat}, {_lon})")
                    self.map_page.map_widget.set_position(_lat, _lon)
                    self.map_page.map_widget.set_zoom(17)
                    self.has_centered_on_drone = True
                    self.create_system_chat_message(f"Map centered on drone {drone_id} position.")
            else:
                print(f"DEBUG: updateDronePosition called but drone {drone_id} not found. lat={_lat}, lon={_lon}")
        self._invoker.invoke(_do)

    def updateDroneTelemetry(self, drone_id, roll, pitch, yaw):
        def _do():
            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                drone.setTelemetry(roll, pitch, yaw)
        self._invoker.invoke(_do)

    def addDrone(self, drone_id, system_status):
        def _do():
            print(f"DEBUG: Adding drone {drone_id} with status {system_status}")
            self.map_page._add_drone(drone_id, system_status)
        self._invoker.invoke(_do)

    def updateDroneStatus(self, drone_id, system_status):
        def _do():
            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                drone.setStatus(system_status)
        self._invoker.invoke(_do)

    def updateJobs(self, drone_id, active_job, job_list):
        def _do():
            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                drone.update_jobs(active_job, job_list)
        self._invoker.invoke(_do)

    def updateDroneOperatingAltitude(self, drone_id, altitude):
        def _do():
            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                drone.info_widget.altitude_label.setText(f"Altitude: {altitude} m (set)")
        self._invoker.invoke(_do)

    def updateDroneVisionModel(self, drone_id, model):
        def _do():
            drone = next((d for d in self.map_page.drones if d.id == drone_id), None)
            if drone is not None:
                print(f"Drone {drone_id} vision model updated to {model}")
        self._invoker.invoke(_do)

    # ── POI ───────────────────────────────────────────────

    def callAddPoiInMissionState(self, poi):
        self.missionState.addPOI(poi)

    def addPOI(self, poi):
        def _do():
            if poi not in self.map_page.pois:
                self.map_page.add_poi(poi.lat, poi.lon, poi.name)
        self._invoker.invoke(_do)

    def addDetectedPOI(self, lat, lon, name, description=""):
        """Thread-safe: add a POI from image detection, returns poi_id.
        Blocks the calling thread until the main thread creates the POI."""
        result = [None]
        event = threading.Event()
        def _do():
            result[0] = self.map_page.add_poi(lat, lon, name, description)
            event.set()
        self._invoker.invoke(_do)
        event.wait(timeout=30)
        return result[0]

    def showTargetFoundDialog(self, poi, drone_id):
        """Thread-safe: show target found dialog on the main thread."""
        self._invoker.invoke(lambda: poi.target_found(drone_id))

    # ── Chat ──────────────────────────────────────────────

    def create_system_chat_message(self, text):
        """Add a system message bubble to the chat window (thread-safe)."""
        self._invoker.invoke(
            lambda: self.map_page.chat_sidebar.add_message_bubble(text, sender="llm")
        )

    # ── Detection points (simulation) ─────────────────────

    def start_adding_detection_points(self):
        self.isAddingDetectionPoints = True
        self.map_page.map_widget.add_right_click_menu_command(
            "Finish Adding Detection Points", self.finish_adding_detection_points
        )

    def add_detection_point(self, coords):
        self.detection_points.append(coords)
        marker_id = self.map_page.map_widget.add_marker(coords["lat"], coords["lon"], "Detection Point")
        self.detection_point_marker_ids.append(marker_id)

    def finish_adding_detection_points(self):
        self.isAddingDetectionPoints = False
        self.map_page.map_widget.remove_right_click_menu_command("Finish Adding Detection Points")

        for marker_id in self.detection_point_marker_ids:
            self.map_page.map_widget.remove_marker(marker_id)
        self.detection_point_marker_ids = []

        self.missionState.setDetectionPoints(self.detection_points)
        self.create_system_chat_message("Setup Complete. You can now begin the mission.")
        self.map_page.end_mission_button.setEnabled(True)

    # ── Debug functions ───────────────────────────────────

    def call_takeoff_mission(self):
        target_drone = self.map_page.get_target_debug_drone()
        self.missionState.takeoff_mission(target_drone)

    def call_arm_mission(self):
        target_drone = self.map_page.get_target_debug_drone()
        self.missionState.arm_mission(target_drone)

    def call_send_waypoints(self):
        target_drone = self.map_page.get_target_debug_drone()
        debug_waypoints = self.map_page.get_debug_waypoints()
        self.missionState.send_waypoints(target_drone, debug_waypoints)

    def call_return_to_launch(self):
        target_drone = self.map_page.get_target_debug_drone()
        self.missionState.return_to_launch(target_drone)

    def call_request_mission_list(self):
        target_drone = self.map_page.get_target_debug_drone()
        self.missionState.send_mission_list_request(target_drone)

    def call_create_test_job(self):
        target_drone = self.map_page.get_target_debug_drone()
        debug_waypoints = self.map_page.get_debug_waypoints()
        self.missionState.test_add_job(target_drone, debug_waypoints)

    def add_job_waypoint(self, coords):
        if len(self.currentJobWaypoints) == 0:
            self.map_page.map_widget.add_right_click_menu_command("Finish Job", self.finish_creating_job)
        waypointNum = len(self.currentJobWaypoints) + 1
        waypoint = JobWaypoint(coords[0], coords[1], waypointNum, self.map_page.map_widget)
        self.currentJobWaypoints.append(waypoint)
        if len(self.currentJobWaypoints) >= 2:
            positions = [(wp.lat, wp.lon) for wp in self.currentJobWaypoints]
            self.map_page.map_widget.set_path("job_path", positions, color="red", width=5)

    def call_simulate_image_detection(self):
        target_drone = self.map_page.get_target_debug_drone()
        target_image = self.map_page.get_debug_waypoints()
        image_path = f"./temp/drone_testing{target_image}.jpg"
        self.missionState.handle_image_detection(target_drone, image_path)

    def finish_creating_job(self):
        pass

    def call_investigate_poi(self):
        drone_id = self.map_page.get_target_debug_drone()
        poi_id = self.map_page.get_debug_waypoints()
        self.missionState.create_poi_investigate_job(poi_id, drone_id)

    # ── Mission control ───────────────────────────────────

    def call_start_mission(self):
        if not self.missionStarted:
            self.missionStarted = True
            self.missionState.startSearchMission()
            self.create_system_chat_message("Mission started successfully!")
            self.map_page.end_mission_button.setText("End Mission")
            self.map_page.end_mission_button.clicked.disconnect()
            self.map_page.end_mission_button.clicked.connect(self.missionState.end_mission)

    def call_start_search_mission(self):
        self.missionState.startSearchMission()

    # ── GCS placement ─────────────────────────────────────

    def set_gcs_location(self, coordinates_tuple):
        """Set the GCS location."""
        self.gcs_location = coordinates_tuple
        self.missionState.set_gcs_location(coordinates_tuple)
        self.choosing_gcs_location = False

        self.gcs_marker_id = self.map_page.map_widget.add_marker(
            coordinates_tuple[0], coordinates_tuple[1],
            "Ground Control", icon="gcs"
        )
        print(f"GCS location set to: {coordinates_tuple}")
        self.create_system_chat_message("GCS location set successfully.")
        self.map_page.finalize_gcs_placement()
        self.map_page.place_gcs_button.setText("Remove GCS")
        self.create_system_chat_message(
            "You can now draw the mission area by clicking on the map to create a polygon. "
            "Press the 'Finish Creating Polygon' button when you're ready to finish the mission area."
        )
        self.map_page.start_polygon_button.setEnabled(True)


if __name__ == "__main__":
    app = GUI()
    app.run()
