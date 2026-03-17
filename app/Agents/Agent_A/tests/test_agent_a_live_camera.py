# tests/test_agent_a_live_camera.py
"""
Agent A - Live USB Camera Test (UPDATED v2)

Tests the full perception pipeline:
1. Capture frames from USB camera
2. Run YOLO detection
3. Generate LLaVA captions (optional)
4. Create MCP messages
5. Display results and save logs

Controls:
  SPACE - Process current frame (YOLO + LLaVA)
  D     - Process with YOLO only (fast detection)
  S     - Save current frame and MCP messages
  Q     - Quit
  C     - Toggle continuous processing mode
  J     - Toggle live JSON display window
  
Prerequisites:
  - USB camera connected
  - YOLO model at PerceptionProcessing/yolo_models/rf3v1.pt
  - Ollama running with llava model (for captions): ollama serve
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
from PerceptionProcessing.mcp_schema import create_detection_from_yolo, create_caption_from_llava, MCPDetection


class LiveCameraTest:
    """Live USB camera testing for Agent A perception pipeline"""
    
    def __init__(self, 
                 camera_id: int = 0,
                 yolo_model_path: str = None,
                 output_dir: str = "output/agent_a_live_test",
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
        if output_dir == "output/agent_a_live_test":
            output_dir = str(Path(__file__).parent / "output" / "agent_a_live_test")
        
        # Initialize perception engine
        print("="*80)
        print("  AGENT A - LIVE USB CAMERA TEST")
        print("="*80)
        print(f"\nMission ID: {self.mission_id}")
        print(f"UAV ID: {self.uav_id}")
        print(f"Sector: {self.sector}")
        print(f"Output: {self.output_dir}")
        print("\nInitializing perception engine...")
        
        self.engine = PerceptionEngine(
            yolo_model_path=yolo_model_path,
            yolo_confidence=0.5,
            caption_threshold=0.7,
            device="cpu"  # Change to "cuda" if GPU available
        )
        
        print("✓ Perception engine ready")
        
        # Statistics
        self.frame_count = 0
        self.processed_count = 0
        self.mcp_messages = []
        self.processing_times = []
        
        # Mode flags
        self.continuous_mode = False
        self.show_json_window = False
        
    def _open_camera(self, camera_id: int):
        """
        Open camera with Windows-safe backend and a live-frame probe.
        Returns a VideoCapture on success, or None on failure.
        """
        import platform
        system = platform.system()

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
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            ret, _ = cap.read()
            if not ret:
                print(f"    ✗ {name}: opened but returned no frames")
                cap.release()
                continue
            print(f"    ✓ {name}: camera {camera_id} confirmed live")
            return cap
        return None

    def run(self):
        """Main test loop"""
        
        # Open camera with Windows-safe backend probe
        print("\nOpening camera...")
        cap = self._open_camera(self.camera_id)
        if cap is None:
            print(f"\n❌ Could not open camera {self.camera_id} on any backend.")
            print("\nTroubleshooting:")
            print("  1. Confirm the camera is physically connected")
            print("  2. Make sure it is not open in another app (Teams, Zoom, OBS…)")
            print("  3. Try a different ID:  python test_agent_a_live_camera.py --camera 1")
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
        
        # Check if Ollama is accessible
        self._check_ollama()
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("Failed to grab frame")
                    break
                
                self.frame_count += 1
                
                # Add overlay info
                display_frame = self._add_overlay(frame.copy())
                
                # Show live feed
                cv2.imshow('Agent A - Live Camera (Press H for help)', display_frame)
                
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
                    
                elif key == ord('h'):  # H - Help
                    self._print_controls()
                    
                # Continuous processing mode
                if self.continuous_mode and self.frame_count % 120 == 0:  # Every 30 frames (~1 second)
                    self._process_frame(frame, generate_captions=True)
        
        finally:
            cap.release()
            cv2.destroyAllWindows()
            self._print_summary()
            self._save_session()
    
    def _check_ollama(self):
        """Check if Ollama is running"""
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=2)
            if response.status_code == 200:
                print("✓ Ollama is running")
            else:
                print("⚠️  Ollama may not be running correctly")
        except:
            print("⚠️  WARNING: Cannot connect to Ollama")
            print("   Captions will not work. Start Ollama with: ollama serve")
    
    def _process_frame(self, frame, generate_captions: bool = True):
        """Process a single frame through perception pipeline"""
        
        mode = "FULL (YOLO + LLaVA)" if generate_captions else "DETECTION ONLY (YOLO)"
        print(f"\n{'='*80}")
        print(f"Processing Frame {self.processed_count + 1} - {mode}")
        print(f"{'='*80}")
        print(f"DEBUG: generate_captions parameter = {generate_captions}")
        
        start_time = time.time()
        
        # Run perception pipeline
        detections, annotated_img = self.engine.process_image(
            image=frame,
            drone_id=None,  # Will be set in MCP message
            location=None,  # USB camera doesn't have GPS
            generate_captions=generate_captions,
            return_annotated=True
        )
        
        processing_time = time.time() - start_time
        self.processing_times.append(processing_time)
        
        print(f"\n⏱️  Processing time: {processing_time:.3f}s")
        print(f"📦 Found {len(detections)} detection(s)")
        
        # DEBUG: Check caption status
        print(f"\nDEBUG: Caption status for each detection:")
        for idx, det in enumerate(detections, 1):
            has_caption = det.caption is not None and det.caption != ""
            print(f"  Detection {idx} ({det.class_name}): caption={'YES ✓' if has_caption else 'NO ✗'}")
            if has_caption:
                print(f"    Caption preview: {det.caption[:60]}...")
        
        # Convert to MCP messages
        frame_mcp_messages = []
        
        for i, det in enumerate(detections, 1):
            print(f"\n  Detection {i}:")
            print(f"    Class:      {det.class_name}")
            print(f"    Confidence: {det.confidence:.2%}")
            print(f"    BBox:       {det.bbox_pixels}")
            
            if det.caption:
                caption_preview = det.caption[:80] + "..." if len(det.caption) > 80 else det.caption
                print(f"    Caption:    {caption_preview}")
            
            # Create MCP Detection message
            mcp_detection = create_detection_from_yolo(
                detection=det,
                frame_number=self.processed_count,
                uav_id=self.uav_id,
                sector=self.sector,
                correlation_id=self.mission_id
            )
            
            frame_mcp_messages.append(mcp_detection.to_dict())
            
            # FIXED: If we have a caption, create MCP Caption message
            # (regardless of generate_captions flag - caption might already exist)
            if det.caption:
                mcp_caption = create_caption_from_llava(
                    caption_text=det.caption,
                    uav_id=self.uav_id,
                    sector=self.sector,
                    correlation_id=self.mission_id
                )
                frame_mcp_messages.append(mcp_caption.to_dict())
                print(f"    ✓ Created MCP.Caption message")
        
        # Store messages
        self.mcp_messages.extend(frame_mcp_messages)
        self.processed_count += 1
        
        # Show annotated result
        if annotated_img is not None:
            # Add processing time to annotated image
            cv2.putText(annotated_img, f"Processing: {processing_time:.2f}s", 
                       (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.imshow('Detections', annotated_img)
        
        # Show JSON window if enabled
        if self.show_json_window and frame_mcp_messages:
            self._display_json_window(frame_mcp_messages)
        
        print(f"\n✓ Generated {len(frame_mcp_messages)} MCP message(s)")
    
    def _display_json_window(self, mcp_messages: List[dict]):
        """Display MCP messages as formatted JSON in OpenCV window"""
        # Format latest message
        json_str = json.dumps(mcp_messages[-1], indent=2)
        
        # Create blank image for text
        img_height = 900
        img_width = 1100
        img = np.zeros((img_height, img_width, 3), dtype=np.uint8)
        
        # Dark background
        img[:] = (20, 20, 20)
        
        # Header
        cv2.putText(img, f"Latest MCP Message ({len(mcp_messages)} total)", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        
        # Split JSON into lines
        lines = json_str.split('\n')
        
        # Draw text line by line
        y_offset = 70
        for line in lines[:40]:  # Limit to first 40 lines
            # Color code based on content
            if '"schema"' in line or '"type"' in line:
                color = (0, 255, 255)  # Cyan for key fields
            elif '"label"' in line or '"confidence"' in line:
                color = (0, 255, 0)  # Green for detection data
            elif '"caption"' in line:
                color = (255, 100, 255)  # Pink for captions
            else:
                color = (200, 200, 200)  # Gray for others
            
            cv2.putText(img, line[:90], (20, y_offset), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
            y_offset += 20
        
        # Footer
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
        # Background for text
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (450, 145), (0, 0, 0), -1)
        frame = cv2.addWeighted(frame, 0.7, overlay, 0.3, 0)
        
        # Text info
        y_offset = 25
        line_height = 25
        
        info_lines = [
            f"Frame: {self.frame_count}",
            f"Processed: {self.processed_count}",
            f"MCP Messages: {len(self.mcp_messages)}",
            f"Mode: {'CONTINUOUS' if self.continuous_mode else 'MANUAL'}",
            f"JSON Window: {'ON' if self.show_json_window else 'OFF'}"
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
        print("  SPACE - Process frame with YOLO + LLaVA (full pipeline)")
        print("  D     - Process frame with YOLO only (fast detection)")
        print("  S     - Save current frame to disk")
        print("  C     - Toggle continuous processing mode")
        print("  J     - Toggle live JSON display window")
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
        
        # Count message types
        detection_msgs = sum(1 for m in self.mcp_messages if m.get('type') == 'MCP.Detection')
        caption_msgs = sum(1 for m in self.mcp_messages if m.get('type') == 'MCP.Caption')
        print(f"  - MCP.Detection:         {detection_msgs}")
        print(f"  - MCP.Caption:           {caption_msgs}")
        
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
        
        # Save MCP messages as JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        mcp_path = self.output_dir / f"mcp_messages_{timestamp}.json"
        
        with open(mcp_path, 'w') as f:
            json.dump(self.mcp_messages, f, indent=2)
        
        print(f"\n💾 Saved {len(self.mcp_messages)} MCP messages to:")
        print(f"   {mcp_path}")
        
        # Save session metadata
        metadata = {
            "mission_id": self.mission_id,
            "uav_id": self.uav_id,
            "sector": self.sector,
            "timestamp": timestamp,
            "frames_captured": self.frame_count,
            "frames_processed": self.processed_count,
            "mcp_messages": len(self.mcp_messages),
            "detection_messages": sum(1 for m in self.mcp_messages if m.get('type') == 'MCP.Detection'),
            "caption_messages": sum(1 for m in self.mcp_messages if m.get('type') == 'MCP.Caption'),
            "avg_processing_time": sum(self.processing_times) / len(self.processing_times) if self.processing_times else 0
        }
        
        metadata_path = self.output_dir / f"session_metadata_{timestamp}.json"
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        print(f"   {metadata_path}")


def main():
    """Run live camera test"""
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description="Agent A Live USB Camera Test")
    parser.add_argument("--camera", type=int, default=0, help="Camera ID (default: 0)")
    parser.add_argument("--model", type=str, help="Path to YOLO model")
    parser.add_argument("--output", type=str, default="output/agent_a_live_test", help="Output directory")
    parser.add_argument("--uav-id", type=str, default="USB_CAM_0", help="UAV identifier")
    parser.add_argument("--sector", type=str, default="TEST_ZONE", help="Sector identifier")
    parser.add_argument("--mission", type=str, help="Mission ID")
    
    args = parser.parse_args()
    
    # Create and run test
    test = LiveCameraTest(
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