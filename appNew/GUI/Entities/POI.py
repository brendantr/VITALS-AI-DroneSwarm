import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QFrame
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class POI:
    def __init__(self, lat, lon, name, description, map_widget, info_container, poi_count, gui_ref):
        self.map_widget = map_widget
        self.gui_ref = gui_ref
        self.info_container = info_container
        self.poi_target_at_location = False
        self.id = poi_count
        self.lat = lat
        self.lon = lon
        self.name = f"poi {poi_count}"
        self.positive_flags = 0
        self.description = description

        # Add marker on map
        self.marker_id = map_widget.add_marker(lat, lon, self.name, icon="poi")
        map_widget.marker_clicked.connect(self._on_marker_click)

        # Add info box to sidebar
        self.info_widget = POIInfoBox(info_container, self.name, lat, lon, poi_count, self.open_popup)

    def _on_marker_click(self, marker_id):
        if marker_id == self.marker_id:
            self.open_popup()

    def target_found(self, drone_id):
        self.poi_target_at_location = True
        self.map_widget.set_marker_tooltip(self.marker_id, f"{self.name} (Target Found)")

        # Non-modal dialog so user can still interact with the map (e.g. click POIs)
        self._target_dialog = TargetFoundDialog(self.name, self.gui_ref)
        self._target_dialog.accepted.connect(
            lambda: self.gui_ref.missionState.end_mission()
        )
        self._target_dialog.rejected.connect(
            lambda: self.gui_ref.missionState.remove_poi_investigate_job(self.id)
        )
        self._target_dialog.show()

    def open_popup(self):
        dialog = POIDetailDialog(self, self.gui_ref)
        dialog.exec()


class TargetFoundDialog(QDialog):
    def __init__(self, poi_name, gui_ref, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{poi_name} - Target Found")
        self.setFixedSize(400, 200)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        label = QLabel(f"Target found at {poi_name}!\nDo you want to end the mission or continue the search?")
        label.setStyleSheet("font-size: 14px;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        layout.addWidget(label)

        layout.addSpacing(20)

        btn_layout = QHBoxLayout()

        end_btn = QPushButton("End Mission")
        end_btn.setProperty("cssClass", "danger")
        end_btn.clicked.connect(self.accept)
        btn_layout.addWidget(end_btn)

        continue_btn = QPushButton("Continue Search")
        continue_btn.setProperty("cssClass", "primary")
        continue_btn.clicked.connect(self.reject)
        btn_layout.addWidget(continue_btn)

        layout.addLayout(btn_layout)


class POIDetailDialog(QDialog):
    def __init__(self, poi, gui_ref, parent=None):
        super().__init__(parent)
        self.setWindowTitle(poi.name)
        self.setFixedSize(340, 520)

        layout = QVBoxLayout(self)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(8)

        # Name
        name_label = QLabel(f"Name: {poi.name}")
        name_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        content_layout.addWidget(name_label)

        # Coordinates
        coords_label = QLabel(f"Coordinates: ({poi.lat:.4f}, {poi.lon:.4f})")
        coords_label.setStyleSheet("font-size: 12px; color: #aaa;")
        content_layout.addWidget(coords_label)

        # Description
        desc_text = poi.description if poi.description else "No description available."
        desc_label = QLabel(f"Description: {desc_text}")
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("font-size: 12px;")
        content_layout.addWidget(desc_label)

        # Images
        mission_id = gui_ref.missionState.get_missionID()
        image_folder = f"./Missions/{mission_id}/POIs/{poi.id}/"

        if os.path.exists(image_folder):
            for filename in os.listdir(image_folder):
                if filename.endswith((".jpg", ".png")):
                    image_path = os.path.join(image_folder, filename)
                    print(f"Image path loading popup: {image_path}")

                    pixmap = QPixmap(image_path).scaled(
                        280, 280,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                    img_label = QLabel()
                    img_label.setPixmap(pixmap)
                    img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    content_layout.addWidget(img_label)
        else:
            no_img = QLabel("No images available.")
            no_img.setStyleSheet("color: #888;")
            content_layout.addWidget(no_img)

        content_layout.addStretch()

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)


class POIInfoBox:
    def __init__(self, parent_widget, name, lat, lon, poi_count, popup_func):
        self.popup_func = popup_func

        self.frame = QFrame(parent_widget)
        self.frame.setProperty("cssClass", "poi-card")
        self.frame.setStyleSheet(
            "QFrame { background-color: #0f3460; border: 1px solid #337ab7; "
            "border-radius: 8px; padding: 8px; }"
        )
        self.frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self.frame.mousePressEvent = lambda e: popup_func()

        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)

        self.name_label = QLabel(f"Name: {name}")
        self.name_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #e0e0e0; border: none; background: transparent;")
        layout.addWidget(self.name_label)

        self.coords_label = QLabel(f"Coordinates: ({lat:.4f}, {lon:.4f})")
        self.coords_label.setStyleSheet("font-size: 10px; color: #aaa; border: none; background: transparent;")
        layout.addWidget(self.coords_label)
