import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QStackedWidget, QSizePolicy
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

        # Logo
        logo_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "lockheed_martin_logo.png")
        if os.path.exists(logo_path):
            logo_label = QLabel()
            pixmap = QPixmap(logo_path).scaled(
                200, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)
            layout.addSpacing(10)

        # Welcome label
        self.title_label = QLabel("Welcome to VITALS!")
        self.title_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #e0e0e0;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)
        layout.addSpacing(30)

        # Stacked widget for initial menu vs mission type selection
        self.page_stack = QStackedWidget()
        self.page_stack.setMaximumWidth(400)
        self.page_stack.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.page_stack, alignment=Qt.AlignmentFlag.AlignCenter)

        # ── Page 0: Initial menu ──────────────────────────
        initial_menu = QWidget()
        initial_layout = QVBoxLayout(initial_menu)
        initial_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.start_mission_button = QPushButton("Start Mission")
        self.start_mission_button.setProperty("cssClass", "primary")
        self.start_mission_button.setMinimumWidth(250)
        self.start_mission_button.setMinimumHeight(44)
        self.start_mission_button.clicked.connect(self.show_mission_type_selection)
        initial_layout.addWidget(self.start_mission_button)

        self.mission_review_button = QPushButton("Mission Review")
        self.mission_review_button.setMinimumWidth(250)
        self.mission_review_button.setMinimumHeight(44)
        initial_layout.addWidget(self.mission_review_button)

        self.page_stack.addWidget(initial_menu)  # index 0

        # ── Page 1: Mission type selection ────────────────
        mission_type_page = QWidget()
        mission_type_layout = QVBoxLayout(mission_type_page)
        mission_type_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        mission_type_label = QLabel("Select Mission Type")
        mission_type_label.setStyleSheet("font-size: 18px; font-weight: 600; color: #e0e0e0;")
        mission_type_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mission_type_layout.addWidget(mission_type_label)
        mission_type_layout.addSpacing(15)

        self.simulation_button = QPushButton("Simulation")
        self.simulation_button.setProperty("cssClass", "primary")
        self.simulation_button.setMinimumWidth(250)
        self.simulation_button.setMinimumHeight(44)
        self.simulation_button.clicked.connect(self.start_simulation)
        mission_type_layout.addWidget(self.simulation_button)

        self.real_mission_button = QPushButton("Real Mission")
        self.real_mission_button.setProperty("cssClass", "primary")
        self.real_mission_button.setMinimumWidth(250)
        self.real_mission_button.setMinimumHeight(44)
        self.real_mission_button.clicked.connect(self.start_real_mission)
        mission_type_layout.addWidget(self.real_mission_button)

        mission_type_layout.addSpacing(10)

        info_label = QLabel(
            "*Simulation mode allows for the placement of predefined targets\n"
            "to replace the detection of objects from onboard drone CV."
        )
        info_label.setStyleSheet("font-size: 11px; color: #888888;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setWordWrap(True)
        mission_type_layout.addWidget(info_label)

        mission_type_layout.addSpacing(15)

        back_button = QPushButton("Back")
        back_button.setMaximumWidth(120)
        back_button.clicked.connect(self.show_initial_menu)
        mission_type_layout.addWidget(back_button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.page_stack.addWidget(mission_type_page)  # index 1

        # Show initial menu by default
        self.page_stack.setCurrentIndex(0)

    def show_mission_type_selection(self):
        """Hide initial menu and show mission type selection."""
        self.page_stack.setCurrentIndex(1)

    def show_initial_menu(self):
        """Hide mission type selection and show initial menu."""
        self.page_stack.setCurrentIndex(0)

    def start_simulation(self):
        """Start a simulation mission."""
        self.gui_ref.isSimulation = True
        self.gui_ref.show_map_page()

    def start_real_mission(self):
        """Start a real mission."""
        self.gui_ref.isSimulation = False
        self.gui_ref.show_map_page()
