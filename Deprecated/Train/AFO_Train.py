from ultralytics import YOLO

# Define the path to the dataset and configuration
dataset_path = "AFO-1/data.yaml"  # Relative path to the dataset configuration file
model_path = "yolo11l.pt"  # Path to your YOLOv11 model file (adjust based on the model you want to use)

# Load the YOLOv11 model
model = YOLO(model_path)

# Train the model
train_results = model.train(
    data=dataset_path,  # Path to the dataset YAML file
    epochs=100,  # Number of training epochs
    imgsz=640,  # Image size for training
    device="cpu",  # Device to use for training
    project="runs/train",  # Base folder to save training results
    name="AFO_train"  # Subfolder name for this training session
)

# Print completion message
print("Training completed successfully!")
