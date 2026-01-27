import os
import PIL.Image
import customtkinter


class POI:
    def __init__(self, lat, lon, name, description, map_widget, info_container, poi_count, gui_ref):
        self.map_widget = map_widget
        self.gui_ref = gui_ref
        self.info_container = info_container
        self.poi_target_at_location = False  # Flag to check if this POI is being targeted by a drone
        self.id = poi_count
        self.lat = lat
        self.lon = lon
        self.name = f"poi {poi_count}"
        self.positive_flags = 0
        self.description = description
        self.marker = map_widget.set_marker(lat, lon, text=self.name, command=self.open_popup)
        self.info_widget = POIInfoBox(info_container, self.name, lat, lon, poi_count, popup_func=self.open_popup)

    def target_found(self, drone_id):
        self.poi_target_at_location = True
        self.marker.set_text(f"{self.name} (Target Found)")
        #create popup to ask if the user wants to end the mission or continue investigating
        self.target_found_popup = customtkinter.CTkToplevel(self.info_container)
        self.target_found_popup.title(f"{self.name} - Target Found")
        self.target_found_popup.geometry("400x300")
        self.target_found_popup.resizable(False, False)
        self.target_found_popup.attributes("-topmost", True)  # Keep it on top
        label = customtkinter.CTkLabel(self.target_found_popup, text=f"Target found at {self.name}!\nDo you want to end the mission or continue the search?", font=("Arial", 14))
        label.pack(pady=20)
        end_button = customtkinter.CTkButton(self.target_found_popup, text="End Mission", command=self.end_mission)
        end_button.pack(pady=10)
        continue_button = customtkinter.CTkButton(self.target_found_popup, text="Continue Search", command=self.continue_investigating)
        continue_button.pack(pady=10)

    def end_mission(self):
        if hasattr(self, 'target_found_popup'):
            self.target_found_popup.destroy()
            self.target_found_popup = None
        self.gui_ref.missionState.end_mission()

    def continue_investigating(self):
        if hasattr(self, 'target_found_popup'):
            self.target_found_popup.destroy()
            self.target_found_popup = None
        # remove investigation job if it exists
        self.gui_ref.missionState.remove_poi_investigate_job(self.id)

    def open_popup(self, event):
        # Create a new window
        self.popup = customtkinter.CTkToplevel(self.info_container)
        self.popup.title(self.name)
        self.popup.geometry("320x500")  # Increased width slightly for better layout

        # Push the popup to the front
        self.popup.lift()
        self.popup.focus_force()
        self.popup.grab_set()
        self.popup.protocol("WM_DELETE_WINDOW", self.popup.destroy)

        # Create a scrollable frame
        scrollable_frame = customtkinter.CTkScrollableFrame(self.popup, width=300, height=450)  # Limit height to trigger scrolling
        scrollable_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # Add content to the scrollable frame
        name_label = customtkinter.CTkLabel(scrollable_frame, text=f"Name: {self.name}", font=("Arial", 12))
        name_label.pack(pady=10)

        coordinates_label = customtkinter.CTkLabel(scrollable_frame, text=f"Coordinates: ({self.lat:.4f}, {self.lon:.4f})", font=("Arial", 12))
        coordinates_label.pack(pady=10)

        if self.description:
            description_label = customtkinter.CTkLabel(scrollable_frame, text=f"Description: {self.description}", wraplength=280, font=("Arial", 12))
            description_label.pack(pady=10)
        else:
            description_label = customtkinter.CTkLabel(scrollable_frame, text="Description: No description available.", font=("Arial", 12))
            description_label.pack(pady=10)

        # Load all images in the POI folder
        mission_id = self.gui_ref.missionState.get_missionID()
        image_folder = f"./Missions/{mission_id}/POIs/{self.id}/"

        if os.path.exists(image_folder):
            for filename in os.listdir(image_folder):
                if filename.endswith(".jpg") or filename.endswith(".png"):
                    image_path = os.path.join(image_folder, filename)
                    print(f"Image path loading popup: {image_path}")

                    image = PIL.Image.open(image_path)
                    image = image.resize((280, 280))  # Resize to fit scrollable frame
                    photo = customtkinter.CTkImage(image, size=(280, 280))

                    image_label = customtkinter.CTkLabel(scrollable_frame, image=photo, text="", width=280, height=280)
                    image_label.pack(pady=10)
        else:
            no_image_label = customtkinter.CTkLabel(scrollable_frame, text="No images available.", font=("Arial", 12))
            no_image_label.pack(pady=10)

        # Add a separator
        separator = customtkinter.CTkLabel(scrollable_frame, text="", height=2)
        separator.pack(fill="x", pady=10)

        # Add a close button
        close_button = customtkinter.CTkButton(scrollable_frame, text="Close", command=self.popup.destroy)
        close_button.pack(pady=10)


class POIInfoBox(customtkinter.CTkFrame):
    def __init__(self, parent, name, lat, lon, poi_count, popup_func):
        # Create the POI info frame
        self.poi_info = customtkinter.CTkFrame(parent, fg_color="#337ab7")  # Blue background
        self.poi_info.grid(row=poi_count, column=0, padx=10, pady=10, sticky="ew")
        self.poi_info.bind("<Button-1>", popup_func)

        # Add the POI name
        self.name_label = customtkinter.CTkLabel(self.poi_info, text=f"Name: {name}", font=("Arial", 12, "bold"), fg_color="#337ab7")
        self.name_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        # Add the coordinates label
        self.coordinates_label = customtkinter.CTkLabel(self.poi_info, text=f"Coordinates: ({lat:.4f}, {lon:.4f})", font=("Arial", 10), fg_color="#337ab7")
        self.coordinates_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=5)
