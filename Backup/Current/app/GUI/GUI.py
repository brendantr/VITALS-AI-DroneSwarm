from datetime import datetime
import os
import PIL.Image
import PIL.ImageTk
import customtkinter

# Import from refactored modules
from GUI.Entities.Job import JobWaypoint
from GUI.Pages.HomePage import HomePage
from GUI.Pages.MapPage import MapPage


class GUI:
    def __init__(self):
        #self.missionState = missionState
        self.app = customtkinter.CTk()
        self.app.title("VITALS DESKTOP APP")
        self.app.geometry("1280x720")
        self.choosing_gcs_location = False
        self.gcs_location = None
        self.gcs_marker = None
        self.container = customtkinter.CTkFrame(self.app)
        self.container.pack(fill="both", expand=True)

        self.currentJobWaypoints = []
        self.currentJobPath = None

        self.isSimulation = False
        self.missionStarted = False

        self.detection_points = []
        self.detection_point_markers = []
        self.isAddingDetectionPoints = False

        # Create pages
        self.home_page = HomePage(self.container, self)
        self.map_page = MapPage(self.container, self.show_home_page, self)

        # Show the home page initially
        self.home_page.pack(fill="both", expand=True)

    def show_home_page(self):
        self.map_page.pack_forget()
        self.home_page.pack(fill="both", expand=True)

    def show_map_page(self):
        currentDateTime = datetime.now()
        print("Current date and time:", currentDateTime)
        mission_id = currentDateTime.strftime('%Y-%m-%d_%H-%M-%S')
        # Create Mission Folder
        os.makedirs(f"missions/{mission_id}", exist_ok=True)
        self.map_page.gui_ref.missionState.set_missionID(mission_id)
        self.home_page.pack_forget()
        self.map_page.pack(fill="both", expand=True)
        self.create_system_chat_message(f"Welcome to VITALS! I am your AI assistant. Please connect to mavlink with the button on the left sidebar to start the mission. Your mission ID is {mission_id}.")

    def run(self):
        self.app.mainloop()

    def link_mission_state(self, missionState):
        self.missionState = missionState

    def call_mavlink_connection(self):
        success = self.missionState.connect_to_mavlink()
        if success:
            print("Connected to Mavlink successfully.")
            self.map_page.connect_button.configure(state="disabled", text="Connected")
            self.map_page.place_gcs_button.configure(state="normal")
            self.create_system_chat_message("Connected to Mavlink successfully. Please place the GCS location using the 'Place GCS' button.")
        else:
            print("Failed to connect to Mavlink.Callback")

    def get_polygon_points(self):
        return self.map_page.get_polygon_points()

    def sendMissionPolygon(self, polygon_points):
        self.missionState.addMissionPolygon(polygon_points)

    def updateDronePosition(self, drone_id, lat, lon, altitude, relative_altitude, heading, vx, vy, vz):
        drone = next((drone for drone in self.map_page.drones if drone.id == drone_id), None)
        if drone is not None:
            drone.setPosition(lat, lon, altitude, relative_altitude, heading, vx, vy, vz)

    def updateDroneTelemetry(self, drone_id, roll, pitch, yaw):
        drone = next((drone for drone in self.map_page.drones if drone.id == drone_id), None)
        if drone is not None:
            drone.setTelemetry(roll, pitch, yaw)

    def addDrone(self, drone_id, system_status):
        self.map_page._add_drone(drone_id, system_status)

    def updateDroneStatus(self, drone_id, system_status):
        drone = next((drone for drone in self.map_page.drones if drone.id == drone_id), None)
        if drone is not None:
            drone.setStatus(system_status)

    def updateJobs(self, drone_id, active_job, job_list):
        drone = next((drone for drone in self.map_page.drones if drone.id == drone_id), None)
        if drone is not None:
            drone.update_jobs(active_job, job_list)

    def callAddPoiInMissionState(self, poi):
        self.missionState.addPOI(poi)

    def addPOI(self, poi):
        #check if poi is already in the list
        if poi not in self.map_page.pois:
            self.map_page.add_poi(poi.lat, poi.lon, poi.name)

    def create_system_chat_message(self, text):
        """Add a system message bubble to the chat window."""
        self.map_page.collapsible_sidebar.add_message_bubble(text, sender="llm")

    def start_adding_detection_points(self):
        self.isAddingDetectionPoints = True
        self.map_page.map_widget.add_right_click_menu_command(label="Finish Adding Detection Points", command=self.finish_adding_detection_points)

    def add_detection_point(self, coords):
        self.detection_points.append(coords)
        self.detection_point_markers.append(self.map_page.map_widget.set_marker(coords["lat"], coords["lon"], text="Detection Point"))

    def finish_adding_detection_points(self):
        self.isAddingDetectionPoints = False
        #remove the right click menu command where label =  "Finish Adding Detection Points"
        list = self.map_page.map_widget.right_click_menu_commands
        target_command = None
        for command in list:
            if command['label'] == "Finish Adding Detection Points":
                target_command = command
                break
        list.remove(target_command)

        for marker in self.detection_point_markers:
            marker.delete()
        self.detection_point_markers = []
        self.missionState.setDetectionPoints(self.detection_points)
        self.create_system_chat_message("Setup Complete. You can now begin the mission.")
        self.map_page.end_mission_button.configure(state="normal")

    #Debugging Functions
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
            self.map_page.map_widget.add_right_click_menu_command(label="Finish Job", command=self.finish_creating_job)
        waypointNum = len(self.currentJobWaypoints) + 1
        waypoint = JobWaypoint(coords[0], coords[1], waypointNum, self.map_page.map_widget)
        self.currentJobWaypoints.append(waypoint)
        if len(self.currentJobWaypoints) >= 2:
            self.map_page.map_widget.delete_all_path()
            positions = []
            for waypoint in self.currentJobWaypoints:
                positions.append((waypoint.lat, waypoint.lon))
            path = self.map_page.map_widget.set_path(position_list=positions, width=5, color="red")

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

    def call_start_mission(self):
        if not self.missionStarted:
            self.missionStarted = True
            self.missionState.startSearchMission()
            self.create_system_chat_message("Mission started successfully!")
            self.map_page.end_mission_button.configure(text="End Mission", command=self.missionState.end_mission)

    def call_start_search_mission(self):
        self.missionState.startSearchMission()

    def set_gcs_location(self, coordinates_tuple, confirm_popup):
        """Set the GCS location and close the confirmation popup."""

        self.gcs_location = coordinates_tuple
        self.missionState.set_gcs_location(coordinates_tuple)
        self.choosing_gcs_location = False

        #load icon from assets folder
        def _load_icon(self, path):
            image = PIL.Image.open(path)
            image = image.resize((50, 50))
            return PIL.ImageTk.PhotoImage(image)

        gcs_icon_path = "./assets/gcs.png"
        gcs_icon = _load_icon(self, gcs_icon_path)

        self.gcs_marker = self.map_page.map_widget.set_marker(
            coordinates_tuple[0], coordinates_tuple[1],
            text="Ground Control",
            icon=gcs_icon,
            icon_anchor="center"
        )
        print(f"GCS location set to: {coordinates_tuple}")
        self.create_system_chat_message("GCS location set successfully.")
        confirm_popup.destroy()
        # Clean up the preview marker and motion binding
        self.map_page.finalize_gcs_placement()
        self.map_page.place_gcs_button.configure(text="Remove GCS")
        self.create_system_chat_message("You can now draw the mission area by clicking on the map to create a polygon. Press the 'Finish Creating Polygon' button when you're ready to finish the mission area.")
        self.map_page.start_polygon_button.configure(state="normal")


if __name__ == "__main__":
    app = GUI()
    app.run()
