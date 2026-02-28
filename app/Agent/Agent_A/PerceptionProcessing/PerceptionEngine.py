# Agent_A/PerceptionProcessing/PerceptionEngine.py

"""
PerceptionEngine orchestrates YOLO detection + LLaVA captioning.
Handles enrichment with drone metadata (drone_id, location, captions).
"""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple, Optional
try:
    from app.Agent.Agent_A.PerceptionProcessing.YoloDetector import YoloDetector
    from app.Agent.Agent_A.PerceptionProcessing.LLaVACaptioner import LLaVACaptioner
    from app.Agent.Agent_A.PerceptionProcessing.Detection import Detection
except ImportError:
    from PerceptionProcessing.YoloDetector import YoloDetector
    from PerceptionProcessing.LLaVACaptioner import LLaVACaptioner
    from PerceptionProcessing.Detection import Detection


class PerceptionEngine:
    def __init__(
        self,
        yolo_model_path: str,
        yolo_confidence: float = 0.5,
        yolo_iou: float = 0.45,
        caption_threshold: float = 0.7,
        device: str = "cpu"
    ):
        """
        Initialize PerceptionEngine with YOLO + LLaVA
        
        Args:
            yolo_model_path: Path to YOLO .pt model
            yolo_confidence: YOLO detection confidence threshold
            yolo_iou: YOLO IoU threshold for NMS
            caption_threshold: Only caption detections above this confidence
            device: Device to run on ('cuda' or 'cpu')
        """
        print("Initializing Perception Engine...")
        
        # Initialize YOLO detector
        self.yolo_detector = YoloDetector(  # ← FIX 1: Make sure attribute name is 'yolo_detector'
            model_path=yolo_model_path,
            confidence_threshold=yolo_confidence,
            iou_threshold=yolo_iou,
            device=device
        )
        
        # Initialize LLaVA captioner
        self.captioner = LLaVACaptioner(device=device)
        
        self.caption_threshold = caption_threshold
        self.device = device
        
        print("✓ Perception Engine ready")
    
    def process_image_path(
        self,
        image_path: str,
        drone_id: Optional[int] = None,
        location: Optional[str] = None,
        generate_captions: bool = False,
        return_annotated: bool = True
    ) -> Tuple[List[Detection], Optional[np.ndarray]]:
        """
        Process image from file path
        
        Args:
            image_path: Path to image file
            drone_id: Optional drone ID for enrichment
            location: Optional location string (e.g., "28.6024,-81.2001")
            generate_captions: Whether to generate LLaVA captions
            return_annotated: Whether to return annotated image
        
        Returns:
            Tuple of (detections_list, annotated_image)
        """
        print(f"Processing: {Path(image_path).name}")
        print("-" * 80)
        
        # Run YOLO detection
        detections, annotated_img = self.yolo_detector.detect_from_path(
            image_path,
            return_annotated=return_annotated
        )
        
        print(f"Found {len(detections)} detection(s)")
        
        # Enrich with drone metadata
        for det in detections:
            det.enrich(drone_id=drone_id, location=location)
        
        # Generate captions if requested
        if generate_captions:
            detections = self._add_captions(image_path, detections)
        
        return detections, annotated_img
    
    def process_image(  # ← FIX 2: Add this method for numpy array input
        self,
        image: np.ndarray,
        drone_id: Optional[int] = None,
        location: Optional[str] = None,
        generate_captions: bool = False,
        return_annotated: bool = True
    ) -> Tuple[List[Detection], Optional[np.ndarray]]:
        """
        Process image from numpy array (cv2 frame)
        
        Args:
            image: Input image as numpy array (BGR format)
            drone_id: Optional drone ID for enrichment
            location: Optional location string
            generate_captions: Whether to generate LLaVA captions
            return_annotated: Whether to return annotated image
        
        Returns:
            Tuple of (detections_list, annotated_image)
        """
        # Run YOLO detection
        detections, annotated_img = self.yolo_detector.detect(
            image,
            return_annotated=return_annotated
        )
        
        print(f"Found {len(detections)} detection(s)")
        
        # Enrich with drone metadata
        for det in detections:
            det.enrich(drone_id=drone_id, location=location)
        
        # Generate captions if requested
        if generate_captions:
            detections = self._add_captions(image, detections)
        
        return detections, annotated_img
    
    def _add_captions(
        self,
        image,  # Can be path (str) or numpy array
        detections: List[Detection]
    ) -> List[Detection]:
        """
        Add LLaVA captions to detections above confidence threshold
        
        Args:
            image: Image path or numpy array
            detections: List of Detection objects
        
        Returns:
            Updated detections with captions
        """
        # Load image if path provided
        if isinstance(image, str):
            frame = cv2.imread(image)
        else:
            frame = image
        
        for i, det in enumerate(detections, 1):
            # Only caption high-confidence detections
            if det.confidence >= self.caption_threshold:
                print(f"Generating caption for detection {i}/{len(detections)}: {det.class_name}")
                
                try:
                    caption = self.captioner.caption_detection(
                        image=frame,
                        detection_bbox=det.bbox_pixels,
                        class_name=det.class_name,
                        confidence=det.confidence
                    )
                    
                    # Truncate for display
                    display_caption = caption[:80] + "..." if len(caption) > 80 else caption
                    print(f"  Caption: {det.class_name} (conf: {det.confidence:.2f}): {display_caption}")
                    
                    det.enrich(caption=caption)
                    
                except Exception as e:
                    print(f"  ⚠ Caption generation failed: {e}")
                    det.enrich(caption=None)
            else:
                print(f"Skipping caption for {det.class_name} (conf={det.confidence:.2f} < {self.caption_threshold})")
        
        return detections
