import numpy as np
from typing import Tuple, Dict

class Detection:
    def __init__(
        self,
        drone_id: int,
        class_type: str,
        location: str,
        confidence: float,
        bbox: Tuple[float, float, float, float],
        caption: str
    ):
        self.drone_id = drone_id
        self.class_type = class_type
        self.location = location
        self.confidence = confidence
        self.bbox = bbox
        self.caption = caption

    def to_dict(self) -> Dict:
        """
        Docstring for to_dict
        
        :param self: detection object
        :return: Dictionary object to assist in MCP encoding
        :rtype: Dict
        """
        return {
            'drone_id': self.drone_id,
            'class_type': self.class_type,
            'location': self.location,
            'confidence': float(self.confidence,),
            'bbox': {
                'x_min': float(self.bbox[0]),
                'y_min': float(self.bbox[1]),
                'x_max': float(self.bbox[2]),
                'y_max': float(self.bbox[3])
            },
            'caption': self.caption
        }