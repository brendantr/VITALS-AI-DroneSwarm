import ast
import customtkinter
import tkintermapview
import PIL.Image
import PIL.ImageTk

from TerrainPreProcessing.check_internet import has_internet
from GUI.Entities.Drone import Drone
from GUI.Entities.Job import Job
from GUI.Entities.POI import POI
from GUI.Widgets.ChatSidebar import ChatSidebar


class MapPage(customtkinter.CTkFrame):
    def __init__(self, parent, switch_to_home, gui_ref, **kwargs):
        super().__init__(parent, **kwargs)
        self.gui_ref = gui_ref
        self.switch_to_home = switch_to_home
        self.polygons = []
        self.drones = []
        self.polygon_points = []
        self.jobs = []
        self.pois = []
        self.first_polygon_point = False
        self.editing_polygon = False
        self.debug_window = None

        # GCS placement preview
        self.gcs_preview_marker = None
        self.gcs_motion_binding = None
        self._load_gcs_icon()

        # Left sidebar
        self.sidebar = customtkinter.CTkFrame(self)
        self.sidebar.grid(row=0, column=0, sticky="nsw", rowspan=2)
        self.sidebar.grid_columnconfigure(0, weight=1)

        sidebar_title = customtkinter.CTkLabel(
            self.sidebar, text="VITALS", font=("Arial", 20)
        )
        sidebar_title.grid(row=0, column=0, pady=10, padx=20, sticky="w")

        # move_drone_test_button = customtkinter.CTkButton(
        #     self.sidebar, text="Move Drone Test", command=self.move_marker
        # )
        # move_drone_test_button.grid(row=1, column=0, pady=10, padx=20, sticky="w")

        self.start_polygon_button = customtkinter.CTkButton(
            self.sidebar, text="Start Creating Polygon", state="disabled", command=self.start_creating_polygon
        )
        self.start_polygon_button.grid(row=3, column=0, pady=10, padx=20, sticky="w")

        # Polygon editing buttons frame (hidden by default)
        self.polygon_edit_frame = customtkinter.CTkFrame(self.sidebar, fg_color="transparent")

        self.undo_polygon_button = customtkinter.CTkButton(
            self.polygon_edit_frame, text="Undo Last Point", width=80, command=self.undo_last_polygon_point
        )
        self.undo_polygon_button.pack(side="left", padx=5)

        self.reset_polygon_button = customtkinter.CTkButton(
            self.polygon_edit_frame, text="Reset", width=60, command=self.reset_polygon
        )
        self.reset_polygon_button.pack(side="left", padx=5)

        self.connect_button = customtkinter.CTkButton(
            self.sidebar, text="Connect to Mavlink", command=self.gui_ref.call_mavlink_connection
        )
        self.connect_button.grid(row=1, column=0, pady=10, padx=20, sticky="w")

        self.place_gcs_button = customtkinter.CTkButton(
            self.sidebar, text="Place GCS", state="disabled", command=self.toggle_gcs_placement
        )
        self.place_gcs_button.grid(row=2, column=0, pady=10, padx=20, sticky="w")

        self.end_mission_button = customtkinter.CTkButton(
            self.sidebar, text="Start Mission", state="disabled", command=self.gui_ref.call_start_mission
        )
        self.end_mission_button.grid(row=4, column=0, pady=10, padx=20, sticky="w")

        self.view_path_button = customtkinter.CTkButton(
            self.sidebar, text="View Path Plan", state="disabled", command=self.show_path_visualization
        )
        self.view_path_button.grid(row=5, column=0, pady=10, padx=20, sticky="w")

        self.debug_button = customtkinter.CTkButton(
            self.sidebar, text="Debug Menu", command=self.open_debug_popup
        )
        self.debug_button.grid(row=6, column=0, pady=10, padx=20, sticky="w")

        # Back button
        back_button = customtkinter.CTkButton(
            self.sidebar, text="Back to Home", command=self.switch_to_home
        )
        back_button.grid(row=7, column=0, pady=10, padx=20, sticky="w")

        # drone info container
        self.drone_info_container = customtkinter.CTkFrame(self.sidebar)
        self.drone_info_container.grid(row=8, column=0, pady=10, padx=20, rowspan=8, sticky="nsew")
        self.drone_info_Label = customtkinter.CTkLabel(self.drone_info_container, text="Drones", font=("Arial", 20))
        self.drone_info_Label.grid(row=0, column=0, pady=10, padx=20, sticky="nsew")

        # Map frame
        self.map_frame = customtkinter.CTkFrame(self)
        self.map_frame.grid(row=0, column=1, sticky="nsew", rowspan=2)

        self.map_widget = tkintermapview.TkinterMapView(
            self.map_frame, width=600, height=600, corner_radius=20
        )

        #Use this for offline demonstrations.
        if not has_internet():
            self.map_widget.set_tile_server("http://localhost:8080/tile/{z}/{x}/{y}.png")
        self.map_widget.pack(fill="both", expand=False, padx=20, pady=20)
        #UCF Position: 28.6026251, -81.1999887
        self.map_widget.set_position(28.5477810, -80.8481593)
        self.map_widget.add_left_click_map_command(self.left_click_event)

        #bottom frame
        self.bottom_frame = customtkinter.CTkFrame(self)
        self.bottom_frame.grid(row=1, column=1, sticky="nsew")

        # Grid configuration for job lists
        self.bottom_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        # Grid configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=2)  # 2/3 height for map
        self.grid_rowconfigure(1, weight=1)  # 1/3 height for bottom frame

        #RightClick Menu
        self.map_widget.add_right_click_menu_command(label="Add Job Waypoint", command=self.gui_ref.add_job_waypoint, pass_coords=True)
        self.map_widget.add_right_click_menu_command(label="Create POI", command=self.create_test_poi, pass_coords=True)

        # Collapsible right sidebar
        self.collapsible_sidebar = ChatSidebar(self, self.gui_ref)
        self.collapsible_sidebar.grid(row=0, column=2, sticky="nsew")

        #POI Info Frame
        self.poi_info_container = customtkinter.CTkScrollableFrame(self, width=200, height=200)
        self.poi_info_container.grid(row=1, column=2, pady=10, padx=20, sticky="nsew")
        self.poi_info_Label = customtkinter.CTkLabel(self.poi_info_container, text="POIs", font=("Arial", 20))
        self.poi_info_Label.grid(row=0, column=0, pady=10, padx=20, sticky="nsew")

        # Grid configuration
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def set_missionID(self, mission_id):
        self.mission_id = mission_id
        self.missionState.set_missionID(mission_id)

    def open_debug_popup(self):
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()  # Bring to front if already open
            return

        self.debug_window = customtkinter.CTkToplevel(self)
        self.debug_window.title("Debugging Menu")
        self.debug_window.geometry("300x600")
        self.debug_window.resizable(False, False)

        # Ensure the window does not close instantly
        self.debug_window.after(100, lambda: self.debug_window.focus_force())

        # Prevent accidental closure
        self.debug_window.protocol("WM_DELETE_WINDOW", self.close_debug_popup)
        #target drone input
        target_drone_label = customtkinter.CTkLabel(self.debug_window, text="Target Drone ID (1-4):")
        target_drone_label.pack(pady=10)

        self.target_drone_entry = customtkinter.CTkEntry(self.debug_window)
        self.target_drone_entry.pack(pady=10)

        #use waypoints input
        use_waypoints_label = customtkinter.CTkLabel(self.debug_window, text="Use Waypoints (1-4):")
        use_waypoints_label.pack(pady=10)
        self.use_waypoints_entry = customtkinter.CTkEntry(self.debug_window)
        self.use_waypoints_entry.pack(pady=10)
        #debugging tools

        debug_label = customtkinter.CTkLabel(self.debug_window, text="Debugging Tools", font=("Arial", 16, "bold"))
        debug_label.pack(pady=10)

        btn_test_move = customtkinter.CTkButton(self.debug_window, text="Test Move Drone", command=self.move_marker)
        btn_test_move.pack(pady=5)

        btn_test_arm = customtkinter.CTkButton(self.debug_window, text="Test Arm Drone", command=self.gui_ref.call_arm_mission)
        btn_test_arm.pack(pady=5)

        btn_test_takeoff = customtkinter.CTkButton(self.debug_window, text="Test Takeoff", command=self.gui_ref.call_takeoff_mission)
        btn_test_takeoff.pack(pady=5)

        btn_send_waypoints = customtkinter.CTkButton(self.debug_window, text="Send Waypoints", command=self.gui_ref.call_send_waypoints)
        btn_send_waypoints.pack(pady=5)

        btn_return_home = customtkinter.CTkButton(self.debug_window, text="Return to Launch", command=self.gui_ref.call_return_to_launch)
        btn_return_home.pack(pady=5)

        btn_request_mission_list = customtkinter.CTkButton(self.debug_window, text="Request Mission List", command=self.gui_ref.call_request_mission_list)
        btn_request_mission_list.pack(pady=5)

        btn_add_test_job = customtkinter.CTkButton(self.debug_window, text="Add Test Job", command=self.gui_ref.call_create_test_job)
        btn_add_test_job.pack(pady=5)

        btn_investigate_poi = customtkinter.CTkButton(self.debug_window, text="Investigate POI", command=self.gui_ref.call_investigate_poi)
        btn_investigate_poi.pack(pady=5)

        btn_simulate_image_detection = customtkinter.CTkButton(self.debug_window, text="Simulate Image Detection", command=self.gui_ref.call_simulate_image_detection)
        btn_simulate_image_detection.pack(pady=5)

        btn_close = customtkinter.CTkButton(self.debug_window, text="Close", command=self.close_debug_popup)
        btn_close.pack(pady=10)

    def get_target_debug_drone(self):
        try:
            return int(self.target_drone_entry.get())
        except ValueError:
            return None

    def get_debug_waypoints(self):
        try:
            return int(self.use_waypoints_entry.get())
        except ValueError:
            return None

    def close_debug_popup(self):
        """Closes the debug popup properly"""
        if self.debug_window is not None:
            self.debug_window.destroy()
            self.debug_window = None

    def show_path_visualization(self):
        """Opens the path visualization window on-demand."""
        self.gui_ref.missionState.showPathVisualization()

    def add_job(self, drone_id, job_text, inprogress=False):
        """
        Adds a new job to the scrollable frame for the given drone_id (1-4).
        """
        if inprogress:
            color = "#1F6AA5"
        else:
            color = "#5C5C5C"
        if 1 <= drone_id <= 4:
            job_frame = customtkinter.CTkFrame(self.job_lists[drone_id - 1], )
            job_frame.pack(fill="x", padx=5, pady=5)

            job_label = customtkinter.CTkLabel(job_frame, text=job_text, font=("Arial", 14), fg_color=color, text_color="white", corner_radius=4)
            job_label.pack(fill="both", expand=True, padx=5, pady=5)

    def _add_drone(self, drone_id, system_status):
        newdrone = Drone(self.map_widget, self.drone_info_container, self.bottom_frame, drone_id, system_status, self.gui_ref)
        self.drones.append(newdrone)

    def left_click_event(self, coordinates_tuple):
        if self.gui_ref.isAddingDetectionPoints:
            self.gui_ref.add_detection_point({"lat": coordinates_tuple[0], "lon": coordinates_tuple[1], "num_hits": 0})
            return
        if self.first_polygon_point:
            self.polygon_points.append(coordinates_tuple)
            self.polygon = self.map_widget.set_polygon(self.polygon_points, fill_color=None)
            self.first_polygon_point = False
            return
        elif self.editing_polygon:
            self.polygon_points.append(coordinates_tuple)
            # Delete and recreate the polygon to ensure consistency with undo
            if self.polygon is not None:
                self.polygon.delete()
            self.polygon = self.map_widget.set_polygon(self.polygon_points, fill_color=None)
            return
        elif self.gui_ref.choosing_gcs_location:
            # Directly place the GCS marker without confirmation popup
            self.gui_ref.set_gcs_location(coordinates_tuple)
            return
        else:
            pass

    def move_marker(self):
        if self.drones:
            self.drones[0].move(0.0001, 0.0001)

    def create_drone_job(self, job_name, drone_id, waypoints, spacing=0):
        #convert waypoints to list of tuples
        list_of_tuples = [tuple(i) for i in ast.literal_eval(waypoints)]

        # draw path on map
        path_obj = self.map_widget.set_path(position_list=list_of_tuples, width=5, color="red")
        print("Job Created")
        # create job object
        job = Job(job_name, drone_id, list_of_tuples, path_obj)
        self.jobs.append(job)

    def start_creating_polygon(self):
        if self.editing_polygon:
            # Finishing polygon editing
            self.editing_polygon = False
            self.start_polygon_button.configure(text="Mission Area Created")
            self.start_polygon_button.configure(state="disabled")
            # Hide polygon edit buttons and restore button positions
            self.polygon_edit_frame.grid_forget()
            self.end_mission_button.grid(row=4, column=0, pady=10, padx=20, sticky="w")
            self.view_path_button.grid(row=5, column=0, pady=10, padx=20, sticky="w")
            self.view_path_button.configure(state="normal")
            self.debug_button.grid(row=6, column=0, pady=10, padx=20, sticky="w")
            self.polygon.name = "Mission Area"
            self.gui_ref.sendMissionPolygon(self.polygon_points)
            if(self.gui_ref.isSimulation):
                self.gui_ref.start_adding_detection_points()
                self.gui_ref.create_system_chat_message("Mission Area has been defined and terrain has been processed. For the simulation, please add detection points to the map. When you are done, right click the map and select 'Finish Adding Detection Points'")
            else:
                # Real mission - enable start button directly without requiring detection points
                self.gui_ref.create_system_chat_message("Mission Area has been defined. You can now begin the mission.")
                self.end_mission_button.configure(state="normal")

            print(self.polygon_points)
        else:
            # Starting polygon editing
            self.first_polygon_point = True
            self.editing_polygon = True
            # Disable GCS button once polygon drawing starts
            self.place_gcs_button.configure(state="disabled")
            # Show polygon edit buttons below the polygon button
            self.polygon_edit_frame.grid(row=4, column=0, pady=(0, 10), padx=20, sticky="w")
            # Shift other buttons down
            self.end_mission_button.grid(row=5, column=0, pady=10, padx=20, sticky="w")
            self.view_path_button.grid(row=6, column=0, pady=10, padx=20, sticky="w")
            self.debug_button.grid(row=7, column=0, pady=10, padx=20, sticky="w")
            # change button text
            self.start_polygon_button.configure(text="Finish Creating Polygon")

    def create_test_job(self):
        job = Job((28.6037837, -81.2018019), [(28.6037837, -81.2018019), (28.6037931, -81.2008148), (28.6037366, -81.1983150)], (28.6037366, -81.1983150), None)
        print(job.start)
        print(job.waypoints)
        print(job.end)
        self.map_widget.set_path(position_list=job.waypoints, width=5, color="red")
        print("Job Created")

    def get_polygon_points(self):
        return self.polygon_points

    def undo_last_polygon_point(self):
        """Remove the last placed polygon point."""
        if len(self.polygon_points) == 0:
            return

        # Remove the last point
        self.polygon_points.pop()

        # Delete the current polygon
        if hasattr(self, 'polygon') and self.polygon is not None:
            self.polygon.delete()
            self.polygon = None

        # Recreate the polygon with remaining points
        if len(self.polygon_points) > 0:
            self.polygon = self.map_widget.set_polygon(self.polygon_points, fill_color=None)
            self.first_polygon_point = False
        else:
            # No points left, ready for first point again
            self.first_polygon_point = True

        self.gui_ref.create_system_chat_message(f"Removed last point. {len(self.polygon_points)} points remaining.")

    def reset_polygon(self):
        """Clear all polygon points and start over."""
        # Clear the points list
        self.polygon_points = []

        # Delete the current polygon
        if hasattr(self, 'polygon') and self.polygon is not None:
            self.polygon.delete()
            self.polygon = None

        # Reset to initial state
        self.first_polygon_point = True

        self.gui_ref.create_system_chat_message("Polygon reset. Click on the map to start placing points.")

    def reset_for_new_mission(self):
        """Reset MapPage state for a new mission."""
        # Clear polygon
        self.polygon_points = []
        if hasattr(self, 'polygon') and self.polygon is not None:
            self.polygon.delete()
            self.polygon = None
        self.first_polygon_point = False
        self.editing_polygon = False

        # Clear POIs from map
        for poi in self.pois:
            if hasattr(poi, 'marker') and poi.marker is not None:
                poi.marker.delete()
            if hasattr(poi, 'info_widget') and poi.info_widget is not None:
                poi.info_widget.poi_info.destroy()
        self.pois = []

        # Reset button states
        self.connect_button.configure(state="normal", text="Connect to Mavlink")
        self.place_gcs_button.configure(state="disabled", text="Place GCS")
        self.start_polygon_button.configure(state="disabled", text="Start Creating Polygon")
        self.end_mission_button.configure(state="disabled", text="Start Mission", command=self.gui_ref.call_start_mission)
        self.view_path_button.configure(state="disabled")

        # Restore button grid positions
        self.polygon_edit_frame.grid_forget()
        self.end_mission_button.grid(row=4, column=0, pady=10, padx=20, sticky="w")
        self.view_path_button.grid(row=5, column=0, pady=10, padx=20, sticky="w")
        self.debug_button.grid(row=6, column=0, pady=10, padx=20, sticky="w")

        # Show/hide debug button based on mission type
        if self.gui_ref.isSimulation:
            self.debug_button.grid(row=6, column=0, pady=10, padx=20, sticky="w")
        else:
            self.debug_button.grid_forget()

    def add_poi(self, lat, lon, name, description=""):
        poi_count = len(self.pois) + 1
        poi = POI(lat, lon, name, description, self.map_widget, self.poi_info_container, poi_count, self.gui_ref)
        self.pois.append(poi)
        self.gui_ref.callAddPoiInMissionState(poi)
        return poi_count

    def create_test_poi(self, coords):
        poi_count = len(self.pois) + 1
        self.add_poi(coords[0], coords[1], f"POI {poi_count}")

    def toggle_gcs_placement(self):
        """Toggle between placing and removing GCS."""
        if self.gui_ref.gcs_marker is None:
            if self.gui_ref.choosing_gcs_location:
                # Cancel placement mode
                self.cancel_gcs_placement()
            else:
                # Enable GCS placement mode
                self.gui_ref.choosing_gcs_location = True
                self.place_gcs_button.configure(text="Cancel Placement")
                self.gui_ref.create_system_chat_message("Move cursor over map to preview GCS location. Click to place.")

                # Create the preview marker at the current map center
                center_lat, center_lon = self.map_widget.get_position()
                if self.gcs_icon:
                    self.gcs_preview_marker = self.map_widget.set_marker(
                        center_lat, center_lon,
                        text="GCS Preview",
                        icon=self.gcs_icon,
                        icon_anchor="center"
                    )
                else:
                    self.gcs_preview_marker = self.map_widget.set_marker(
                        center_lat, center_lon,
                        text="GCS Preview"
                    )

                # Bind mouse motion to update preview marker position
                self.gcs_motion_binding = self.map_widget.canvas.bind("<Motion>", self.update_gcs_preview)
        else:
            # Remove the GCS marker
            self.gui_ref.gcs_marker.delete()
            self.gui_ref.gcs_marker = None
            self.gui_ref.gcs_location = None
            self.place_gcs_button.configure(text="Place GCS")
            self.start_polygon_button.configure(state="disabled")
            self.gui_ref.create_system_chat_message("GCS location removed.")

    def _load_gcs_icon(self):
        """Load the GCS icon for use in markers."""
        try:
            gcs_icon_path = "./assets/gcs.png"
            image = PIL.Image.open(gcs_icon_path)
            image = image.resize((50, 50))
            self.gcs_icon = PIL.ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"Failed to load GCS icon: {e}")
            self.gcs_icon = None

    def update_gcs_preview(self, event):
        """Update the preview marker position as mouse moves over the map."""
        if not self.gui_ref.choosing_gcs_location or self.gcs_preview_marker is None:
            return

        # Convert canvas coordinates to lat/lon
        coords = self.map_widget.convert_canvas_coords_to_decimal_coords(event.x, event.y)
        if coords is None:
            return

        lat, lon = coords

        # Update the existing marker's position
        self.gcs_preview_marker.set_position(lat, lon)

    def cancel_gcs_placement(self):
        """Cancel GCS placement mode and clean up preview."""
        self.gui_ref.choosing_gcs_location = False
        self.place_gcs_button.configure(text="Place GCS")

        # Remove preview marker
        if self.gcs_preview_marker is not None:
            self.gcs_preview_marker.delete()
            self.gcs_preview_marker = None

        # Unbind motion event
        if self.gcs_motion_binding is not None:
            self.map_widget.canvas.unbind("<Motion>", self.gcs_motion_binding)
            self.gcs_motion_binding = None

        self.gui_ref.create_system_chat_message("GCS placement cancelled.")

    def finalize_gcs_placement(self):
        """Clean up preview after GCS has been placed."""
        # Remove preview marker
        if self.gcs_preview_marker is not None:
            self.gcs_preview_marker.delete()
            self.gcs_preview_marker = None

        # Unbind motion event
        if self.gcs_motion_binding is not None:
            self.map_widget.canvas.unbind("<Motion>", self.gcs_motion_binding)
            self.gcs_motion_binding = None
