import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QDialog, QFrame,
    QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt


class jobInfoContainer:
    def __init__(self, parent_widget, drone_id):
        self.drone_id = drone_id

        self.job_frame = QFrame(parent_widget)
        self.job_frame.setProperty("cssClass", "card")
        self.job_frame.setStyleSheet(
            "QFrame { background-color: #16213e; border: 1px solid #0f3460; border-radius: 8px; }"
        )

        frame_layout = QVBoxLayout(self.job_frame)
        frame_layout.setContentsMargins(6, 6, 6, 6)
        frame_layout.setSpacing(4)

        self.job_label = QLabel(f"Drone {drone_id} Jobs")
        self.job_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #e0e0e0; border: none;")
        frame_layout.addWidget(self.job_label)

        # Scrollable area for job items
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setMaximumHeight(220)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.job_scrollable_widget = QWidget()
        self.job_scrollable_layout = QVBoxLayout(self.job_scrollable_widget)
        self.job_scrollable_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.job_scrollable_layout.setContentsMargins(2, 2, 2, 2)
        self.job_scrollable_layout.setSpacing(4)

        self.scroll_area.setWidget(self.job_scrollable_widget)
        frame_layout.addWidget(self.scroll_area)

    def clear_jobs(self):
        """Remove all job widgets from the scrollable area."""
        while self.job_scrollable_layout.count():
            item = self.job_scrollable_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()


class jobInfoItem:
    def __init__(self, parent_layout, job, drone=None, active=False):
        self.drone = drone
        self.active = active

        self.frame = QFrame()
        if active:
            self.frame.setProperty("cssClass", "job-active")
            self.frame.setStyleSheet(
                "QFrame { background-color: #0f3460; border-left: 3px solid #00e676; "
                "border-radius: 4px; padding: 6px; }"
            )
        else:
            self.frame.setProperty("cssClass", "job-queued")
            self.frame.setStyleSheet(
                "QFrame { background-color: #16213e; border-left: 3px solid #555555; "
                "border-radius: 4px; padding: 6px; }"
            )

        layout = QGridLayout(self.frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        type_label = QLabel(job.job_type)
        type_label.setStyleSheet("font-weight: bold; font-size: 11px; color: #e0e0e0; border: none; background: transparent;")
        layout.addWidget(type_label, 0, 0)

        status_label = QLabel(job.job_status)
        status_label.setStyleSheet("font-weight: bold; font-size: 10px; color: #aaa; border: none; background: transparent;")
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(status_label, 0, 1)

        wp_label = QLabel(f"Waypoints: {len(job.waypoints)}")
        wp_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(wp_label, 1, 0, 1, 2)

        last_wp_label = QLabel(f"Last Visited: {job.last_waypoint}")
        last_wp_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(last_wp_label, 2, 0, 1, 2)

        priority_label = QLabel(f"Priority: {job.job_priority}")
        priority_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(priority_label, 3, 0, 1, 2)

        if active and drone:
            self.frame.setCursor(Qt.CursorShape.PointingHandCursor)
            self.frame.mousePressEvent = lambda e: self._toggle_path()

        parent_layout.addWidget(self.frame)

    def _toggle_path(self):
        if self.drone:
            self.drone.toggle_show_active_job_path()
            self.drone.showing_active_job_path = not self.drone.showing_active_job_path


class DroneInfoBox:
    def __init__(self, parent_widget, drone_id, drone_ref):
        self.drone_ref = drone_ref
        self.parent_widget = parent_widget
        self.id = drone_id

        self.frame = QFrame(parent_widget)
        self.frame.setProperty("cssClass", "drone-card")
        self.frame.setStyleSheet(
            "QFrame { background-color: #0f3460; border: 1px solid #533483; border-radius: 8px; padding: 8px; }"
        )

        layout = QGridLayout(self.frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)

        # ID
        self.id_label = QLabel(f"ID: {drone_id}")
        self.id_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #e0e0e0; border: none; background: transparent;")
        layout.addWidget(self.id_label, 0, 0)

        # Status
        self.status_label = QLabel("Active")
        self.status_label.setStyleSheet(
            "font-weight: bold; font-size: 10px; color: #00e676; "
            "background: rgba(0, 230, 118, 0.15); border-radius: 4px; padding: 2px 8px; border: none;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.status_label, 0, 1)

        # Details
        self.position_label = QLabel("Position: Unknown")
        self.position_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(self.position_label, 1, 0, 1, 2)

        self.altitude_label = QLabel("Altitude: Unknown")
        self.altitude_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(self.altitude_label, 2, 0, 1, 2)

        self.velocity_label = QLabel("Velocity: Unknown")
        self.velocity_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(self.velocity_label, 3, 0, 1, 2)

        self.heading_label = QLabel("Heading: Unknown")
        self.heading_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(self.heading_label, 4, 0, 1, 2)

        self.settings_button = QPushButton("Settings")
        self.settings_button.setStyleSheet(
            "QPushButton { font-size: 11px; padding: 4px 8px; }"
        )
        self.settings_button.clicked.connect(self.open_settings)
        layout.addWidget(self.settings_button, 5, 0, 1, 2)

    def updatePos(self, position, altitude, velocity, heading):
        self.position_label.setText(f"Position: {position[0]:.7f}, {position[1]:.7f}")
        self.altitude_label.setText(f"Altitude: {altitude / 1000} m")
        self.velocity_label.setText(f"Velocity: {velocity:.2f}")
        self.heading_label.setText(f"Heading: {heading}")

    def open_settings(self):
        dialog = DroneSettingsDialog(
            self.id, self.drone_ref, self.parent_widget
        )
        dialog.exec()

    def updateStatus(self, status):
        status_map = {
            0: ("UnInit", "#78909c", "rgba(120, 144, 156, 0.15)"),
            1: ("Boot", "#78909c", "rgba(120, 144, 156, 0.15)"),
            2: ("Calibrating", "#ffab00", "rgba(255, 171, 0, 0.15)"),
            3: ("Standby", "#ffab00", "rgba(255, 171, 0, 0.15)"),
            4: ("Active", "#00e676", "rgba(0, 230, 118, 0.15)"),
            5: ("Critical", "#ff1744", "rgba(255, 23, 68, 0.15)"),
            6: ("Emergency", "#ff1744", "rgba(255, 23, 68, 0.15)"),
        }
        text, color, bg = status_map.get(status, ("Unknown", "#78909c", "rgba(120, 144, 156, 0.15)"))
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"font-weight: bold; font-size: 10px; color: {color}; "
            f"background: {bg}; border-radius: 4px; padding: 2px 8px; border: none;"
        )


class DroneSettingsDialog(QDialog):
    def __init__(self, drone_id, drone_ref, parent=None):
        super().__init__(parent)
        self.drone_id = drone_id
        self.drone_ref = drone_ref
        self.setWindowTitle(f"Settings for Drone {drone_id}")
        self.setFixedSize(320, 500)

        starting_alt = drone_ref.gui_ref.missionState.get_drone_operatingAltitude(drone_id)
        starting_model = drone_ref.gui_ref.missionState.get_drone_vision_model(drone_id)
        available_models = []
        models_dir = os.path.join(os.path.dirname(__file__), "..", "..", "vision-edge", "yolo_models")
        if os.path.isdir(models_dir):
            for filename in os.listdir(models_dir):
                if filename.endswith(".pt"):
                    available_models.append(filename[:-3])

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        title = QLabel(f"Settings for Drone {drone_id}")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Altitude
        layout.addWidget(QLabel("Operating Altitude (m):"))
        self.altitude_entry = QLineEdit()
        self.altitude_entry.setPlaceholderText(str(starting_alt))
        layout.addWidget(self.altitude_entry)

        # Vision model
        layout.addWidget(QLabel("Vision Model:"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(available_models)
        if starting_model and starting_model.endswith(".pt"):
            model_name = starting_model[:-3]
            idx = self.model_combo.findText(model_name)
            if idx >= 0:
                self.model_combo.setCurrentIndex(idx)
        layout.addWidget(self.model_combo)

        # Camera settings
        layout.addWidget(QLabel("Camera Mount Angle (degrees):"))
        self.mount_angle_entry = QLineEdit()
        self.mount_angle_entry.setPlaceholderText("-5")
        layout.addWidget(self.mount_angle_entry)

        layout.addWidget(QLabel("Vertical FOV (degrees):"))
        self.vertical_fov_entry = QLineEdit()
        self.vertical_fov_entry.setPlaceholderText("60")
        layout.addWidget(self.vertical_fov_entry)

        layout.addWidget(QLabel("Horizontal FOV (degrees):"))
        self.horizontal_fov_entry = QLineEdit()
        self.horizontal_fov_entry.setPlaceholderText("80")
        layout.addWidget(self.horizontal_fov_entry)

        layout.addStretch()

        # Buttons
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setProperty("cssClass", "primary")
        save_btn.clicked.connect(lambda: self.save_settings(starting_alt, starting_model))
        btn_layout.addWidget(save_btn)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def save_settings(self, starting_alt, starting_model):
        alt_text = self.altitude_entry.text().strip()
        model = self.model_combo.currentText()

        if alt_text:
            try:
                alt = int(alt_text)
                if alt < 0:
                    raise ValueError("Altitude must be positive.")
                if alt != starting_alt:
                    self.drone_ref.gui_ref.missionState.set_drone_operatingAltitude(self.drone_id, alt)
            except ValueError as e:
                print(f"Invalid altitude value: {e}")
                return

        if model and model != starting_model:
            self.drone_ref.gui_ref.missionState.set_drone_vision_model(self.drone_id, model + ".pt")

        self.close()
