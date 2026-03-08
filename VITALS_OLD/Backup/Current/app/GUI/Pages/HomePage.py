import customtkinter


class HomePage(customtkinter.CTkFrame):
    def __init__(self, parent, gui_ref, **kwargs):
        super().__init__(parent, **kwargs)

        self.gui_ref = gui_ref

        # Main content frame (to hold both views)
        self.content_frame = customtkinter.CTkFrame(self, fg_color="transparent")
        self.content_frame.pack(expand=True)

        # Welcome label (always visible)
        self.label = customtkinter.CTkLabel(self.content_frame, text="Welcome to VITALS!", font=("Arial", 24))
        self.label.pack(pady=20)

        # Initial menu frame
        self.initial_menu_frame = customtkinter.CTkFrame(self.content_frame, fg_color="transparent")
        self.start_mission_button = customtkinter.CTkButton(
            self.initial_menu_frame, text="Start Mission", command=self.show_mission_type_selection
        )
        self.mission_review_button = customtkinter.CTkButton(
            self.initial_menu_frame, text="Mission Review",
        )
        self.start_mission_button.pack(pady=10)
        self.mission_review_button.pack(pady=10)

        # Mission type selection frame (initially hidden)
        self.mission_type_frame = customtkinter.CTkFrame(self.content_frame, fg_color="transparent")

        self.mission_type_label = customtkinter.CTkLabel(
            self.mission_type_frame, text="Select Mission Type", font=("Arial", 16)
        )
        self.mission_type_label.pack(pady=10)

        self.simulation_button = customtkinter.CTkButton(
            self.mission_type_frame, text="Simulation", command=self.start_simulation
        )
        self.simulation_button.pack(pady=10)

        self.real_mission_button = customtkinter.CTkButton(
            self.mission_type_frame, text="Real Mission", command=self.start_real_mission
        )
        self.real_mission_button.pack(pady=10)

        self.info_label = customtkinter.CTkLabel(
            self.mission_type_frame,
            text="*Simulation mode allows for the placement of predefined targets\n to replace the detection of objects from onboard drone CV.",
            font=("Arial", 10),
            text_color="gray"
        )
        self.info_label.pack(pady=10)

        self.back_button = customtkinter.CTkButton(
            self.mission_type_frame, text="Back", command=self.show_initial_menu, width=80
        )
        self.back_button.pack(pady=20)

        # Show initial menu by default
        self.initial_menu_frame.pack()

    def show_mission_type_selection(self):
        """Hide initial menu and show mission type selection."""
        self.initial_menu_frame.pack_forget()
        self.mission_type_frame.pack()

    def show_initial_menu(self):
        """Hide mission type selection and show initial menu."""
        self.mission_type_frame.pack_forget()
        self.initial_menu_frame.pack()

    def start_simulation(self):
        """Start a simulation mission."""
        self.gui_ref.isSimulation = True
        self.gui_ref.show_map_page()

    def start_real_mission(self):
        """Start a real mission."""
        self.gui_ref.isSimulation = False
        self.gui_ref.show_map_page()
