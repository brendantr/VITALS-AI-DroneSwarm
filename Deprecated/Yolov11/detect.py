from ultralytics import YOLO
import json
from pathlib import Path

# Specify the model path (either yolov11Custom.pt or rf3v1.pt)
model_path = "CustomModels/yolov11Custom.pt"  # Change this to the desired model 

# Load the YOLOv11 model
model = YOLO(model_path)

# Extract the model's label mapping
custom_labels = model.names  # This pulls the correct labels from the model

# Debug: Print the actual labels used by your model
print("Loaded Labels:", custom_labels)


# Define subfolder name based on model type
if "11C" in model_path:
    subfolder_name = "yolov11Custom"
elif "rf3" in model_path:
    subfolder_name = "rf3v1"
else:
    subfolder_name = "other_runs"  #no match is found

# Create unique directories for JSON and video files
base_json_dir = Path("runs/") / subfolder_name / "jsonfile"
base_video_dir = Path("runs/") / subfolder_name / "videorun"

# Increment directory names for new runs
json_output_dir = base_json_dir
video_output_dir = base_video_dir
for i in range(1, 100):  
    if not json_output_dir.exists():
        break
    json_output_dir = Path(f"{base_json_dir}{i}")
    video_output_dir = Path(f"{base_video_dir}{i}")

json_output_dir.mkdir(parents=True, exist_ok=True)
video_output_dir.mkdir(parents=True, exist_ok=True)

results_cache = []  # Store results for JSON creation

try:
    print("Starting model prediction...")
    results = model.predict(
        source=0,  # Webcam index
        imgsz=640,
        device="cpu",  # Use 'cuda' if your GPU is supported
        conf=0.4,  # Confidence threshold
        show=True,  # Display results
        save=True,  # Save results
        project=str(video_output_dir),  # Save video in videorun folder
        name="",  # Leave empty to avoid creating additional subfolders
        stream=True,  # Enable streaming for real-time processing
    )

    for i, result in enumerate(results):
        detections = []
        for box in result.boxes:  # Iterate over detected objects in the frame
            bbox_coords = [float(coord) for coord in box.xyxy[0].tolist()]  # Bounding box in [x_min, y_min, x_max, y_max] format
            label_index = int(box.cls)  # Get the detected class index

            # Ensure the correct label is used from the model
            label_name = custom_labels[label_index] if label_index < len(custom_labels) else "Unknown"

            detections.append({
                "label": label_name,  # Correct label from model
                "confidence": float(box.conf),  # Confidence score
                "bbox": bbox_coords  # Bounding box coordinates
            })

        # Only create a JSON file if there are detections
        if detections:
            yolo_output = {
                "frame_id": i,  # Frame index
                "detections": detections  # List of detections
            }

            # Save JSON to a file
            json_path = json_output_dir / f"yolo_output_frame_{i}.json"
            with open(json_path, "w") as f:
                json.dump(yolo_output, f, indent=4)

            print(f"Saved YOLO output to {json_path}")

except KeyboardInterrupt:
    print("Detection stopped by user.")
finally:
    print("Detection process completed.")
