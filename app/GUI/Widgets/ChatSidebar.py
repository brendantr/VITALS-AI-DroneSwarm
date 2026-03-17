import os
from concurrent.futures import ThreadPoolExecutor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QPixmap, QIcon
from LangGraph import langChainMain
import re


class ChatSidebar(QWidget):
    def __init__(self, gui_ref, parent=None):
        super().__init__(parent)
        self.gui_ref = gui_ref
        self.executor = ThreadPoolExecutor()
        self.setFixedWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        chat_label = QLabel("Chat")
        chat_label.setStyleSheet("font-size: 18px; font-weight: bold; color: #e0e0e0;")
        chat_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(chat_label)

        # Scrollable chat area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: #1a1a2e; }")

        self.message_container = QWidget()
        self.message_layout = QVBoxLayout(self.message_container)
        self.message_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.message_layout.setContentsMargins(4, 4, 4, 4)
        self.message_layout.setSpacing(6)

        self.scroll_area.setWidget(self.message_container)
        layout.addWidget(self.scroll_area, stretch=1)

        # Input area
        input_frame = QWidget()
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(6)

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.returnPressed.connect(self.send_message)
        input_layout.addWidget(self.input_field, stretch=1)

        send_button = QPushButton()
        send_icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "send.png")
        if os.path.exists(send_icon_path):
            send_button.setIcon(QIcon(send_icon_path))
            send_button.setIconSize(QSize(20, 20))
        else:
            send_button.setText("Send")
        send_button.setFixedSize(36, 36)
        send_button.setProperty("cssClass", "primary")
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(send_button)

        layout.addWidget(input_frame)

    def add_message_bubble(self, text, sender="user"):
        """Create and add a message bubble to the chat."""
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setMaximumWidth(230)
        bubble.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if sender == "user":
            bubble.setProperty("cssClass", "chat-user")
            bubble.setStyleSheet(
                "background-color: #0f3460; color: white; border-radius: 12px; "
                "padding: 8px 12px; font-size: 12px;"
            )
        else:
            bubble.setProperty("cssClass", "chat-system")
            bubble.setStyleSheet(
                "background-color: #2a2a4a; color: #b0b0b0; border-radius: 12px; "
                "padding: 8px 12px; font-size: 12px;"
            )

        # Wrapper for alignment
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)

        if sender == "user":
            wrapper_layout.addStretch()
            wrapper_layout.addWidget(bubble)
        else:
            wrapper_layout.addWidget(bubble)
            wrapper_layout.addStretch()

        self.message_layout.addWidget(wrapper)

        # Auto-scroll to bottom
        QTimer.singleShot(50, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        scrollbar = self.scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_message(self):
        """Handle sending a message and updating the chat."""
        user_message = self.input_field.text().strip()
        self.input_field.clear()

        def parse_quick_command(message):
            normalized = re.sub(r"[^a-z0-9/\s]", " ", message.lower())
            normalized = re.sub(r"\s+", " ", normalized).strip()

            for prefix in ["please ", "can you ", "could you ", "vitals "]:
                if normalized.startswith(prefix):
                    normalized = normalized[len(prefix):].strip()

            drone_match = re.search(r"(?:drone\s*)?(\d+)", normalized)
            target_drone_id = int(drone_match.group(1)) if drone_match else None

            land_keywords = [
                "land",
                "land now",
                "land all",
                "emergency land",
                "land immediately",
                "stop",
                "stop now",
                "abort",
                "abort mission",
                "/land",
            ]
            rtl_keywords = [
                "rtl",
                "rtl now",
                "return",
                "return to launch",
                "go home",
                "home",
                "/rtl",
            ]

            if any(keyword in normalized for keyword in land_keywords):
                return ("land", target_drone_id)
            if any(keyword in normalized for keyword in rtl_keywords):
                return ("rtl", target_drone_id)
            return (None, None)

        if user_message:
            self.add_message_bubble(f"You: {user_message}", sender="user")

            # Check for direct emergency commands
            command, target_drone_id = parse_quick_command(user_message)
            if command in ["land", "rtl"]:
                drones = self.gui_ref.missionState.getDrones()
                if not drones:
                    self.add_message_bubble("No active drones found to command.", sender="llm")
                    return

                if target_drone_id is not None:
                    target_drones = [d for d in drones if int(d.drone_id) == int(target_drone_id)]
                    if not target_drones:
                        self.add_message_bubble(f"Drone {target_drone_id} not found.", sender="llm")
                        return
                else:
                    target_drones = drones

                if command == "land":
                    for drone in target_drones:
                        self.gui_ref.missionState.land_drone(drone.drone_id)
                    if target_drone_id is not None:
                        self.add_message_bubble(f"Emergency: Landing drone {target_drone_id} immediately!", sender="llm")
                    else:
                        self.add_message_bubble("Emergency: Landing all drones immediately!", sender="llm")
                else:
                    for drone in target_drones:
                        self.gui_ref.missionState.call_drone_home(drone.drone_id)
                    if target_drone_id is not None:
                        self.add_message_bubble(f"Returning drone {target_drone_id} to launch.", sender="llm")
                    else:
                        self.add_message_bubble("Returning all drones to launch.", sender="llm")
                return

            # Call the LLM with user input
            polygon_points = self.gui_ref.get_polygon_points()
            drones = self.gui_ref.missionState.getDrones()
            pois = self.gui_ref.missionState.getPOIs()

            def call_create_poi_investigate_job(poi_id, drone_id, priority=5):
                self.gui_ref.missionState.create_poi_investigate_job(int(poi_id), int(drone_id), int(priority))
                self._invoke_bubble(f"LLM: Sending drone {drone_id} to investigate POI {poi_id}", "llm")

            def call_return_to_launch(drone_id):
                self.gui_ref.missionState.call_drone_home(drone_id)
                self._invoke_bubble(f"LLM: Sending drone {drone_id} to launch.", "llm")

            def call_end_mission(**kwargs):
                self.gui_ref.missionState.end_mission()
                self._invoke_bubble("LLM: Ending mission, returning all drones to launch.", "llm")

            def call_start_mission(**kwargs):
                self.gui_ref.call_start_mission()
                self._invoke_bubble("LLM: Starting search mission.", "llm")

            def resume_drone_mission(drone_id, **kwargs):
                self.gui_ref.missionState.resume_drone_mission(int(drone_id))
                self._invoke_bubble(f"LLM: Resuming mission for drone {drone_id}.", "llm")

            def on_complete(future):
                available_tools = {
                    'create_poi_investigate_job': call_create_poi_investigate_job,
                    'call_return_to_launch': call_return_to_launch,
                    'call_end_mission': call_end_mission,
                    'call_start_mission': call_start_mission,
                    'resume_drone_mission': resume_drone_mission
                }
                try:
                    response = future.result()
                except Exception as e:
                    print(f"LLM call failed: {e}")
                    self._invoke_bubble(f"LLM: Error — {e}", "llm")
                    return

                # Display the LLM's text response
                if response.content:
                    self._invoke_bubble(f"LLM: {response.content}", "llm")

                # Execute any tool calls
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        if tool_call.function.name in available_tools:
                            print(f"Calling tool: {tool_call.function.name}")
                            available_tools[tool_call.function.name](**tool_call.function.arguments)
                        else:
                            print(f"Tool {tool_call.function.name} not found")

            future = self.executor.submit(langChainMain.call_llm, user_message, polygon_points, drones, pois)
            future.add_done_callback(on_complete)

    def _invoke_bubble(self, text, sender):
        """Thread-safe: add a chat bubble from any thread."""
        self.gui_ref._invoker.invoke(lambda: self.add_message_bubble(text, sender))
