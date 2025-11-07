import os
from roboflow import Roboflow

# Initialize Roboflow with your API key
rf = Roboflow(api_key="FZ8nMp8jPXuF4Tf2qnEN")

# Access the specific project and version
project = rf.workspace("vitals-s7v4a").project("afo-ft1xo-ligmt")
version = project.version(1)

# Download the dataset into the base directory
dataset = version.download("yolov11")

print(f"Dataset downloaded successfully to {dataset.location}")

             