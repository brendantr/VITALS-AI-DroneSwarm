from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QDialog, QLineEdit
)
from PyQt6.QtCore import Qt

from GUI.Entities.Drone import Drone
from GUI.Entities.POI import POI
from GUI.Widgets.LeafletMap import LeafletMap
from GUI.Widgets.ChatSidebar import ChatSidebar


class MapPage(QWidget):
    def __init__(self, gui_ref, **kwargs):
        super().__init__(**kwargs)
        self.gui_ref = gui_ref
        self.drones = []
        self.polygon_points = []
        self.jobs = []
        self.pois = []
        self.first_polygon_point = False
        self.editing_polygon = False
        self.debug_dialog = None
        self.gcs_preview_marker_id = None

        # ── Main horizontal layout: sidebar | center | right ──
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ═══════════════════════════════════════════════════════
        # LEFT SIDEBAR
        # ═══════════════════════════════════════════════════════
        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            "QFrame { background-color: #16213e; border-right: 1px solid #0f3460; }"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(8)

        title = QLabel("VITALS")
        title.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #e0e0e0; "
            "border: none; background: transparent;"
        )
        sidebar_layout.addWidget(title)

        # Connect to Mavlink
        self.connect_button = QPushButton("Connect to Mavlink")
        self.connect_button.clicked.connect(self.gui_ref.call_mavlink_connection)
        sidebar_layout.addWidget(self.connect_button)

        # Place GCS
        self.place_gcs_button = QPushButton("Place GCS")
        self.place_gcs_button.setEnabled(False)
        self.place_gcs_button.clicked.connect(self.toggle_gcs_placement)
        sidebar_layout.addWidget(self.place_gcs_button)

        # Start Creating Polygon
        self.start_polygon_button = QPushButton("Start Creating Polygon")
        self.start_polygon_button.setEnabled(False)
        self.start_polygon_button.clicked.connect(self.start_creating_polygon)
        sidebar_layout.addWidget(self.start_polygon_button)

        # Polygon edit frame (hidden by default)
        self.polygon_edit_frame = QWidget()
        self.polygon_edit_frame.setStyleSheet("background: transparent;")
        polygon_edit_layout = QHBoxLayout(self.polygon_edit_frame)
        polygon_edit_layout.setContentsMargins(0, 0, 0, 0)
        polygon_edit_layout.setSpacing(4)

        undo_btn = QPushButton("Undo Last")
        undo_btn.clicked.connect(self.undo_last_polygon_point)
        polygon_edit_layout.addWidget(undo_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self.reset_polygon)
        polygon_edit_layout.addWidget(reset_btn)

        self.polygon_edit_frame.setVisible(False)
        sidebar_layout.addWidget(self.polygon_edit_frame)

        # Start / End Mission
        self.end_mission_button = QPushButton("Start Mission")
        self.end_mission_button.setEnabled(False)
        self.end_mission_button.clicked.connect(self.gui_ref.call_start_mission)
        sidebar_layout.addWidget(self.end_mission_button)

        # View Path Plan
        self.view_path_button = QPushButton("View Path Plan")
        self.view_path_button.setEnabled(False)
        self.view_path_button.clicked.connect(self.show_path_visualization)
        sidebar_layout.addWidget(self.view_path_button)

        # Debug Menu
        self.debug_button = QPushButton("Debug Menu")
        self.debug_button.clicked.connect(self.open_debug_popup)
        sidebar_layout.addWidget(self.debug_button)

        # Back to Home
        back_button = QPushButton("Back to Home")
        back_button.clicked.connect(self.gui_ref.show_home_page)
        sidebar_layout.addWidget(back_button)

        # ── Drone info section ────────────────────────────────
        drone_section_label = QLabel("Drones")
        drone_section_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e0e0e0; "
            "border: none; background: transparent;"
        )
        sidebar_layout.addWidget(drone_section_label)

        drone_scroll = QScrollArea()
        drone_scroll.setWidgetResizable(True)
        drone_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.drone_info_container = QWidget()
        self.drone_info_container.setStyleSheet("background: transparent;")
        self.drone_info_layout = QVBoxLayout(self.drone_info_container)
        self.drone_info_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.drone_info_layout.setContentsMargins(0, 0, 0, 0)
        self.drone_info_layout.setSpacing(6)

        drone_scroll.setWidget(self.drone_info_container)
        sidebar_layout.addWidget(drone_scroll, stretch=1)

        main_layout.addWidget(sidebar)

        # ═══════════════════════════════════════════════════════
        # CENTER AREA (map + bottom job frame)
        # ═══════════════════════════════════════════════════════
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # Map
        self.map_widget = LeafletMap()
        self.map_widget.map_clicked.connect(self.left_click_event)
        self.map_widget.set_position(28.5477810, -80.8481593)
        center_layout.addWidget(self.map_widget, stretch=2)

        # Bottom frame for job info
        self.bottom_frame = QFrame()
        self.bottom_frame.setStyleSheet(
            "QFrame { background-color: #16213e; border-top: 1px solid #0f3460; }"
        )
        self.bottom_frame_layout = QHBoxLayout(self.bottom_frame)
        self.bottom_frame_layout.setContentsMargins(8, 8, 8, 8)
        self.bottom_frame_layout.setSpacing(8)
        self.bottom_frame_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.bottom_frame.setMinimumHeight(180)
        self.bottom_frame.setMaximumHeight(250)
        center_layout.addWidget(self.bottom_frame)

        main_layout.addWidget(center, stretch=1)

        # ═══════════════════════════════════════════════════════
        # RIGHT AREA (chat + POI info)
        # ═══════════════════════════════════════════════════════
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Chat sidebar
        self.chat_sidebar = ChatSidebar(self.gui_ref)
        right_layout.addWidget(self.chat_sidebar, stretch=2)

        # POI info panel
        poi_frame = QFrame()
        poi_frame.setStyleSheet(
            "QFrame { background-color: #16213e; border-top: 1px solid #0f3460; }"
        )
        poi_frame_inner = QVBoxLayout(poi_frame)
        poi_frame_inner.setContentsMargins(8, 8, 8, 8)
        poi_frame_inner.setSpacing(4)

        poi_label = QLabel("POIs")
        poi_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #e0e0e0; "
            "border: none; background: transparent;"
        )
        poi_frame_inner.addWidget(poi_label)

        self.poi_scroll = QScrollArea()
        self.poi_scroll.setWidgetResizable(True)
        self.poi_scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.poi_info_container = QWidget()
        self.poi_info_container.setStyleSheet("background: transparent;")
        self.poi_info_layout = QVBoxLayout(self.poi_info_container)
        self.poi_info_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.poi_info_layout.setContentsMargins(0, 0, 0, 0)
        self.poi_info_layout.setSpacing(4)

        self.poi_scroll.setWidget(self.poi_info_container)
        poi_frame_inner.addWidget(self.poi_scroll, stretch=1)

        poi_frame.setMinimumHeight(180)
        poi_frame.setMaximumHeight(250)
        right_layout.addWidget(poi_frame)

        main_layout.addWidget(right)

        # ── Right-click context menu commands ─────────────────
        self.map_widget.add_right_click_menu_command(
            "Add Job Waypoint",
            lambda: self.gui_ref.add_job_waypoint(
                self.map_widget._last_right_click_pos
            )
        )
        self.map_widget.add_right_click_menu_command(
            "Create POI",
            lambda: self.create_test_poi(
                self.map_widget._last_right_click_pos
            )
        )

    # ── Map click handling ────────────────────────────────────

    def left_click_event(self, lat, lon):
        coordinates_tuple = (lat, lon)

        if self.gui_ref.isAddingDetectionPoints:
            self.gui_ref.add_detection_point(
                {"lat": lat, "lon": lon, "num_hits": 0}
            )
            return

        if self.first_polygon_point:
            self.polygon_points.append(coordinates_tuple)
            self.map_widget.set_polygon(
                "mission_polygon", self.polygon_points
            )
            self.first_polygon_point = False
            return

        elif self.editing_polygon:
            self.polygon_points.append(coordinates_tuple)
            self.map_widget.set_polygon(
                "mission_polygon", self.polygon_points
            )
            return

        elif self.gui_ref.choosing_gcs_location:
            self.gui_ref.set_gcs_location(coordinates_tuple)
            return

    # ── Polygon ───────────────────────────────────────────────

    def start_creating_polygon(self):
        if self.editing_polygon:
            # Finishing polygon editing
            self.editing_polygon = False
            self.start_polygon_button.setText("Mission Area Created")
            self.start_polygon_button.setEnabled(False)
            self.polygon_edit_frame.setVisible(False)
            self.view_path_button.setEnabled(True)

            self.gui_ref.sendMissionPolygon(self.polygon_points)

            if self.gui_ref.isSimulation:
                self.gui_ref.start_adding_detection_points()
                self.gui_ref.create_system_chat_message(
                    "Mission Area has been defined and terrain has been processed. "
                    "For the simulation, please add detection points to the map. "
                    "When you are done, right click the map and select "
                    "'Finish Adding Detection Points'"
                )
            else:
                # Real mission — enable start button directly
                self.gui_ref.create_system_chat_message(
                    "Mission Area has been defined. You can now begin the mission."
                )
                self.end_mission_button.setEnabled(True)

            print(self.polygon_points)
        else:
            # Starting polygon editing
            self.first_polygon_point = True
            self.editing_polygon = True
            self.place_gcs_button.setEnabled(False)
            self.polygon_edit_frame.setVisible(True)
            self.start_polygon_button.setText("Finish Creating Polygon")

    def undo_last_polygon_point(self):
        if len(self.polygon_points) == 0:
            return

        self.polygon_points.pop()

        if len(self.polygon_points) > 0:
            self.map_widget.set_polygon(
                "mission_polygon", self.polygon_points
            )
            self.first_polygon_point = False
        else:
            self.map_widget.remove_polygon("mission_polygon")
            self.first_polygon_point = True

        self.gui_ref.create_system_chat_message(
            f"Removed last point. {len(self.polygon_points)} points remaining."
        )

    def reset_polygon(self):
        self.polygon_points = []
        self.map_widget.remove_polygon("mission_polygon")
        self.first_polygon_point = True
        self.gui_ref.create_system_chat_message(
            "Polygon reset. Click on the map to start placing points."
        )

    def get_polygon_points(self):
        return self.polygon_points

    # ── GCS placement ─────────────────────────────────────────

    def toggle_gcs_placement(self):
        if self.gui_ref.gcs_marker_id is None:
            if self.gui_ref.choosing_gcs_location:
                # Cancel placement mode
                self.cancel_gcs_placement()
            else:
                # Enable GCS placement mode
                self.gui_ref.choosing_gcs_location = True
                self.place_gcs_button.setText("Cancel Placement")
                self.gui_ref.create_system_chat_message(
                    "Move cursor over map to preview GCS location. Click to place."
                )
                # Disable pointer events on all existing markers so clicks pass through to the map
                self.map_widget.set_all_markers_interactive(False)
                # Create non-interactive preview marker
                self.gcs_preview_marker_id = self.map_widget.add_marker(
                    0, 0, "GCS Preview", icon="gcs", interactive=False
                )
                self._gcs_mouse_conn = self.map_widget.map_mouse_move.connect(
                    self._update_gcs_preview
                )
        else:
            # Remove existing GCS marker
            self.map_widget.remove_marker(self.gui_ref.gcs_marker_id)
            self.gui_ref.gcs_marker_id = None
            self.gui_ref.gcs_location = None
            self.place_gcs_button.setText("Place GCS")
            self.start_polygon_button.setEnabled(False)
            self.gui_ref.create_system_chat_message("GCS location removed.")

    def _update_gcs_preview(self, lat, lon):
        """Move the preview marker as the mouse moves over the map."""
        if self.gui_ref.choosing_gcs_location and self.gcs_preview_marker_id:
            self.map_widget.move_marker(self.gcs_preview_marker_id, lat, lon)

    def cancel_gcs_placement(self):
        self.gui_ref.choosing_gcs_location = False
        self.place_gcs_button.setText("Place GCS")
        self._cleanup_gcs_preview()
        self.gui_ref.create_system_chat_message("GCS placement cancelled.")

    def finalize_gcs_placement(self):
        """Called after GCS has been placed successfully."""
        self._cleanup_gcs_preview()

    def _cleanup_gcs_preview(self):
        """Remove preview marker, disconnect mouse tracking, re-enable markers."""
        if hasattr(self, 'gcs_preview_marker_id') and self.gcs_preview_marker_id:
            self.map_widget.remove_marker(self.gcs_preview_marker_id)
            self.gcs_preview_marker_id = None
        # Re-enable pointer events on all markers
        self.map_widget.set_all_markers_interactive(True)
        try:
            self.map_widget.map_mouse_move.disconnect(self._update_gcs_preview)
        except TypeError:
            pass

    # ── Drone management ──────────────────────────────────────

    def _add_drone(self, drone_id, system_status):
        newdrone = Drone(
            self.map_widget, self.drone_info_container, self.bottom_frame,
            drone_id, system_status, self.gui_ref
        )
        self.drones.append(newdrone)
        # Explicitly add widgets to their parent layouts
        self.drone_info_layout.addWidget(newdrone.info_widget.frame)
        self.bottom_frame_layout.addWidget(newdrone.job_info_container.job_frame)

    def move_marker(self):
        if self.drones:
            self.drones[0].move(0.0001, 0.0001)

    # ── POI management ────────────────────────────────────────

    def add_poi(self, lat, lon, name, description=""):
        poi_count = len(self.pois) + 1
        poi = POI(
            lat, lon, name, description,
            self.map_widget, self.poi_info_container,
            poi_count, self.gui_ref
        )
        self.pois.append(poi)
        self.poi_info_layout.addWidget(poi.info_widget.frame)
        self.gui_ref.callAddPoiInMissionState(poi)
        return poi_count

    def create_test_poi(self, coords):
        poi_count = len(self.pois) + 1
        self.add_poi(coords[0], coords[1], f"POI {poi_count}")

    # ── Path visualization ────────────────────────────────────

    def show_path_visualization(self):
        self.gui_ref.missionState.showPathVisualization()

    # ── Debug popup ───────────────────────────────────────────

    def open_debug_popup(self):
        if self.debug_dialog is not None and self.debug_dialog.isVisible():
            self.debug_dialog.raise_()
            self.debug_dialog.activateWindow()
            return

        self.debug_dialog = DebugDialog(self, self.gui_ref)
        self.debug_dialog.show()

    def get_target_debug_drone(self):
        if self.debug_dialog and self.debug_dialog.target_drone_entry:
            try:
                return int(self.debug_dialog.target_drone_entry.text())
            except ValueError:
                return None
        return None

    def get_debug_waypoints(self):
        if self.debug_dialog and self.debug_dialog.use_waypoints_entry:
            try:
                return int(self.debug_dialog.use_waypoints_entry.text())
            except ValueError:
                return None
        return None

    # ── Mission reset ─────────────────────────────────────────

    def reset_for_new_mission(self):
        # Clear polygon
        self.polygon_points = []
        self.map_widget.remove_polygon("mission_polygon")
        self.first_polygon_point = False
        self.editing_polygon = False

        # Clear POIs from map and sidebar
        for poi in self.pois:
            if poi.marker_id:
                self.map_widget.remove_marker(poi.marker_id)
            if hasattr(poi, 'info_widget') and poi.info_widget is not None:
                poi.info_widget.frame.deleteLater()
        self.pois = []

        # Reset button states
        self.connect_button.setEnabled(True)
        self.connect_button.setText("Connect to Mavlink")
        self.place_gcs_button.setEnabled(False)
        self.place_gcs_button.setText("Place GCS")
        self.start_polygon_button.setEnabled(False)
        self.start_polygon_button.setText("Start Creating Polygon")
        self.end_mission_button.setEnabled(False)
        self.end_mission_button.setText("Start Mission")
        self.view_path_button.setEnabled(False)

        # Reconnect end_mission_button to start mission handler
        try:
            self.end_mission_button.clicked.disconnect()
        except TypeError:
            pass
        self.end_mission_button.clicked.connect(self.gui_ref.call_start_mission)

        # Hide polygon edit frame
        self.polygon_edit_frame.setVisible(False)

        # Show/hide debug button based on mission type
        self.debug_button.setVisible(self.gui_ref.isSimulation)

        # Close debug dialog if open
        if self.debug_dialog is not None and self.debug_dialog.isVisible():
            self.debug_dialog.close()
            self.debug_dialog = None


class DebugDialog(QDialog):
    def __init__(self, map_page, gui_ref, parent=None):
        super().__init__(parent)
        self.map_page = map_page
        self.gui_ref = gui_ref
        self.setWindowTitle("Debugging Menu")
        self.setFixedSize(300, 600)
        self.setWindowFlags(
            self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # Target drone input
        layout.addWidget(QLabel("Target Drone ID (1-4):"))
        self.target_drone_entry = QLineEdit()
        self.target_drone_entry.setPlaceholderText("1")
        layout.addWidget(self.target_drone_entry)

        # Waypoints input
        layout.addWidget(QLabel("Use Waypoints (1-4):"))
        self.use_waypoints_entry = QLineEdit()
        self.use_waypoints_entry.setPlaceholderText("1")
        layout.addWidget(self.use_waypoints_entry)

        # Section label
        debug_label = QLabel("Debugging Tools")
        debug_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(debug_label)

        # Debug action buttons
        buttons = [
            ("Test Move Drone", self.map_page.move_marker),
            ("Test Arm Drone", self.gui_ref.call_arm_mission),
            ("Test Takeoff", self.gui_ref.call_takeoff_mission),
            ("Send Waypoints", self.gui_ref.call_send_waypoints),
            ("Return to Launch", self.gui_ref.call_return_to_launch),
            ("Request Mission List", self.gui_ref.call_request_mission_list),
            ("Add Test Job", self.gui_ref.call_create_test_job),
            ("Investigate POI", self.gui_ref.call_investigate_poi),
            ("Simulate Image Detection", self.gui_ref.call_simulate_image_detection),
        ]

        for text, callback in buttons:
            btn = QPushButton(text)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
