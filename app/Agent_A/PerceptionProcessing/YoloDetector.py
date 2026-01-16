import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ultralytics import YOLO
from ultralytics.engine.results import Results
import logging

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
