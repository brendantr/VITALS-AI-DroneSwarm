# PerceptionProcessing/mcp_schema.py
"""
MCP v0.1 Schema - Official VITALS Protocol Compliant

Based on schemas/mcp.v0.1/base.json and schemas/mcp.v0.1/types/detection.json
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


class MCPDetection:
    """
    MCP.Detection message - compliant with official MCP v0.1 schema.
    
    Schema location: schemas/mcp.v0.1/types/detection.json
    
    Required fields (enforced by schema):
    - Base: schema, event_id, ts, type, source, payload
    - Payload: label, confidence
    
    This class generates messages that pass Agent B's SchemaValidator.
    """
    
    def __init__(self,
                 # Required detection fields (payload.label, payload.confidence)
                 label: str,                    # e.g., "person", "vehicle", "debris"
                 confidence: float,             # 0.0 to 1.0
                 
                 # Required source identification
                 component: str = "AgentA",     # Which agent sent this
                 instance: Optional[str] = None, # Specific UAV/camera ID
                 
                 # Optional bounding box (schema uses bbox_xyxy format)
                 bbox_xyxy: Optional[List[float]] = None,  # [x1, y1, x2, y2] in pixels
                 
                 # Optional detection metadata
                 track_id: Optional[str] = None,
                 sensor: str = "rgb",           # "rgb", "thermal", etc.
                 sector: Optional[str] = None,  # e.g., "B4"
                 uav_id: Optional[str] = None,  # e.g., "UAV_2"
                 frame_ts: Optional[str] = None,
                 
                 # Optional geo location
                 latitude: Optional[float] = None,
                 longitude: Optional[float] = None,
                 altitude_m: Optional[float] = None,
                 
                 # Optional metadata
                 correlation_id: Optional[str] = None,
                 priority: int = 50,            # 0-100, default 50
                 tags: Optional[List[str]] = None,
                 text: Optional[str] = None):    # Custom text for embeddings
        
        # Payload - required fields
        self.label = label
        self.confidence = confidence
        
        # Payload - optional fields
        self.bbox_xyxy = bbox_xyxy
        self.track_id = track_id
        self.sensor = sensor
        self.sector = sector
        self.uav_id = uav_id
        self.frame_ts = frame_ts or self._iso_now()
        
        # Source - required
        self.component = component
        self.instance = instance or uav_id  # Use uav_id as instance if not specified
        
        # Geo - optional
        self.latitude = latitude
        self.longitude = longitude
        self.altitude_m = altitude_m
        
        # Envelope metadata
        self.correlation_id = correlation_id
        self.priority = max(0, min(100, priority))  # Clamp to 0-100
        self.tags = tags or []
        self.custom_text = text
        
        # Auto-generated fields (required by base schema)
        self.event_id = f"evt_{uuid.uuid4().hex[:12]}"
        self.timestamp = self._iso_now()
    
    @staticmethod
    def _iso_now() -> str:
        """Generate ISO 8601 timestamp (required format for ts, frame_ts)"""
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to MCP v0.1 message format.
        
        Validates against: schemas/mcp.v0.1/message.json
        """
        # Build payload (detection.json schema)
        payload: Dict[str, Any] = {
            "label": self.label,
            "confidence": self.confidence
        }
        
        # Add optional payload fields (only if present)
        if self.bbox_xyxy is not None:
            payload["bbox_xyxy"] = self.bbox_xyxy
        if self.track_id is not None:
            payload["track_id"] = self.track_id
        if self.sensor != "rgb":  # Only include if non-default
            payload["sensor"] = self.sensor
        if self.sector is not None:
            payload["sector"] = self.sector
        if self.uav_id is not None:
            payload["uav_id"] = self.uav_id
        if self.frame_ts is not None:
            payload["frame_ts"] = self.frame_ts
        
        # Build source (base.json schema - required)
        source: Dict[str, Any] = {
            "system": "VITALS",
            "component": self.component
        }
        if self.instance is not None:
            source["instance"] = self.instance
        
        # Build base message (all required fields)
        message: Dict[str, Any] = {
            "schema": "mcp.v0.1",
            "event_id": self.event_id,
            "ts": self.timestamp,
            "type": "MCP.Detection",
            "source": source,
            "payload": payload
        }
        
        # Add optional base fields
        if self.correlation_id is not None:
            message["corr_id"] = self.correlation_id
        
        if self.priority != 50:  # Only include if non-default
            message["priority"] = self.priority
        
        # Add geo if we have coordinates
        if self.latitude is not None and self.longitude is not None:
            geo: Dict[str, Any] = {
                "lat": self.latitude,
                "lon": self.longitude
            }
            if self.altitude_m is not None:
                geo["alt_m"] = self.altitude_m
            message["geo"] = geo
        
        # Add tags if present
        if self.tags:
            message["tags"] = self.tags
        
        # Add text field (recommended for Agent B embeddings)
        if self.custom_text is not None:
            message["text"] = self.custom_text
        else:
            message["text"] = self._generate_text()
        
        return message
    
    def _generate_text(self) -> str:
        """
        Generate embedding-friendly text summary.
        Agent B uses this for semantic search.
        """
        parts = [f"{self.label.capitalize()} detected"]
        
        if self.sector:
            parts.append(f"in sector {self.sector}")
        
        parts.append(f"with {self.confidence:.0%} confidence")
        
        if self.uav_id:
            parts.append(f"by {self.uav_id}")
        
        return " ".join(parts) + "."
    
    def __repr__(self):
        return (f"MCPDetection(event_id={self.event_id}, "
                f"label={self.label}, conf={self.confidence:.2f})")


class MCPCaption:
    """
    MCP.Caption message - for LLaVA-generated scene descriptions.
    
    Schema location: schemas/mcp.v0.1/types/caption.json
    """
    
    def __init__(self,
                 caption: str,
                 confidence: Optional[float] = None,
                 sector: Optional[str] = None,
                 uav_id: Optional[str] = None,
                 frame_ts: Optional[str] = None,
                 component: str = "AgentA",
                 instance: Optional[str] = None,
                 correlation_id: Optional[str] = None):
        
        self.caption = caption
        self.confidence = confidence
        self.sector = sector
        self.uav_id = uav_id
        self.frame_ts = frame_ts or self._iso_now()
        
        self.component = component
        self.instance = instance or uav_id
        self.correlation_id = correlation_id
        
        self.event_id = f"evt_{uuid.uuid4().hex[:12]}"
        self.timestamp = self._iso_now()
    
    @staticmethod
    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to MCP.Caption message"""
        payload: Dict[str, Any] = {"caption": self.caption}
        
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.sector is not None:
            payload["sector"] = self.sector
        if self.uav_id is not None:
            payload["uav_id"] = self.uav_id
        if self.frame_ts is not None:
            payload["frame_ts"] = self.frame_ts
        
        source = {
            "system": "VITALS",
            "component": self.component
        }
        if self.instance is not None:
            source["instance"] = self.instance
        
        message = {
            "schema": "mcp.v0.1",
            "event_id": self.event_id,
            "ts": self.timestamp,
            "type": "MCP.Caption",
            "source": source,
            "payload": payload,
            "text": self.caption  # Use caption as the text for embeddings
        }
        
        if self.correlation_id is not None:
            message["corr_id"] = self.correlation_id
        
        return message


def create_detection_from_yolo(detection,
                                frame_number: int,
                                uav_id: str,
                                sector: Optional[str] = None,
                                correlation_id: Optional[str] = None) -> MCPDetection:
    """
    Helper: Convert Detection object from YoloDetector to MCP.Detection
    
    Args:
        detection: Detection object with bbox_pixels, class_name, confidence
        frame_number: Frame index
        uav_id: UAV identifier (e.g., "UAV_2")
        sector: Optional sector (e.g., "B4")
        correlation_id: Optional mission ID
    
    Returns:
        MCPDetection ready to send to Agent B
    """
    # Extract bbox in schema format: [x1, y1, x2, y2]
    x_min, y_min, x_max, y_max = detection.bbox_pixels
    bbox_xyxy = [float(x_min), float(y_min), float(x_max), float(y_max)]
    
    # Parse GPS if available
    latitude = None
    longitude = None
    if detection.location:
        try:
            lat_str, lon_str = detection.location.split(',')
            latitude = float(lat_str.strip())
            longitude = float(lon_str.strip())
        except:
            pass
    
    return MCPDetection(
        label=detection.class_name,
        confidence=detection.confidence,
        bbox_xyxy=bbox_xyxy,
        sector=sector,
        uav_id=uav_id,
        instance=uav_id,
        latitude=latitude,
        longitude=longitude,
        correlation_id=correlation_id
    )


def create_caption_from_llava(caption_text: str,
                               uav_id: str,
                               confidence: Optional[float] = None,
                               sector: Optional[str] = None,
                               correlation_id: Optional[str] = None) -> MCPCaption:
    """
    Helper: Create MCP.Caption from LLaVA output
    
    Args:
        caption_text: LLaVA-generated description
        uav_id: UAV identifier
        confidence: Optional confidence score
        sector: Optional sector
        correlation_id: Optional mission ID
    
    Returns:
        MCPCaption ready to send to Agent B
    """
    return MCPCaption(
        caption=caption_text,
        confidence=confidence,
        sector=sector,
        uav_id=uav_id,
        instance=uav_id,
        correlation_id=correlation_id
    )


# Example usage
if __name__ == "__main__":
    import json
    
    # Test MCP.Detection
    detection = MCPDetection(
        label="person",
        confidence=0.92,
        bbox_xyxy=[100.0, 200.0, 300.0, 500.0],
        sector="B4",
        uav_id="UAV_2",
        latitude=28.6024,
        longitude=-81.2001,
        correlation_id="mission_001",
        tags=["high_priority", "needs_investigation"]
    )
    
    print("MCP.Detection:")
    print(json.dumps(detection.to_dict(), indent=2))
    
    print("\n" + "="*80 + "\n")
    
    # Test MCP.Caption
    caption = MCPCaption(
        caption="Person wearing orange vest waving near debris field",
        confidence=0.95,
        sector="B4",
        uav_id="UAV_2",
        correlation_id="mission_001"
    )
    
    print("MCP.Caption:")
    print(json.dumps(caption.to_dict(), indent=2))