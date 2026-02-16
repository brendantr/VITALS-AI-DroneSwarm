# Agent_A/DataFusion/DataFusion.py

"""
DataFusion orchestrates multi-source perception data and prepares MCP messages.
Handles temporal tracking, confidence aggregation, and geo-correlation.
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime, timezone
import uuid

from PerceptionProcessing.Detection import Detection
from PerceptionProcessing.mcp_schema import MCPDetection, MCPCaption, create_detection_from_yolo


class TrackedDetection:
    """
    Represents a detection tracked across multiple frames/sources.
    Implements temporal smoothing and confidence aggregation.
    """
    
    def __init__(self, detection: Detection, frame_number: int, timestamp: str):
        self.track_id = f"track_{uuid.uuid4().hex[:8]}"
        self.detections: List[Tuple[Detection, int, str]] = [(detection, frame_number, timestamp)]
        self.class_name = detection.class_name
        self.first_seen = timestamp
        self.last_seen = timestamp
        self.frame_count = 1
        
        # Aggregated confidence (exponential moving average)
        self.confidence = detection.confidence
        self.alpha = 0.3  # Smoothing factor for new detections
        
        # Spatial tracking
        self.last_bbox = detection.bbox_pixels
        self.centroid_history: List[Tuple[float, float]] = [self._get_centroid(detection.bbox_pixels)]
        
        # Geo tracking
        self.locations: List[Optional[str]] = [detection.location]
        
    def _get_centroid(self, bbox: Tuple[int, int, int, int]) -> Tuple[float, float]:
        """Calculate bbox centroid"""
        x_min, y_min, x_max, y_max = bbox
        return ((x_min + x_max) / 2, (y_min + y_max) / 2)
    
    def iou(self, bbox1: Tuple[int, int, int, int], bbox2: Tuple[int, int, int, int]) -> float:
        """Calculate Intersection over Union between two bboxes"""
        x1_min, y1_min, x1_max, y1_max = bbox1
        x2_min, y2_min, x2_max, y2_max = bbox2
        
        # Intersection
        inter_x_min = max(x1_min, x2_min)
        inter_y_min = max(y1_min, y2_min)
        inter_x_max = min(x1_max, x2_max)
        inter_y_max = min(y1_max, y2_max)
        
        if inter_x_max < inter_x_min or inter_y_max < inter_y_min:
            return 0.0
        
        inter_area = (inter_x_max - inter_x_min) * (inter_y_max - inter_y_min)
        
        # Union
        area1 = (x1_max - x1_min) * (y1_max - y1_min)
        area2 = (x2_max - x2_min) * (y2_max - y2_min)
        union_area = area1 + area2 - inter_area
        
        return inter_area / union_area if union_area > 0 else 0.0
    
    def update(self, detection: Detection, frame_number: int, timestamp: str) -> bool:
        """
        Update track with new detection if it matches.
        
        Returns:
            True if detection was added to this track
        """
        # Check if same class
        if detection.class_name != self.class_name:
            return False
        
        # Check spatial proximity using IoU
        iou_score = self.iou(self.last_bbox, detection.bbox_pixels)
        
        if iou_score > 0.3:  # IoU threshold for tracking
            # Update with exponential moving average
            self.confidence = (1 - self.alpha) * self.confidence + self.alpha * detection.confidence
            
            # Add to history
            self.detections.append((detection, frame_number, timestamp))
            self.last_seen = timestamp
            self.frame_count += 1
            self.last_bbox = detection.bbox_pixels
            self.centroid_history.append(self._get_centroid(detection.bbox_pixels))
            
            if detection.location:
                self.locations.append(detection.location)
            
            return True
        
        return False
    
    def get_best_detection(self) -> Detection:
        """Return detection with highest confidence"""
        return max(self.detections, key=lambda x: x[0].confidence)[0]
    
    def get_latest_detection(self) -> Detection:
        """Return most recent detection"""
        return self.detections[-1][0]
    
    def is_stable(self, min_frames: int = 3) -> bool:
        """Check if track is stable (seen across multiple frames)"""
        return self.frame_count >= min_frames
    
    def get_average_location(self) -> Optional[str]:
        """Calculate average GPS location if available"""
        valid_locations = [loc for loc in self.locations if loc]
        
        if not valid_locations:
            return None
        
        try:
            lats, lons = [], []
            for loc_str in valid_locations:
                lat_str, lon_str = loc_str.split(',')
                lats.append(float(lat_str.strip()))
                lons.append(float(lon_str.strip()))
            
            avg_lat = sum(lats) / len(lats)
            avg_lon = sum(lons) / len(lons)
            return f"{avg_lat:.6f},{avg_lon:.6f}"
        except:
            return valid_locations[-1]  # Return most recent


class DataFusion:
    """
    Fuses perception data from multiple sources/frames.
    Implements:
    - Temporal tracking across frames
    - Multi-drone correlation
    - Confidence aggregation
    - MCP message generation
    """
    
    def __init__(
        self,
        iou_threshold: float = 0.3,
        min_track_frames: int = 3,
        max_track_age: int = 30  # frames
    ):
        """
        Initialize DataFusion
        
        Args:
            iou_threshold: IoU threshold for tracking association
            min_track_frames: Minimum frames to consider track stable
            max_track_age: Maximum frames before dropping inactive track
        """
        self.iou_threshold = iou_threshold
        self.min_track_frames = min_track_frames
        self.max_track_age = max_track_age
        
        # Tracking state
        self.active_tracks: List[TrackedDetection] = []
        self.completed_tracks: List[TrackedDetection] = []
        self.frame_number = 0
        
        # Per-drone tracking (for multi-drone scenarios)
        self.drone_tracks: Dict[int, List[TrackedDetection]] = defaultdict(list)
        
        print("✓ DataFusion initialized")
    
    def _get_timestamp(self) -> str:
        """Generate ISO timestamp"""
        return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    
    def process_detections(
        self,
        detections: List[Detection],
        drone_id: Optional[int] = None
    ) -> List[TrackedDetection]:
        """
        Process new detections and update tracks.
        
        Args:
            detections: List of Detection objects from perception
            drone_id: Optional drone ID for multi-drone tracking
        
        Returns:
            List of updated/new tracks
        """
        self.frame_number += 1
        timestamp = self._get_timestamp()
        
        updated_tracks = []
        unmatched_detections = []
        
        # Try to match detections to existing tracks
        for detection in detections:
            matched = False
            
            for track in self.active_tracks:
                if track.update(detection, self.frame_number, timestamp):
                    updated_tracks.append(track)
                    matched = True
                    break
            
            if not matched:
                unmatched_detections.append(detection)
        
        # Create new tracks for unmatched detections
        for detection in unmatched_detections:
            new_track = TrackedDetection(detection, self.frame_number, timestamp)
            self.active_tracks.append(new_track)
            updated_tracks.append(new_track)
            
            if drone_id is not None:
                self.drone_tracks[drone_id].append(new_track)
        
        # Age out old tracks
        self._prune_tracks()
        
        return updated_tracks
    
    def _prune_tracks(self):
        """Remove tracks that haven't been updated recently"""
        active = []
        
        for track in self.active_tracks:
            age = self.frame_number - track.detections[-1][1]  # frames since last update
            
            if age <= self.max_track_age:
                active.append(track)
            else:
                # Move to completed if it was stable
                if track.is_stable(self.min_track_frames):
                    self.completed_tracks.append(track)
        
        self.active_tracks = active
    
    def get_stable_tracks(self) -> List[TrackedDetection]:
        """Return only tracks that are stable (seen across multiple frames)"""
        return [track for track in self.active_tracks if track.is_stable(self.min_track_frames)]
    
    def get_high_confidence_tracks(self, threshold: float = 0.7) -> List[TrackedDetection]:
        """Return tracks with aggregated confidence above threshold"""
        return [track for track in self.active_tracks if track.confidence >= threshold]
    
    def create_mcp_messages(
        self,
        tracks: Optional[List[TrackedDetection]] = None,
        uav_id: str = "UAV_1",
        sector: Optional[str] = None,
        correlation_id: Optional[str] = None,
        include_captions: bool = True
    ) -> List[Dict]:
        """
        Convert tracked detections to MCP messages.
        
        Args:
            tracks: Tracks to convert (defaults to stable tracks)
            uav_id: UAV identifier
            sector: Search sector
            correlation_id: Mission correlation ID
            include_captions: Whether to include caption messages
        
        Returns:
            List of MCP message dictionaries
        """
        if tracks is None:
            tracks = self.get_stable_tracks()
        
        mcp_messages = []
        
        for track in tracks:
            # Get best detection for this track
            detection = track.get_best_detection()
            
            # Use averaged location if available
            avg_location = track.get_average_location()
            if avg_location:
                detection.location = avg_location
            
            # Create detection message
            mcp_det = create_detection_from_yolo(
                detection=detection,
                frame_number=self.frame_number,
                uav_id=uav_id,
                sector=sector,
                correlation_id=correlation_id
            )
            
            # Override with track info
            mcp_det.track_id = track.track_id
            mcp_det.confidence = track.confidence  # Use aggregated confidence
            
            # Add priority based on class and confidence
            if detection.class_name == "person":
                mcp_det.priority = min(100, int(80 + track.confidence * 20))
            else:
                mcp_det.priority = int(50 + track.confidence * 30)
            
            # Add tags
            tags = []
            if track.is_stable(5):
                tags.append("stable_track")
            if track.confidence > 0.9:
                tags.append("high_confidence")
            if detection.class_name == "person":
                tags.append("person_detected")
            mcp_det.tags = tags
            
            mcp_messages.append(mcp_det.to_dict())
            
            # Add caption if available
            if include_captions and detection.caption:
                caption_msg = MCPCaption(
                    caption=detection.caption,
                    confidence=track.confidence,
                    sector=sector,
                    uav_id=uav_id,
                    correlation_id=correlation_id
                )
                mcp_messages.append(caption_msg.to_dict())
        
        return mcp_messages
    
    def get_statistics(self) -> Dict:
        """Return fusion statistics"""
        stable_tracks = self.get_stable_tracks()
        high_conf = self.get_high_confidence_tracks()
        
        return {
            'frame_number': self.frame_number,
            'active_tracks': len(self.active_tracks),
            'stable_tracks': len(stable_tracks),
            'high_confidence_tracks': len(high_conf),
            'completed_tracks': len(self.completed_tracks),
            'total_tracks_created': len(self.active_tracks) + len(self.completed_tracks)
        }
    
    def reset(self):
        """Reset all tracking state"""
        self.active_tracks = []
        self.completed_tracks = []
        self.drone_tracks.clear()
        self.frame_number = 0
        print("DataFusion state reset")