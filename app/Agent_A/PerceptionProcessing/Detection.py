# Detection.py

import numpy as np
from typing import Tuple, Dict, Optional

class Detection:
    def __init__(
        self,
        class_id: int,
        class_name: str,
        confidence: float,
        bbox_normalized: Tuple[float, float, float, float],  # (x_min, y_min, x_max, y_max) in [0,1]
        bbox_pixels: Tuple[int, int, int, int],  # (x_min, y_min, x_max, y_max) in pixels
        # Agent A enrichment fields (added later in pipeline)
        drone_id: Optional[int] = None,
        location: Optional[str] = None,
        caption: Optional[str] = None
    ):
        # YOLO core fields
        self.class_id = class_id
        self.class_name = class_name
        self.confidence = confidence
        self.bbox_normalized = bbox_normalized
        self.bbox_pixels = bbox_pixels
        
        # Agent A enrichment fields (optional)
        self.drone_id = drone_id
        self.location = location
        self.caption = caption
    
    def __repr__(self):
        return f"Detection(class={self.class_name}, conf={self.confidence:.3f}, bbox_pixels={self.bbox_pixels})"
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for MCP encoding"""
        return {
            'class_id': self.class_id,
            'class_name': self.class_name,
            'confidence': self.confidence,
            'bbox_normalized': {
                'x_min': self.bbox_normalized[0],
                'y_min': self.bbox_normalized[1],
                'x_max': self.bbox_normalized[2],
                'y_max': self.bbox_normalized[3]
            },
            'bbox_pixels': {
                'x_min': self.bbox_pixels[0],
                'y_min': self.bbox_pixels[1],
                'x_max': self.bbox_pixels[2],
                'y_max': self.bbox_pixels[3]
            },
            # Optional enrichment fields
            'drone_id': self.drone_id,
            'location': self.location,
            'caption': self.caption
        }
    
    def enrich(
        self,
        drone_id: Optional[int] = None,
        location: Optional[str] = None,
        caption: Optional[str] = None
    ):
        """Add contextual information after initial detection"""
        if drone_id is not None:
            self.drone_id = drone_id
        if location is not None:
            self.location = location
        if caption is not None:
            self.caption = caption