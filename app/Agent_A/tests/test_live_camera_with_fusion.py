# Agent_A/tests/test_live_camera_with_fusion.py

"""
Agent A - Live Camera Test with Data Fusion Integration

This test extends the basic live camera test with:
1. Temporal tracking across frames (DataFusion)
2. Confidence aggregation
3. Stable detection filtering
4. Enhanced MCP messages with track IDs

Controls:
  SPACE - Process current frame (YOLO + optional LLaVA + Fusion)
  D     - Process with YOLO only (fast detection + Fusion)
  S     - Save current frame and results
  Q     - Quit and save session
  C     - Toggle continuous processing mode
  J     - Toggle live JSON display window
  T     - Toggle track display overlay
  R     - Reset fusion state (clear all tracks)
  
Prerequisites:
  - USB camera connected
  - YOLO model at PerceptionProcessing/yolo_models/rf3v1.pt
  - DataFusion module
"""

import cv2
import json
import time
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Optional
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from PerceptionProcessing.PerceptionEngine import PerceptionEngine
from PerceptionProcessing.mcp_schema import create_detection_from_yolo
from DataFusion.DataFusion import DataFusion


class LiveCameraWithFusion:
    """Live USB camera testing with temporal tracking"""
    
    def __init__(self, 
                 camera_id: int = 0,
                 yolo_model_path: str = None,
                 output_dir: str = "output/agent_a_fusion_test",
                 mission_id: str = None,
                 uav_id: str = "USB_CAM_0",
                 sector: str = "TEST_ZONE"):
        
        self.camera_id = camera_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Mission context
        self.mission_id = mission_id or f"mission_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.uav_id = uav_id
        self.sector = sector
        
        # Set default model path if not provided
        if yolo_model_path is None:
            yolo_model_path = str(Path(__file__).parent.parent / "PerceptionProcessing" / "yolo_models" / "rf3v1.pt")
        
        # Default output relative to the tests/ folder so it stays inside the repo
        if output_dir == "output/agent_a_fusion_test":
            output_dir = str(Path(__file__).parent / "output" / "agent_a_fusion_test")
        
        # Initialize perception engine
        print("="*80)
        print("  AGENT A - LIVE CAMERA WITH DATA FUSION")
        print("="*80)
        print(f"\nMission ID: {self.mission_id}")
        print(f"UAV ID: {self.uav_id}")
        print(f"Sector: {self.sector}")
        print(f"Output: {self.output_dir}")
        
        print("\n[1/2] Initializing perception engine...")
        self.engine = PerceptionEngine(
            yolo_model_path=yolo_model_path,
            yolo_confidence=0.5,
            caption_threshold=0.7,
            device="cpu"  # Change to "cuda" if GPU available
        )
        print("✓ Perception engine ready")
        
        print("\n[2/2] Initializing data fusion...")
        self.fusion = DataFusion(
            iou_threshold=0.3,      # Track association threshold
            min_track_frames=3,     # Require 3 frames for stable track
            max_track_age=30        # Drop tracks after 30 frames
        )
        print("✓ Data fusion ready")
        
        # Statistics
        self.frame_count = 0
        self.processed_count = 0
        self.mcp_messages = []
        self.processing_times = []
        
        # Mode flags
        self.continuous_mode = False
        self.show_json_window = False
        self.show_tracks = True  # NEW: Show track overlays
        
        print("\n✓ System ready!")
    
    def _open_camera(self, camera_id: int):
        """
        Open camera with Windows-safe backend and a live-frame probe.
        Returns a VideoCapture on success, or None on failure.
        Avoids the silent hang caused by cv2.VideoCapture(id) blocking
        indefinitely on Windows when no camera is present.
        """
        import platform
        system = platform.system()

        # Try backends in priority order.
        # CAP_DSHOW bypasses the Windows Media Foundation layer that hangs.
        if system == "Windows":
            backends = [
                (cv2.CAP_DSHOW, "DirectShow"),
                (cv2.CAP_MSMF,  "Media Foundation"),
                (cv2.CAP_ANY,   "Auto"),
            ]
        else:
            backends = [(cv2.CAP_ANY, "Auto")]

        for backend, name in backends:
            print(f"  Trying {name} backend...")
            cap = cv2.VideoCapture(camera_id, backend)

            if not cap.isOpened():
                print(f"    ✗ {name}: device {camera_id} did not open")
                cap.release()
                continue

            # Probe: actually grab a frame to confirm the device is truly live.
            # isOpened() alone returns True even for ghost/dead devices on Windows.
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, _ = cap.read()
            if not ret:
                print(f"    ✗ {name}: opened but returned no frames")
                cap.release()
                continue

            print(f"    ✓ {name}: camera {camera_id} confirmed live")
            return cap

        return None  # All backends failed

    def run(self):
        """Main test loop"""

        # Use the safe backend probe instead of bare VideoCapture()
        print("\nOpening camera...")
        cap = self._open_camera(self.camera_id)

        if cap is None:
            print(f"\n❌ Could not open camera {self.camera_id} on any backend.")
            print("\nTroubleshooting:")
            print("  1. Confirm the camera is physically connected")
            print("  2. Make sure it is not open in another app (Teams, Zoom, OBS…)")
            print("  3. Try a different ID:  python test_live_camera_with_fusion.py --camera 1")
            print("  4. Quick diagnostic:   python -c \"import cv2; print(cv2.VideoCapture(0, cv2.CAP_DSHOW).isOpened())\"")
            return

        # Get camera info
        fps    = cap.get(cv2.CAP_PROP_FPS)
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(f"\n✓ Camera {self.camera_id} opened")
        print(f"  Resolution: {width}x{height}")
        print(f"  FPS: {fps:.1f}")

        self._print_controls()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("⚠ Failed to grab frame — camera disconnected?")
                    break
                
                self.frame_count += 1
                
                # Add overlay info
                display_frame = self._add_overlay(frame.copy())
                
                # Show live feed
                cv2.imshow('Agent A - Live Camera + Fusion (Press H for help)', display_frame)
                
                key = cv2.waitKey(1) & 0xFF
                
                # Handle key presses
                if key == ord('q'):
                    print("\nQuitting...")
                    break
                    
                elif key == ord(' '):  # SPACE - Full processing
                    self._process_frame(frame, generate_captions=True)
                    
                elif key == ord('d'):  # D - Detection only (fast)
                    self._process_frame(frame, generate_captions=False)
                    
                elif key == ord('s'):  # S - Save
                    self._save_frame(frame)
                    
                elif key == ord('c'):  # C - Toggle continuous mode
                    self.continuous_mode = not self.continuous_mode
                    mode_str = "ON" if self.continuous_mode else "OFF"
                    print(f"\n🔄 Continuous mode: {mode_str}")
                    
                elif key == ord('j'):  # J - Toggle JSON window
                    self.show_json_window = not self.show_json_window
                    window_str = "ON" if self.show_json_window else "OFF"
                    print(f"\n📄 JSON display: {window_str}")
                    if not self.show_json_window:
                        cv2.destroyWindow('MCP Messages (Live JSON)')
                    
                elif key == ord('t'):  # T - Toggle track display
                    self.show_tracks = not self.show_tracks
                    track_str = "ON" if self.show_tracks else "OFF"
                    print(f"\n🎯 Track display: {track_str}")
                    
                elif key == ord('r'):  # R - Reset fusion
                    self._reset_fusion()
                    
                elif key == ord('h'):  # H - Help
                    self._print_controls()
                    
                # Continuous processing mode
                if self.continuous_mode and self.frame_count % 30 == 0:
                    self._process_frame(frame, generate_captions=False)
        
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self._print_summary()
            self._save_session()
    
    def _process_frame(self, frame, generate_captions: bool = True):
        """Process a single frame through perception + fusion pipeline"""
        
        mode = "FULL (YOLO + LLaVA + Fusion)" if generate_captions else "DETECTION + FUSION"
        print(f"\n{'='*80}")
        print(f"Processing Frame {self.processed_count + 1} - {mode}")
        print(f"{'='*80}")
        
        start_time = time.time()
        
        # Step 1: Perception (YOLO + optional LLaVA)
        print("\n[PERCEPTION]")
        detections, annotated_img = self.engine.process_image(
            image=frame,
            drone_id=None,
            location=None,
            generate_captions=generate_captions,
            return_annotated=True
        )
        
        print(f"  → Found {len(detections)} detection(s)")
        
        # Step 2: Data Fusion (Temporal Tracking)
        print("\n[DATA FUSION]")
        tracks = self.fusion.process_detections(detections, drone_id=1)
        
        stats = self.fusion.get_statistics()
        print(f"  → Active tracks: {stats['active_tracks']}")
        print(f"  → Stable tracks: {stats['stable_tracks']}")
        print(f"  → High confidence: {stats['high_confidence_tracks']}")
        
        # Step 3: Generate MCP Messages (only for stable tracks)
        print("\n[MCP GENERATION]")
        stable_tracks = self.fusion.get_stable_tracks()
        
        frame_mcp_messages = self.fusion.create_mcp_messages(
            tracks=stable_tracks,
            uav_id=self.uav_id,
            sector=self.sector,
            correlation_id=self.mission_id,
            include_captions=generate_captions
        )
        
        print(f"  → Generated {len(frame_mcp_messages)} MCP message(s) from {len(stable_tracks)} stable track(s)")
        
        # Store messages
        self.mcp_messages.extend(frame_mcp_messages)
        
        processing_time = time.time() - start_time
        self.processing_times.append(processing_time)
        self.processed_count += 1
        
        print(f"\n✓ Processing complete in {processing_time:.2f}s")
        
        # Show results with track overlays
        if annotated_img is not None:
            result_frame = self._add_track_overlays(annotated_img.copy(), stable_tracks)
            
            # Add processing time
            cv2.putText(result_frame, f"Processing: {processing_time:.2f}s", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow('Detections with Tracking', result_frame)
        
        # Show JSON window if enabled
        if self.show_json_window and frame_mcp_messages:
            self._display_json_window(frame_mcp_messages)
    
    def _add_track_overlays(self, frame, tracks):
        """Add track information overlays to frame"""
        if not self.show_tracks or not tracks:
            return frame
        
        for track in tracks:
            # Get latest detection bbox
            latest_det = track.get_latest_detection()
            x1, y1, x2, y2 = latest_det.bbox_pixels
            
            # Draw track bounding box (different color than detection)
            color = (255, 0, 255)  # Magenta for tracks
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            
            # Track info label
            label = f"Track {track.track_id[-6:]}"  # Last 6 chars of ID
            label += f" | {track.class_name}"
            label += f" | {track.confidence:.2f}"
            label += f" | F:{track.frame_count}"
            
            # Background for label
            (label_w, label_h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame, (x1, y1 - label_h - 10), (x1 + label_w, y1), color, -1)
            
            # Label text
            cv2.putText(frame, label, (x1, y1 - 5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Draw centroid history (track path)
            if len(track.centroid_history) > 1:
                points = np.array(track.centroid_history, dtype=np.int32)
                cv2.polylines(frame, [points], False, color, 2)
        
        return frame
    
    def _reset_fusion(self):
        """Reset data fusion state"""
        print("\n🔄 Resetting data fusion...")
        
        old_stats = self.fusion.get_statistics()
        self.fusion.reset()
        
        print(f"  Cleared {old_stats['active_tracks']} active tracks")
        print(f"  Cleared {old_stats['completed_tracks']} completed tracks")
        print("✓ Fusion state reset")
    
    def _display_json_window(self, mcp_messages: List[dict]):
        """Display MCP messages as formatted JSON in OpenCV window"""
        json_str = json.dumps(mcp_messages[-1], indent=2)
        
        # Create blank image for text
        img_height = 900
        img_width = 1100
        img = np.zeros((img_height, img_width, 3), dtype=np.uint8)
        img[:] = (20, 20, 20)
        
        # Header
        cv2.putText(img, f"Latest MCP Message ({len(mcp_messages)} total)", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Split JSON into lines
        lines = json_str.split('\n')
        
        # Draw text line by line
        y_offset = 70
        for line in lines[:40]:
            if '"track_id"' in line:
                color = (255, 0, 255)  # Magenta for track ID
            elif '"schema"' in line or '"type"' in line:
                color = (0, 255, 255)  # Cyan for key fields
            elif '"label"' in line or '"confidence"' in line:
                color = (0, 255, 0)  # Green for detection data
            else:
                color = (200, 200, 200)
            
            cv2.putText(img, line[:90], (20, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            y_offset += 20
        
        cv2.putText(img, "Press J to hide", (10, img_height - 20), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (100, 100, 100), 1)
        
        cv2.imshow('MCP Messages (Live JSON)', img)
    
    def _save_frame(self, frame):
        """Save current frame to disk"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        frame_path = self.output_dir / f"frame_{timestamp}.jpg"
        cv2.imwrite(str(frame_path), frame)
        print(f"\n💾 Saved frame to: {frame_path}")
    
    def _add_overlay(self, frame):
        """Add info overlay to frame"""
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (500, 170), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        
        y_offset = 25
        line_height = 25
        
        stats = self.fusion.get_statistics()
        
        info_lines = [
            f"Frame: {self.frame_count}",
            f"Processed: {self.processed_count}",
            f"Active Tracks: {stats['active_tracks']}",
            f"Stable Tracks: {stats['stable_tracks']}",
            f"MCP Messages: {len(self.mcp_messages)}",
            f"Mode: {'CONTINUOUS' if self.continuous_mode else 'MANUAL'}"
        ]
        
        for i, line in enumerate(info_lines):
            y = y_offset + (i * line_height)
            cv2.putText(frame, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.6, (0, 255, 0), 2)
        
        return frame
    
    def _print_controls(self):
        """Print control instructions"""
        print("\n" + "="*80)
        print("  CONTROLS")
        print("="*80)
        print("  SPACE - Process frame with YOLO + LLaVA + Fusion")
        print("  D     - Process frame with YOLO + Fusion only (fast)")
        print("  S     - Save current frame to disk")
        print("  C     - Toggle continuous processing mode")
        print("  J     - Toggle live JSON display window")
        print("  T     - Toggle track overlay display")
        print("  R     - Reset fusion state (clear all tracks)")
        print("  H     - Show this help")
        print("  Q     - Quit and save results")
        print("="*80)
    
    def _print_summary(self):
        """Print session summary"""
        print("\n" + "="*80)
        print("  SESSION SUMMARY")
        print("="*80)
        print(f"Total frames captured:     {self.frame_count}")
        print(f"Frames processed:          {self.processed_count}")
        print(f"MCP messages generated:    {len(self.mcp_messages)}")
        
        stats = self.fusion.get_statistics()
        print(f"\nData Fusion Stats:")
        print(f"  Total tracks created:    {stats['total_tracks_created']}")
        print(f"  Active tracks:           {stats['active_tracks']}")
        print(f"  Stable tracks:           {stats['stable_tracks']}")
        print(f"  Completed tracks:        {stats['completed_tracks']}")
        
        if self.processing_times:
            avg_time = sum(self.processing_times) / len(self.processing_times)
            min_time = min(self.processing_times)
            max_time = max(self.processing_times)
            
            print(f"\nProcessing time stats:")
            print(f"  Average: {avg_time:.3f}s ({1/avg_time:.1f} FPS)")
            print(f"  Min:     {min_time:.3f}s")
            print(f"  Max:     {max_time:.3f}s")
    
    def _save_session(self):
        """Save session data to disk"""
        if not self.mcp_messages:
            print("\nNo MCP messages to save.")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save MCP messages
        mcp_path = self.output_dir / f"mcp_messages_{timestamp}.json"
        with open(mcp_path, 'w') as f:
            json.dump(self.mcp_messages, f, indent=2)
        
        print(f"\n💾 Saved {len(self.mcp_messages)} MCP messages to:")
        print(f"   {mcp_path}")
        
        # Save session metadata
        stats = self.fusion.get_statistics()
        
        metadata = {
            "mission_id": self.mission_id,
            "uav_id": self.uav_id,
            "sector": self.sector,
            "timestamp": timestamp,
            "frames_captured": self.frame_count,
            "frames_processed": self.processed_count,
            "mcp_messages": len(self.mcp_messages),
            "fusion_stats": stats,
            "avg_processing_time": sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0
        }
        
        metadata_path = self.output_dir / f"session_metadata_{timestamp}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"   {metadata_path}")


def main():
    """Run live camera test with fusion"""
    
    import argparse
    parser = argparse.ArgumentParser(description="Agent A Live Camera + Data Fusion Test")
    parser.add_argument("--camera", type=int, default=0, help="Camera ID (default: 0)")
    parser.add_argument("--model", type=str, help="Path to YOLO model")
    parser.add_argument("--output", type=str, default="output/agent_a_fusion_test", help="Output directory")
    parser.add_argument("--uav-id", type=str, default="USB_CAM_0", help="UAV identifier")
    parser.add_argument("--sector", type=str, default="TEST_ZONE", help="Sector identifier")
    parser.add_argument("--mission", type=str, help="Mission ID")
    
    args = parser.parse_args()
    
    test = LiveCameraWithFusion(
        camera_id=args.camera,
        yolo_model_path=args.model,
        output_dir=args.output,
        mission_id=args.mission,
        uav_id=args.uav_id,
        sector=args.sector
    )
    
    try:
        test.run()
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()