import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ultralytics import YOLO
from ultralytics.engine.results import Results
import logging
from Detection import Detection

logger = logging.getLogger(__name__)

class YOLODetector:
    
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
            results: Results,
            img_height: int, 
            img_width: int,
    ) -> (List[Detection]):
        """
        Parse results object and return the detections
        
        Args:
            results: 
                Ultralytics results object
            img_height: 
            img_width:
        
        Returns:
            List of detections
        """
        detections = []

        for res in results:

        return detections
    
    def annotated_frames(
            self,
            frame: np.ndarray,
            detections: List[Detection]
    ) -> (np.ndarray):

        for detection in detections:
            x_min, y_min, x_max, y_max = detection.bbox_pixels
            cv2.rectangle(frame, (x_min, y_min), (x_max, y_max), color='blue', thickness=2)

        return frame