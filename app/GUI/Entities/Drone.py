import math
import PIL.Image
import PIL.ImageTk

# Import widgets - these will be imported from the Widgets module
from GUI.Widgets.DroneWidgets import DroneInfoBox, jobInfoContainer, jobInfoItem


class Drone:

    def __init__(self, map_widget, info_container, job_container, drone_id, system_status, gui_ref):
        self.gui_ref = gui_ref
        self.map_widget = map_widget
        self.info_container = info_container
        self.job_container = job_container
        self.id = drone_id
        self.system_status = system_status
        self.position = None
        self.marker = None
        self.heading_path = None
        self.altitude = None
        self.relative_altitude = None
        self.heading = None
        self.roll = None
        self.pitch = None
        self.yaw = None
        self.active_job = None
        self.job_list = []
        self.active_job_path = None
        self.active_job_start_pos = None
        self.showing_active_job_path = False
        self.id_of_job_with_path = None
        self.info_widget = DroneInfoBox(info_container, drone_id, self)
        self.job_info_container = jobInfoContainer(job_container, drone_id)
        if drone_id == 1:
            self.color = "red"
        elif drone_id == 2:
            self.color = "blue"
        elif drone_id == 3:
            self.color = "green"
        elif drone_id == 4:
            self.color = "yellow"
        else:
            self.color = "gray"

    """
        Okay, so this is the one that displays the drone's positions.
    """
    def setPosition(self, lat, lon, altitude, relative_altitude, heading, vx, vy, vz):
        # Coordinates are already converted to decimal degrees by GUI.py
        self.position = (lat, lon)
        self.altitude = altitude
        self.relative_altitude = relative_altitude
        converted_heading = heading / 1e2
        self.vx = vx
        self.vy = vy
        self.vz = vz
        # set marker on map
        if self.marker is None:
            self.marker = self.map_widget.set_marker(lat, lon, icon_anchor="center", text=f"Drone {self.id}", icon=self._load_icon("./assets/camera-drone.png"), font=("Arial", 12, "bold"))
        else:
            self.marker.set_position(lat, lon)

        # create heading path on map
        # calculate 10m point based on heading
        heading_rad = math.radians(converted_heading)
        lat_offset = 0.0005 * math.cos(heading_rad)
        lon_offset = 0.0005 * math.sin(heading_rad)
        if self.heading_path is not None:
            self.heading_path.delete()
            self.heading_path = None
        self.heading_path = self.map_widget.set_path(position_list=[(lat, lon), (lat + lat_offset, lon + lon_offset)], width=2, color="red")

        # calculate velocity
        velocity = math.hypot(vx, vy)
        velocity = velocity * 0.01 # convert cm/s to m/s
        # update info widget
        self.info_widget.updatePos(self.position, self.relative_altitude, velocity, converted_heading)

    def setTelemetry(self, roll, pitch, yaw):
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

    def setStatus(self, system_status):
        self.system_status = system_status
        self.info_widget.updateStatus(system_status)

    def _load_icon(self, path):
        image = PIL.Image.open(path)
        image = image.resize((50, 50))
        return PIL.ImageTk.PhotoImage(image)

    def move(self, lat_offset, lon_offset):
        new_lat = self.position[0] + lat_offset
        new_lon = self.position[1] + lon_offset
        self.position = (new_lat, new_lon)
        self.marker.set_position(new_lat, new_lon)

    def update_jobs(self, active_job, job_list):
        self.active_job = active_job
        self.job_list = job_list
        print(f"Active Job: {self.active_job}")
        print(f"Job List: {self.job_list}")

        # Step 1: Clear old widgets
        def clear_widgets():
            for widget in self.job_info_container.job_scrollable_frame.winfo_children():
                widget.destroy()


            # Step 2: Add new jobs only if they exist
            if active_job:
                jobInfoItem(self.job_info_container.job_scrollable_frame, active_job, 0, self, active=True )
                if self.showing_active_job_path:
                    trimmed_path = []
                    # add current position to path
                    if self.active_job_start_pos is not None:
                        if self.id_of_job_with_path == active_job.job_id:
                            trimmed_path.append(self.position)
                        else:
                            self.active_job_start_pos = self.position
                            self.id_of_job_with_path = active_job.job_id
                            trimmed_path.append(self.position)
                            self.active_job_path.delete()
                    else:
                        self.active_job_start_pos = self.position
                        self.id_of_job_with_path = active_job.job_id
                        trimmed_path.append(self.position)
                    print(f"last visited waypoint: {active_job.last_waypoint}")
                    for i in range(active_job.last_waypoint, len(active_job.waypoints)):
                        trimmed_path.append((active_job.waypoints[i][0], active_job.waypoints[i][1]))
                    if self.active_job_path is not None:
                        self.active_job_path.delete()
                    if len(trimmed_path) > 1:
                        self.active_job_path = self.map_widget.set_path(position_list = trimmed_path, width=5, color=self.color)
            else:
                self.active_job_path.delete()
                self.active_job_path = None
                self.active_job_start_pos = None
                self.id_of_job_with_path = None


            for i, job in enumerate(job_list):
                jobInfoItem(self.job_info_container.job_scrollable_frame, job, i + 1)

        # Use `after` to avoid accessing destroyed widgets immediately
        self.map_widget.after(100, clear_widgets)

    def toggle_show_active_job_path(self):
        if self.active_job_path is not None:
            self.active_job_path.delete()
            self.active_job_path = None
        else:
            # Recreate the path if needed
            if self.active_job is not None:
                trimmed_path = []
                # add current position to path
                if self.active_job_start_pos is not None:
                    trimmed_path.append(self.position)
                else:
                    self.active_job_start_pos = self.position
                    trimmed_path.append(self.position)
                for i in range(self.active_job.last_waypoint, len(self.active_job.waypoints)):
                    trimmed_path.append((self.active_job.waypoints[i][0], self.active_job.waypoints[i][1]))
                if len(trimmed_path) > 1:
                    self.active_job_path = self.map_widget.set_path(position_list = trimmed_path, width=5, color=self.color)
