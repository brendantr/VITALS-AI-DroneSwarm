import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ultralytics import YOLO
from ultralytics.engine.results import Results
import logging
from PerceptionProcessing.Detection import Detection

logger = logging.getLogger(__name__)

class YoloDetector:
    
    def __init__(
        self,
        model_path: str,
        confidence_threshold: float = 0.5,
        iou_threshold: float = 0.45,
        max_detections: int = 100,
        device: str = "cuda"
    ):
        """
        Initialize YOLO detector
        
        Args:
            model_path: Path to .pt model file (ie. "ComputerVision/CVModels/rf3v1.pt")
            confidence_threshold: Minimum confidence for detections (0-1)
            iou_threshold: IoU threshold for NMS (0-1)
            max_detections: Maximum detections per image
            device: Device to run inference on ('cuda' or 'cpu')
        """
        try:
            self.model = YOLO(model_path)
            self.model.to(device)
            print(f"Model Loaded successfully on {device}")
        except Exception as e:
            print(f"Error loading model: {e}")
            raise

        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self.device = device

        self.class_names = self.model.names

        print(f"YOLODetector initialized with {len(self.class_names)} classes")
        print(f"Classes: {list(self.class_names.values())}")
        print(f"Confidence threshold: {confidence_threshold}")

    def detect(
        self,
        frame: np.ndarray,
        return_annotated: bool = True
    ) -> Tuple[List[Detection], Optional[np.ndarray]]:
        """
        Run YOLO detection on a single frame
        
        Args:
            frame: Input image as numpy array (BGR format from OpenCV)
            return_annotated: Whether to return annotated image
        
        Returns:
            Tuple of (detections_list, annotated_image)
            If return_annotated=False, annotated_image will be None
        """
        if frame is None or frame.size == 0:
            print("Warning: Empty frame received")
            return [], None
        
        # Get image dimensions
        img_height, img_width = frame.shape[:2]
        
        try:
            # Run inference
            results = self.model(
                frame,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                max_det=self.max_detections,
                verbose=False  # Suppress per-frame logs
            )
            
            # Extract detections from results
            detections = self.parse_results(results[0], img_width, img_height)
            
            # Generate annotated image if requested
            annotated_img = None
            if return_annotated:
                annotated_img = self.annotate_frame(frame.copy(), detections)
            
            print(f"Detected {len(detections)} objects")
            
            return detections, annotated_img
            
        except Exception as e:
            print(f"Error during detection: {e}")
            return [], None
        
    def detect_from_path(
        self,
        image_path: str,
        return_annotated: bool = True
    ) -> Tuple[List[Detection], Optional[np.ndarray]]:
        """
        Run YOLO detection on an image file (matches existing interface)
        
        Args:
            image_path: Path to image file
            return_annotated: Whether to return annotated image
        
        Returns:
            Tuple of (detections_list, annotated_image)
        """
        print(f"Loading image from {image_path}")
        
        # Load image using OpenCV (BGR format)
        frame = cv2.imread(image_path)
        
        if frame is None:
            print(f"Error: Could not load image from {image_path}")
            return [], None
        
        return self.detect(frame, return_annotated)
    
    def parse_results(
        self,
        result: Results,
        img_width: int,
        img_height: int
    ) -> List[Detection]:
        """
        Parse YOLO Results object into Detection instances
        
        Args:
            result: Ultralytics Results object
            img_width: Original image width
            img_height: Original image height
        
        Returns:
            List of Detection objects (without drone_id, location, caption yet)
        """
        detections = []
        
        # Check for detections
        if result.boxes is None or len(result.boxes) == 0:
            return detections
        
        # Extract all data at once
        boxes = result.boxes.xyxy.cpu().numpy()  # (N, 4)
        confidences = result.boxes.conf.cpu().numpy()  # (N,)
        class_ids = result.boxes.cls.cpu().numpy().astype(int)  # (N,)
        
        # Process each detection
        for i in range(len(boxes)):
            x_min, y_min, x_max, y_max = boxes[i]
            confidence = float(confidences[i])
            class_id = int(class_ids[i])
            class_name = self.class_names.get(class_id, f"class_{class_id}")
            
            # Normalize coordinates to [0, 1]
            bbox_normalized = (
                float(x_min / img_width),
                float(y_min / img_height),
                float(x_max / img_width),
                float(y_max / img_height)
            )
            
            # Pixel coordinates
            bbox_pixels = (
                int(x_min),
                int(y_min),
                int(x_max),
                int(y_max)
            )
            
            # Create Detection (without drone_id, location, caption)
            detection = Detection(
                class_id=class_id,
                class_name=class_name,
                confidence=confidence,
                bbox_normalized=bbox_normalized,
                bbox_pixels=bbox_pixels,
                # These will be added later by perception_engine
                drone_id=None,
                location=None,
                caption=None
            )
            
            detections.append(detection)
        
        return detections
    
    def annotate_frame(
        self,
        frame: np.ndarray,
        detections: List[Detection]
    ) -> np.ndarray:
        """
        Draw bounding boxes and labels on frame
        
        Args:
            frame: Input image (will be modified in-place)
            detections: List of Detection objects
        
        Returns:
            Annotated image
        """
        for det in detections:
            x_min, y_min, x_max, y_max = det.bbox_pixels
            
            # Get color for this class (deterministic)
            color = self._get_class_color(det.class_id)
            
            # Draw bounding box
            cv2.rectangle(
                frame,
                (x_min, y_min),
                (x_max, y_max),
                color,  # ← BGR tuple, not string
                thickness=2
            )
            
            # Prepare label text
            label = f"{det.class_name} {det.confidence:.2f}"
            
            # Calculate label size for background
            (label_width, label_height), baseline = cv2.getTextSize(
                label,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                1
            )
            
            # Draw label background (filled rectangle)
            cv2.rectangle(
                frame,
                (x_min, y_min - label_height - baseline - 5),
                (x_min + label_width, y_min),
                color,
                thickness=-1  # -1 = filled
            )
            
            # Draw label text (white on colored background)
            cv2.putText(
                frame,
                label,
                (x_min, y_min - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 255),  # White text
                thickness=1,
                lineType=cv2.LINE_AA
            )
        
        # Add detection count overlay in top-left
        metadata_text = f"Detections: {len(detections)}"
        cv2.putText(
            frame,
            metadata_text,
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),  # Green text
            thickness=2
        )
        
        return frame
    
    def _get_class_color(self, class_id: int) -> Tuple[int, int, int]:
        """
        Generate consistent BGR color for each class
        
        Args:
            class_id: Class ID
        
        Returns:
            BGR color tuple (for OpenCV)
        """
        # Use deterministic random color based on class_id
        # This ensures same class always gets same color
        np.random.seed(class_id)
        color = tuple(np.random.randint(0, 255, 3).tolist())
        return color
    
    def filter_detections(
        self,
        detections: List[Detection],
        min_confidence: Optional[float] = None,
        class_filter: Optional[List[str]] = None
    ) -> List[Detection]:
        """
        Filter detections by confidence and/or class
        
        Args:
            detections: List of Detection objects
            min_confidence: Minimum confidence threshold
            class_filter: List of class names to keep (None = keep all)
        
        Returns:
            Filtered list of detections
        """
        filtered = detections
        
        # Filter by confidence
        if min_confidence is not None:
            filtered = [d for d in filtered if d.confidence >= min_confidence]
        
        # Filter by class
        if class_filter is not None:
            filtered = [d for d in filtered if d.class_name in class_filter]
        
        print(f"Filtered {len(detections)} -> {len(filtered)} detections")
        return filtered