import PIL.Image
import customtkinter
from concurrent.futures import ThreadPoolExecutor
from LangGraph import langChainMain
import re


class ChatSidebar(customtkinter.CTkFrame):
    def __init__(self, parent, gui_ref, **kwargs):
        super().__init__(parent, **kwargs)

        # Set a fixed width for the chat sidebar
        self.configure(width=300)

        # Reference to the main GUI
        self.gui_ref = gui_ref

        # Thread Executor for LLM Calls
        self.executor = ThreadPoolExecutor()

        # Grid Configuration (Ensures Resizing Behavior)
        self.grid_columnconfigure(0, weight=1)  # Sidebar width fixed
        self.grid_rowconfigure(1, weight=1)  # Chat area expands
        self.grid_rowconfigure(2, weight=0)  # Input area stays fixed

        # Label for the chat sidebar
        chat_label = customtkinter.CTkLabel(self, text="Chat", font=("Arial", 20))
        chat_label.grid(row=0, column=0, pady=10, padx=10, sticky="n")

        # Scrollable chat area using a Canvas
        self.chat_canvas = customtkinter.CTkCanvas(self, height=400, width=280, bg="#2B2B2B", highlightthickness=0)
        self.chat_canvas.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # Scrollbar for chat messages
        self.scrollbar = customtkinter.CTkScrollbar(self, command=self.chat_canvas.yview)
        self.scrollbar.grid(row=1, column=1, sticky="ns")
        self.chat_canvas.configure(yscrollcommand=self.scrollbar.set)

        # Message frame inside the canvas with a fixed width
        self.message_frame = customtkinter.CTkFrame(self.chat_canvas, width=280)
        self.message_window = self.chat_canvas.create_window((0, 0), window=self.message_frame, anchor="nw", width=280)

        # Configure message_frame grid for two columns
        self.message_frame.grid_columnconfigure(0, weight=1)  # Left column (LLM)
        self.message_frame.grid_columnconfigure(1, weight=1)  # Right column (User)

        # Track the current row
        self.current_row = 0

        # Input frame
        input_frame = customtkinter.CTkFrame(self)
        input_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")
        input_frame.grid_columnconfigure(0, weight=1)

        # Input field
        self.input_field = customtkinter.CTkEntry(input_frame, placeholder_text="Type a message...")
        self.input_field.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Load the send button icon
        send_icon = self._load_icon("./assets/send.png")

        # Send button with an icon
        send_button = customtkinter.CTkButton(
            input_frame,
            image=send_icon,
            text="",
            width=20,
            height=20,
            command=self.send_message
        )
        send_button.image = send_icon
        send_button.grid(row=0, column=1)

        # Bind mousewheel scrolling
        self.chat_canvas.bind("<Configure>", self.on_canvas_configure)

    def _load_icon(self, path):
        """Load and resize an icon."""
        image = PIL.Image.open(path)
        image = image.resize((20, 20))
        return customtkinter.CTkImage(light_image=image, dark_image=image)

    def on_canvas_configure(self, event=None):
        """Update the scroll region when new messages are added."""
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))

    def add_message_bubble(self, text, sender="user"):
        """Create and add a message bubble to the chat."""

        # Container Frame takes full width to align bubbles left or right
        container = customtkinter.CTkFrame(self.message_frame, fg_color="transparent")
        container.grid(row=self.current_row, column=0, sticky="ew", padx=5, pady=2)

        # Ensure container expands fully
        container.grid_columnconfigure(0, weight=1)

        # Bubble Label
        bubble = customtkinter.CTkLabel(
            container,
            text=text,
            justify="left",
            anchor="w",
            corner_radius=15,
            fg_color="#3b82f6" if sender == "user" else "#e5e5e5",
            text_color="white" if sender == "user" else "black",
            padx=10,
            pady=5
        )

        # Alignment logic (Left for LLM, Right for User)
        if sender == "user":
            bubble.pack(anchor="e", padx=(40, 0))  # Right alignment with padding
        else:
            bubble.pack(anchor="w", padx=(0, 40))  # Left alignment with padding

        # Set bubble wraplength dynamically based on current sidebar width
        self.update_idletasks()
        max_bubble_width = self.message_frame.winfo_width() * 0.7  # Max 70% of sidebar
        bubble.configure(wraplength=max_bubble_width)

        # Ensure the bubble keeps its width once set, avoiding later resizing issues
        bubble.update_idletasks()
        bubble_width = bubble.winfo_width()
        bubble.configure(width=bubble_width)

        self.current_row += 1
        self.message_frame.update_idletasks()
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        self.chat_canvas.yview_moveto(1)

    def send_message(self):
        """Handle sending a message and updating the chat."""
        user_message = self.input_field.get().strip()
        self.input_field.delete(0, "end")

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
            # Add user message bubble
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
                self.gui_ref.missionState.create_poi_investigate_job(poi_id, drone_id, priority)
                self.add_message_bubble(f"LLM: Sending drone {drone_id} to investigate POI {poi_id}", sender="llm")

            def call_return_to_launch(drone_id):
                self.gui_ref.missionState.call_drone_home(drone_id)
                self.add_message_bubble(f"LLM: Sending drone {drone_id} to launch.", sender="llm")
            
            def call_land_drone(drone_id):
                self.gui_ref.missionState.land_drone(drone_id)
                self.add_message_bubble(f"LLM: Landing drone {drone_id} immediately.", sender="llm")

            def call_end_mission():
                self.gui_ref.missionState.end_mission()
                self.add_message_bubble(f"LLM: Ending mission, returning all drones to launch.", sender="llm")

            def on_complete(future):
                available_tools = {'create_poi_investigate_job': call_create_poi_investigate_job,
                                   'call_return_to_launch': call_return_to_launch,
                                   'call_land_drone': call_land_drone,
                                   'call_end_mission': call_end_mission
                                   }
                response = future.result()
                # Process the toolcalls
                if response.tool_calls:
                    for tool_call in response.tool_calls:
                        if tool_call.function.name in available_tools:
                            print(f"Calling tool: {tool_call.function.name}")
                            result = available_tools[tool_call.function.name](**tool_call.function.arguments)
                        else:
                            print(f"Tool {tool_call.function.name} not found")

            future = self.executor.submit(langChainMain.call_llm, user_message, polygon_points, drones, pois)
            future.add_done_callback(on_complete)
