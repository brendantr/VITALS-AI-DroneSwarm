import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class HomePage(QWidget):
    def __init__(self, gui_ref, **kwargs):
        super().__init__(**kwargs)
        self.gui_ref = gui_ref

        # Main layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Lockheed Martin Logo
        lm_logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "lockheed_martin_logo.png")
        if os.path.exists(lm_logo_path):
            lm_label = QLabel()
            lm_pixmap = QPixmap(lm_logo_path).scaled(
                400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            lm_label.setPixmap(lm_pixmap)
            lm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(lm_label)

        # VITALS Logo (replaces welcome text)
        vitals_logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "VITALS_LOGO.png")
        if os.path.exists(vitals_logo_path):
            vitals_label = QLabel()
            vitals_pixmap = QPixmap(vitals_logo_path).scaled(
                200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            vitals_label.setPixmap(vitals_pixmap)
            vitals_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(vitals_label)
        layout.addSpacing(30)

        # Mission type selection
        mission_type_label = QLabel("Select Mission Type")
        mission_type_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #e0e0e0;")
        mission_type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(mission_type_label)
        layout.addSpacing(15)

        self.simulation_button = QPushButton("Simulation")
        self.simulation_button.setProperty("cssClass", "primary")
        self.simulation_button.setMinimumWidth(250)
        self.simulation_button.setMinimumHeight(44)
        self.simulation_button.clicked.connect(self.start_simulation)
        layout.addWidget(self.simulation_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.real_mission_button = QPushButton("Real Mission")
        self.real_mission_button.setProperty("cssClass", "primary")
        self.real_mission_button.setMinimumWidth(250)
        self.real_mission_button.setMinimumHeight(44)
        self.real_mission_button.clicked.connect(self.start_real_mission)
        layout.addWidget(self.real_mission_button, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(10)

        info_label = QLabel(
            "*Simulation mode allows for the placement of predefined targets\n"
            "to replace the detection of objects from onboard drone CV."
        )
        info_label.setStyleSheet("font-size: 11px; color: #888888;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

    def start_simulation(self):
        """Start a simulation mission."""
        self.gui_ref.isSimulation = True
        self.gui_ref.show_map_page()

    def start_real_mission(self):
        """Start a real mission."""
        self.gui_ref.isSimulation = False
        self.gui_ref.show_map_page()
