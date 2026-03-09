
import cv2
import numpy as np
from ultralytics import YOLO

# Load your trained YOLO model
  # Replace with your model path
model = YOLO("./ComputerVision/CVModels/rf3v1.pt")


custom_labels = model.names  # This pulls the correct labels from the model

def detect_objects(image_path):

    # Load image
    image = cv2.imread(image_path)
    
    # Run inference
    results = model(image)
    
    detections = []
    
    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])  # Bounding box coordinates
            class_id = int(box.cls[0])  # Class ID
            confidence = float(box.conf[0])  # Confidence score
            
            # Get the label name from the model if it exists 
            label_name = custom_labels[class_id] if class_id < len(custom_labels) else "Unknown"

            detections.append({
                "bbox": (x1, y1, x2, y2),
                "class": label_name,
                "confidence": confidence
            })
    
    return detections

# Example usage
image_path = "temp/drone_testing5.jpg"  # Replace with your image path
# detections = detect_objects(image_path)

# # Print results
# for detection in detections:
#     print(f"Class: {detection['class']}, BBox: {detection['bbox']}, Confidence: {detection['confidence']}")

def detect_and_draw(image_path):
    image = cv2.imread(image_path)
    results = model(image)

    detections = []

    for result in results:
        for box in result.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            class_id = int(box.cls[0])
            confidence = float(box.conf[0])

            label_name = custom_labels[class_id] if class_id < len(custom_labels) else "Unknown"

            # Draw bounding box
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{label_name}: {confidence:.2f}"
            cv2.putText(image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
            detections.append({
                "bbox": (x1, y1, x2, y2),
                "class": label_name,
                "confidence": confidence
            })

    # Show image
    return image, detections

# Call function
#detect_and_draw(image_path)