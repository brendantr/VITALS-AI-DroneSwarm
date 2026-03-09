import os
import customtkinter


class jobInfoContainer(customtkinter.CTkFrame):
    def __init__(self, parent, drone_id):
        # Create the drone info frame
        self.job_frame = customtkinter.CTkFrame(parent)
        self.job_frame.grid(row=0, column=drone_id-1, sticky="nsew", padx=10, pady=10)

        self.job_label = customtkinter.CTkLabel(
            self.job_frame, text=f"Drone {drone_id} Jobs", font=("Arial", 16, "bold")
        )
        self.job_label.pack(pady=5)

        self.job_scrollable_frame = customtkinter.CTkScrollableFrame(self.job_frame, width=200, height=200)
        self.job_scrollable_frame.pack(fill="both", expand=True)


class jobInfoItem(customtkinter.CTkFrame):
    def __init__(self, parent, job, row, drone=None, active=False,):
        self.drone = drone
        self.active = active
        # Create the job info frame
        if active:
            self.job_info = customtkinter.CTkFrame(parent, fg_color="#337ab7")
        else:
            self.job_info = customtkinter.CTkFrame(parent, fg_color="#5C5C5C")
        self.job_info.grid(row=row, column=0, padx=10, pady=10, sticky="ew")

        self.job_type_label = customtkinter.CTkLabel(self.job_info, text=job.job_type, font=("Arial", 12, "bold"))
        self.job_type_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.job_status_label = customtkinter.CTkLabel(self.job_info, text=job.job_status, font=("Arial", 10, "bold"))
        self.job_status_label.grid(row=1, column=1, sticky="e", padx=5, pady=5)

        self.num_waypoints_label = customtkinter.CTkLabel(self.job_info, text=f"Waypoints: {len(job.waypoints)}", font=("Arial", 10))
        self.num_waypoints_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=5)

        self.last_waypoint_label = customtkinter.CTkLabel(self.job_info, text=f"Last Visited Waypoint: {job.last_waypoint}", font=("Arial", 10))
        self.last_waypoint_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=5)

        self.job_priority_label = customtkinter.CTkLabel(self.job_info, text=f"Priority: {job.job_priority}", font=("Arial", 10))
        self.job_priority_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=5)

        #bind click to call  toggle_show_active_job_path() on the drone object
        self.job_info.bind("<Button-1>", self.call_toggle_if_active)

    def call_toggle_if_active(self, event):
        self.drone.toggle_show_active_job_path()
        self.drone.showing_active_job_path = not self.drone.showing_active_job_path


class DroneInfoBox(customtkinter.CTkFrame):
    def __init__(self, parent, id, drone_ref):
        # Create the drone info frame
        self.drone_ref = drone_ref
        self.parent = parent
        self.id = id
        self.drone_info = customtkinter.CTkFrame(parent, fg_color="#337ab7")  # Blue background
        self.drone_info.grid(row=id, column=0, padx=10, pady=10, sticky="ew")

        # Add the drone ID
        self.id_label = customtkinter.CTkLabel(self.drone_info, text=f"ID: {id}", font=("Arial", 12, "bold"), fg_color="#337ab7")
        self.id_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        # Add the status label
        self.status_label = customtkinter.CTkLabel(self.drone_info, text="Active", font=("Arial", 10, "bold"), fg_color="green", padx=5, pady=2)
        self.status_label.grid(row=0, column=1, sticky="e", padx=5, pady=5)

        # Add the drone details
        self.position_label = customtkinter.CTkLabel(self.drone_info, text="Position: Unknown", font=("Arial", 10), fg_color="#337ab7")
        self.position_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=5)

        self.altitude_label = customtkinter.CTkLabel(self.drone_info, text="Altitude: Unknown", font=("Arial", 10), fg_color="#337ab7")
        self.altitude_label.grid(row=2, column=0, columnspan=2, sticky="w", padx=5)

        self.velocity_label = customtkinter.CTkLabel(self.drone_info, text="Velocity: Unknown", font=("Arial", 10), fg_color="#337ab7",)
        self.velocity_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=5)

        self.heading_label = customtkinter.CTkLabel(self.drone_info, text="Heading: Unknown", font=("Arial", 10), fg_color="#337ab7",)
        self.heading_label.grid(row=4, column=0, columnspan=2, sticky="w", padx=5)

        self.settings_button = customtkinter.CTkButton(self.drone_info, text="Settings", command=self.open_settings)
        self.settings_button.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

    def updatePos(self, position, altitude, velocity, heading):
        self.position_label.configure(text=f"Position: {position[0]:.7f}, {position[1]:.7f}")
        self.altitude_label.configure(text=f"Altitude: {altitude / 1000} m")
        self.velocity_label.configure(text=f"Velocity: {velocity:.2f}")
        self.heading_label.configure(text=f"Heading: {heading}")

    def open_settings(self):
        # Open settings window
        self.settings_window = customtkinter.CTkToplevel(self.parent)
        self.settings_window.title(f"Settings for Drone {self.id}")
        self.settings_window.geometry("300x600")
        self.settings_window.resizable(False, False)
        starting_alt = self.drone_ref.gui_ref.missionState.get_drone_operatingAltitude(self.id)
        starting_model = self.drone_ref.gui_ref.missionState.get_drone_vision_model(self.id)
        available_models = []
        #parse the CVModels Folder
        for filename in os.listdir("./ComputerVision/CVModels/"):
            if filename.endswith(".pt"):
                available_models.append(filename[:-3])
        #force top level
        self.settings_window.attributes("-topmost", True)
        # Add a label
        label = customtkinter.CTkLabel(self.settings_window, text=f"Settings for Drone {self.id}", font=("Arial", 16))
        label.pack(pady=10)
        # Add operating altitude input
        altitude_label = customtkinter.CTkLabel(self.settings_window, text="Operating Altitude (m):")
        altitude_label.pack(pady=5)
        self.altitude_entry = customtkinter.CTkEntry(self.settings_window, placeholder_text=starting_alt)
        self.altitude_entry.pack(pady=5)
        # Add vision model input
        model_label = customtkinter.CTkLabel(self.settings_window, text="Vision Model:")
        model_label.pack(pady=5)
        self.model_entry = customtkinter.CTkOptionMenu(self.settings_window, values=available_models, command=None)
        self.model_entry.set(starting_model[:-3])
        self.model_entry.pack(pady=5)
        self.mount_angle_label = customtkinter.CTkLabel(self.settings_window, text="Camera Mount Angle (degrees):")
        self.mount_angle_label.pack(pady=5)
        self.mount_angle_entry = customtkinter.CTkEntry(self.settings_window, placeholder_text="-5")
        self.mount_angle_entry.pack(pady=5)
        self.vertical_fov_label = customtkinter.CTkLabel(self.settings_window, text="Vertical FOV (degrees):")
        self.vertical_fov_label.pack(pady=5)
        self.vertical_fov_entry = customtkinter.CTkEntry(self.settings_window, placeholder_text="60")
        self.vertical_fov_entry.pack(pady=5)
        self.horizontal_fov_label = customtkinter.CTkLabel(self.settings_window, text="Horizontal FOV (degrees):")
        self.horizontal_fov_label.pack(pady=5)
        self.horizontal_fov_entry = customtkinter.CTkEntry(self.settings_window, placeholder_text="80")
        self.horizontal_fov_entry.pack(pady=5)

        # Add a save button
        save_button = customtkinter.CTkButton(self.settings_window, text="Save", command=lambda: self.save_settings(starting_alt, starting_model, self.altitude_entry.get(), self.model_entry.get()))
        # Save the settings
        save_button.pack(pady=10)

        # Add a close button
        closebutton = customtkinter.CTkButton(self.settings_window, text="Close", command=self.close_settings)
        closebutton.pack(pady=10)

        # Prevent accidental closure
        self.settings_window.protocol("WM_DELETE_WINDOW", self.close_settings)

    def close_settings(self):
        # Close the settings window
        if hasattr(self, 'settings_window'):
            self.settings_window.destroy()
            self.settings_window = None
        else:
            print("Settings window already closed.")

    def save_settings(self, startingAlt, startingModel, alt, model):

        try:
            alt = int(alt)
            if alt < 0:
                raise ValueError("Altitude must be positive.")
            if alt != startingAlt:
                self.drone_ref.gui_ref.missionState.set_drone_operatingAltitude(self.id, alt)
        except ValueError as e:
            print(f"Invalid altitude value: {e}")
            return
        if model != startingModel:
            self.drone_ref.gui_ref.missionState.set_drone_vision_model(self.id, model+".pt")

    def updateStatus(self, status):

        if status == 0:
            self.status_label.configure(text="UnInit", fg_color="gray")
        elif status == 1:
            self.status_label.configure(text="Boot", fg_color="gray")
        elif status == 2:
            self.status_label.configure(text="Calibrating", fg_color="yellow")
        elif status == 3:
            self.status_label.configure(text="Standby", fg_color="orange")
        elif status == 4:
            self.status_label.configure(text="Active", fg_color="green")
        elif status == 5:
            self.status_label.configure(text="Critical", fg_color="red")
        elif status == 6:
            self.status_label.configure(text="Emergency", fg_color="red")
        else:
            self.status_label.configure(text="Unknown", fg_color="gray")
