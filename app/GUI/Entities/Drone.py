import math
from GUI.Widgets.DroneWidgets import DroneInfoBox, jobInfoContainer, jobInfoItem
from PyQt6.QtCore import QTimer


class Drone:

    def __init__(self, map_widget, info_container, job_container, drone_id, system_status, gui_ref):
        self.gui_ref = gui_ref
        self.map_widget = map_widget
        self.info_container = info_container
        self.job_container = job_container
        self.id = drone_id
        self.system_status = system_status
        self.position = None
        self.marker_id = None
        self.heading_path_id = f"heading_{drone_id}"
        self.altitude = None
        self.relative_altitude = None
        self.heading = None
        self.roll = None
        self.pitch = None
        self.yaw = None
        self.active_job = None
        self.job_list = []
        self.active_job_path_id = f"active_job_path_{drone_id}"
        self.active_job_start_pos = None
        self.showing_active_job_path = False
        self.id_of_job_with_path = None
        self.info_widget = DroneInfoBox(info_container, drone_id, self)
        self.job_info_container = jobInfoContainer(job_container, drone_id)
        match drone_id:
            case 1:
                self.color = "red"
            case 2:
                self.color = "blue"
            case 3:
                self.color = "green"
            case 4:
                self.color = "yellow"
            case _:
                self.color = "gray"

        color_map = {1: "#e74c3c", 2: "#3498db", 3: "#2ecc71", 4: "#f1c40f"}
        self.color = color_map.get(drone_id, "#95a5a6")

    def setPosition(self, lat, lon, altitude, relative_altitude, heading, vx, vy, vz):
        self.position = (lat, lon)
        self.altitude = altitude
        self.relative_altitude = relative_altitude
        converted_heading = heading / 1e2
        self.vx = vx
        self.vy = vy
        self.vz = vz

        # Set/move marker on map
        if self.marker_id is None:
            self.marker_id = self.map_widget.add_marker(lat, lon, f"Drone {self.id}", icon="drone")
        else:
            self.map_widget.move_marker(self.marker_id, lat, lon)

        # Heading path
        heading_rad = math.radians(converted_heading)
        lat_offset = 0.0005 * math.cos(heading_rad)
        lon_offset = 0.0005 * math.sin(heading_rad)
        self.map_widget.set_path(
            self.heading_path_id,
            [(lat, lon), (lat + lat_offset, lon + lon_offset)],
            color=self.color, width=2
        )

        # Velocity
        velocity = math.hypot(vx, vy) * 0.01  # cm/s to m/s

        # Update info widget
        self.info_widget.updatePos(self.position, self.relative_altitude, velocity, converted_heading)

    def setTelemetry(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def setStatus(self, system_status):
        self.system_status = system_status
        self.info_widget.updateStatus(system_status)

    def move(self, lat_offset, lon_offset):
        new_lat = self.position[0] + lat_offset
        new_lon = self.position[1] + lon_offset
        self.position = (new_lat, new_lon)
        if self.marker_id:
            self.map_widget.move_marker(self.marker_id, new_lat, new_lon)

    def update_jobs(self, active_job, job_list):
        self.active_job = active_job
        self.job_list = job_list
        print(f"Active Job: {self.active_job}")
        print(f"Job List: {self.job_list}")

        def refresh_jobs():
            # Clear old job widgets
            self.job_info_container.clear_jobs()

            if active_job:
                jobInfoItem(self.job_info_container.job_scrollable_layout, active_job, self, active=True)

                if self.showing_active_job_path:
                    trimmed_path = []
                    if self.active_job_start_pos is not None:
                        if self.id_of_job_with_path == active_job.job_id:
                            trimmed_path.append(self.position)
                        else:
                            self.active_job_start_pos = self.position
                            self.id_of_job_with_path = active_job.job_id
                            trimmed_path.append(self.position)
                            self.map_widget.remove_path(self.active_job_path_id)
                    else:
                        self.active_job_start_pos = self.position
                        self.id_of_job_with_path = active_job.job_id
                        trimmed_path.append(self.position)

                    print(f"last visited waypoint: {active_job.last_waypoint}")
                    for i in range(active_job.last_waypoint, len(active_job.waypoints)):
                        trimmed_path.append((active_job.waypoints[i][0], active_job.waypoints[i][1]))

                    if len(trimmed_path) > 1:
                        self.map_widget.set_path(self.active_job_path_id, trimmed_path, color=self.color, width=5)
            else:
                if self.active_job_path is not None:
                    self.active_job_path.delete()
                    self.active_job_path = None
                self.active_job_start_pos = None
                self.id_of_job_with_path = None

            for job in job_list:
                jobInfoItem(self.job_info_container.job_scrollable_layout, job)

        # Use QTimer to avoid accessing widgets during deletion
        QTimer.singleShot(100, refresh_jobs)

    def toggle_show_active_job_path(self):
        if self.showing_active_job_path:
            self.map_widget.remove_path(self.active_job_path_id)
        else:
            if self.active_job is not None:
                trimmed_path = []
                if self.active_job_start_pos is not None:
                    trimmed_path.append(self.position)
                else:
                    self.active_job_start_pos = self.position
                    trimmed_path.append(self.position)
                for i in range(self.active_job.last_waypoint, len(self.active_job.waypoints)):
                    trimmed_path.append((self.active_job.waypoints[i][0], self.active_job.waypoints[i][1]))
                if len(trimmed_path) > 1:
                    self.map_widget.set_path(self.active_job_path_id, trimmed_path, color=self.color, width=5)
