# Agent_A/tests/test_data_fusion.py

"""
Data Fusion Module Test Suite

Tests temporal tracking, confidence aggregation, and MCP message generation.
Integrates with existing PerceptionEngine and test infrastructure.

Prerequisites:
    - YOLO model: Agent_A/PerceptionProcessing/yolo_models/rf3v1.pt
    - Test images: Agent_A/tests/images/
    - Ollama server (optional, for caption tests)

Run:
    python tests/test_data_fusion.py
    pytest tests/test_data_fusion.py -v
"""

import sys
from pathlib import Path

# Add Agent_A to path
agent_a_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_a_dir))

import cv2
import json
import numpy as np
from typing import List

from PerceptionProcessing.PerceptionEngine import PerceptionEngine
from PerceptionProcessing.Detection import Detection
from DataFusion.DataFusion import DataFusion, TrackedDetection


class TestDataFusion:
    """Unit and integration tests for DataFusion module"""
    
    @staticmethod
    def get_paths():
        """Get standard paths for testing"""
        return {
            'model':  agent_a_dir / "PerceptionProcessing" / "yolo_models" / "rf3v1.pt",
            'image':  agent_a_dir / "tests" / "images" / "drone_testing1.jpg",
            'output': agent_a_dir / "tests" / "output" / "fusion_tests"
        }
    
    def test_fusion_initialization(self):
        """Test 1: DataFusion initializes correctly"""
        print("\n" + "="*80)
        print("  TEST 1: DataFusion Initialization")
        print("="*80)
        
        try:
            fusion = DataFusion(
                iou_threshold=0.3,
                min_track_frames=3,
                max_track_age=30
            )
            
            print("✓ DataFusion initialized successfully")
            assert fusion is not None
            assert fusion.iou_threshold == 0.3
            assert fusion.min_track_frames == 3
            assert fusion.max_track_age == 30
            assert len(fusion.active_tracks) == 0
            assert len(fusion.completed_tracks) == 0
            assert fusion.frame_number == 0
            
            print(f"✓ IoU threshold: {fusion.iou_threshold}")
            print(f"✓ Min track frames: {fusion.min_track_frames}")
            print(f"✓ Max track age: {fusion.max_track_age}")
            print("✓ All parameters validated")
            
        except Exception as e:
            print(f"✗ Initialization failed: {e}")
            raise
    
    def test_single_frame_processing(self):
        """Test 2: Process single frame of detections"""
        print("\n" + "="*80)
        print("  TEST 2: Single Frame Processing")
        print("="*80)
        
        paths = self.get_paths()
        
        # Initialize perception and fusion
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        fusion = DataFusion()
        
        # Get detections
        detections, _ = engine.process_image_path(
            str(paths['image']),
            drone_id=1,
            location="28.6024,-81.2001",
            generate_captions=False
        )
        
        print(f"Input: {len(detections)} detection(s) from YOLO")
        
        # Process through fusion
        tracks = fusion.process_detections(detections, drone_id=1)
        
        print(f"Output: {len(tracks)} track(s) created")
        
        # Verify
        assert len(tracks) == len(detections), "Each detection should create a track"
        assert fusion.frame_number == 1, "Frame counter should increment"
        
        for track in tracks:
            assert track.frame_count == 1, "New tracks should have frame_count=1"
            assert track.track_id.startswith("track_"), "Track ID should have correct prefix"
            print(f"  ✓ Track {track.track_id}: {track.class_name} (conf={track.confidence:.2f})")
        
        print("✓ Single frame processing works correctly")
    
    def test_multi_frame_tracking(self):
        """Test 3: Track objects across multiple frames"""
        print("\n" + "="*80)
        print("  TEST 3: Multi-Frame Tracking")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        fusion = DataFusion(
            iou_threshold=0.3,
            min_track_frames=3
        )
        
        # Simulate 5 frames of the same image
        num_frames = 5
        print(f"Simulating {num_frames} frames...")
        
        all_tracks = []
        
        for i in range(num_frames):
            detections, _ = engine.process_image_path(
                str(paths['image']),
                drone_id=1,
                generate_captions=False
            )
            
            tracks = fusion.process_detections(detections, drone_id=1)
            all_tracks.append(tracks)
            
            print(f"  Frame {i+1}: {len(tracks)} tracks, {len(fusion.active_tracks)} active")
        
        # Verify tracking
        stats = fusion.get_statistics()
        
        print(f"\nTracking Results:")
        print(f"  Total frames: {stats['frame_number']}")
        print(f"  Active tracks: {stats['active_tracks']}")
        print(f"  Stable tracks: {stats['stable_tracks']}")
        
        # Check for stable tracks (seen in 3+ frames)
        stable_tracks = fusion.get_stable_tracks()
        
        assert len(stable_tracks) > 0, "Should have stable tracks after 5 frames"
        
        for track in stable_tracks:
            print(f"\n  Stable Track: {track.track_id}")
            print(f"    Class: {track.class_name}")
            print(f"    Confidence: {track.confidence:.3f}")
            print(f"    Seen in {track.frame_count} frames")
            assert track.frame_count >= 3, "Stable tracks should appear in 3+ frames"
        
        print("\n✓ Multi-frame tracking works correctly")
    
    def test_confidence_aggregation(self):
        """Test 4: Verify confidence smoothing with EMA"""
        print("\n" + "="*80)
        print("  TEST 4: Confidence Aggregation (EMA)")
        print("="*80)
        
        # Create synthetic detections with varying confidence
        det1 = Detection(
            class_id=0,
            class_name="person",
            confidence=0.8,
            bbox_normalized=(0.1, 0.1, 0.3, 0.3),
            bbox_pixels=(100, 100, 300, 300)
        )
        
        det2 = Detection(
            class_id=0,
            class_name="person",
            confidence=0.9,  # Higher confidence
            bbox_normalized=(0.1, 0.1, 0.3, 0.3),
            bbox_pixels=(100, 100, 300, 300)  # Same location
        )
        
        fusion = DataFusion()
        
        # Frame 1
        tracks1 = fusion.process_detections([det1])
        initial_conf = tracks1[0].confidence
        print(f"Frame 1 confidence: {initial_conf:.3f}")
        
        # Frame 2 (same object, higher confidence)
        tracks2 = fusion.process_detections([det2])
        updated_conf = fusion.active_tracks[0].confidence
        
        print(f"Frame 2 confidence: {updated_conf:.3f}")
        print(f"Expected (EMA):     {0.7 * initial_conf + 0.3 * 0.9:.3f}")
        
        # Verify EMA calculation (α = 0.3)
        expected_conf = 0.7 * initial_conf + 0.3 * 0.9
        
        assert abs(updated_conf - expected_conf) < 0.001, "Confidence should be EMA-smoothed"
        assert updated_conf > initial_conf, "Higher detection should increase confidence"
        
        print("✓ Exponential moving average works correctly")
    
    def test_iou_calculation(self):
        """Test 5: Verify IoU calculation for track association"""
        print("\n" + "="*80)
        print("  TEST 5: IoU Calculation")
        print("="*80)
        
        from DataFusion.DataFusion import TrackedDetection
        
        det = Detection(
            class_id=0,
            class_name="person",
            confidence=0.8,
            bbox_normalized=(0.1, 0.1, 0.3, 0.3),
            bbox_pixels=(100, 100, 300, 300)
        )
        
        import uuid
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        
        track = TrackedDetection(det, frame_number=1, timestamp=timestamp)
        
        # Test 1: Perfect overlap
        bbox_same = (100, 100, 300, 300)
        iou_same = track.iou(track.last_bbox, bbox_same)
        print(f"IoU (same bbox):     {iou_same:.3f} (expected: 1.0)")
        assert abs(iou_same - 1.0) < 0.001, "Same bbox should have IoU = 1.0"
        
        # Test 2: Partial overlap
        bbox_overlap = (150, 150, 350, 350)
        iou_overlap = track.iou(track.last_bbox, bbox_overlap)
        print(f"IoU (partial):       {iou_overlap:.3f}")
        assert 0.0 < iou_overlap < 1.0, "Partial overlap should be between 0 and 1"
        
        # Test 3: No overlap
        bbox_no_overlap = (400, 400, 600, 600)
        iou_no_overlap = track.iou(track.last_bbox, bbox_no_overlap)
        print(f"IoU (no overlap):    {iou_no_overlap:.3f} (expected: 0.0)")
        assert iou_no_overlap == 0.0, "No overlap should have IoU = 0.0"
        
        print("✓ IoU calculation is correct")
    
    def test_track_pruning(self):
        """Test 6: Verify old tracks are pruned"""
        print("\n" + "="*80)
        print("  TEST 6: Track Pruning (Old Track Removal)")
        print("="*80)
        
        fusion = DataFusion(
            max_track_age=5,  # Remove after 5 frames without update
            min_track_frames=2
        )
        
        # Create initial detection
        det = Detection(
            class_id=0,
            class_name="person",
            confidence=0.8,
            bbox_normalized=(0.1, 0.1, 0.3, 0.3),
            bbox_pixels=(100, 100, 300, 300)
        )
        
        # Frame 1: Create track
        fusion.process_detections([det])
        assert len(fusion.active_tracks) == 1, "Should have 1 active track"
        print(f"Frame 1: {len(fusion.active_tracks)} active track(s)")
        
        # Frames 2-6: Process with NO detections (simulate object leaving frame)
        for i in range(2, 7):
            fusion.process_detections([])  # Empty detections
            print(f"Frame {i}: {len(fusion.active_tracks)} active track(s)")
        
        # After max_track_age=5, track should be pruned
        assert len(fusion.active_tracks) == 0, "Old track should be pruned"
        
        # Track should be in completed_tracks (if it was stable)
        print(f"Completed tracks: {len(fusion.completed_tracks)}")
        
        print("✓ Track pruning works correctly")
    
    def test_mcp_message_generation(self):
        """Test 7: Generate MCP messages from tracks"""
        print("\n" + "="*80)
        print("  TEST 7: MCP Message Generation")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        fusion = DataFusion(min_track_frames=2)
        
        # Process 3 frames to get stable tracks
        for i in range(3):
            detections, _ = engine.process_image_path(
                str(paths['image']),
                drone_id=1,
                location="28.6024,-81.2001",
                generate_captions=False
            )
            fusion.process_detections(detections, drone_id=1)
        
        # Generate MCP messages
        mcp_messages = fusion.create_mcp_messages(
            tracks=fusion.get_stable_tracks(),
            uav_id="UAV_1",
            sector="A1",
            correlation_id="test_mission_001",
            include_captions=False
        )
        
        print(f"Generated {len(mcp_messages)} MCP message(s)")
        
        assert len(mcp_messages) > 0, "Should generate at least one message"
        
        # Verify message structure
        for i, msg in enumerate(mcp_messages, 1):
            print(f"\nMessage {i}:")
            print(f"  Schema: {msg.get('schema')}")
            print(f"  Type: {msg.get('type')}")
            print(f"  Event ID: {msg.get('event_id')}")
            
            # Required fields
            assert msg['schema'] == 'mcp.v0.1', "Should have correct schema"
            assert msg['type'] == 'MCP.Detection', "Should be Detection type"
            assert 'event_id' in msg, "Should have event_id"
            assert 'ts' in msg, "Should have timestamp"
            assert 'source' in msg, "Should have source"
            assert 'payload' in msg, "Should have payload"
            
            # Payload fields
            payload = msg['payload']
            assert 'label' in payload, "Payload should have label"
            assert 'confidence' in payload, "Payload should have confidence"
            
            print(f"  Label: {payload['label']}")
            print(f"  Confidence: {payload['confidence']:.2%}")
            
            if 'track_id' in msg:
                print(f"  Track ID: {msg['track_id']}")
            
            if 'priority' in msg:
                print(f"  Priority: {msg['priority']}")
        
        # Save sample message
        paths['output'].mkdir(parents=True, exist_ok=True)
        sample_path = paths['output'] / "sample_mcp_message.json"
        
        with open(sample_path, 'w') as f:
            json.dump(mcp_messages[0], f, indent=2)
        
        print(f"\n✓ Saved sample message to: {sample_path}")
        print("✓ MCP message generation works correctly")
    
    def test_priority_calculation(self):
        """Test 8: Verify priority assignment based on class and confidence"""
        print("\n" + "="*80)
        print("  TEST 8: Priority Calculation")
        print("="*80)
        
        fusion = DataFusion()
        
        # Create person detection (high priority)
        person_det = Detection(
            class_id=0,
            class_name="person",
            confidence=0.95,
            bbox_normalized=(0.1, 0.1, 0.3, 0.3),
            bbox_pixels=(100, 100, 300, 300)
        )
        
        # Create vehicle detection (medium priority)
        vehicle_det = Detection(
            class_id=1,
            class_name="vehicle",
            confidence=0.95,
            bbox_normalized=(0.5, 0.5, 0.7, 0.7),
            bbox_pixels=(500, 500, 700, 700)
        )
        
        # Process
        fusion.process_detections([person_det, vehicle_det])
        
        # Generate MCP messages
        messages = fusion.create_mcp_messages(
            tracks=fusion.active_tracks,
            uav_id="UAV_1"
        )
        
        # Find person and vehicle messages
        person_msg = next(m for m in messages if m['payload']['label'] == 'person')
        vehicle_msg = next(m for m in messages if m['payload']['label'] == 'vehicle')
        
        person_priority = person_msg.get('priority', 50)
        vehicle_priority = vehicle_msg.get('priority', 50)
        
        print(f"Person priority:  {person_priority} (should be 80-100)")
        print(f"Vehicle priority: {vehicle_priority} (should be 50-80)")
        
        assert person_priority > vehicle_priority, "Person should have higher priority"
        assert person_priority >= 80, "Person with 95% confidence should have priority >= 80"
        
        print("✓ Priority calculation is correct")
    
    def test_multi_drone_tracking(self):
        """Test 9: Track detections from multiple drones"""
        print("\n" + "="*80)
        print("  TEST 9: Multi-Drone Tracking")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        fusion = DataFusion()
        
        # Get detections
        detections, _ = engine.process_image_path(
            str(paths['image']),
            generate_captions=False
        )
        
        # Process from drone 1
        tracks_drone1 = fusion.process_detections(detections, drone_id=1)
        print(f"Drone 1: {len(tracks_drone1)} tracks")
        
        # Process from drone 2
        tracks_drone2 = fusion.process_detections(detections, drone_id=2)
        print(f"Drone 2: {len(tracks_drone2)} tracks")
        
        # Verify per-drone tracking
        assert 1 in fusion.drone_tracks, "Should have tracks for drone 1"
        assert 2 in fusion.drone_tracks, "Should have tracks for drone 2"
        
        print(f"Total active tracks: {len(fusion.active_tracks)}")
        print(f"Drone 1 tracks: {len(fusion.drone_tracks[1])}")
        print(f"Drone 2 tracks: {len(fusion.drone_tracks[2])}")
        
        print("✓ Multi-drone tracking works")
    
    def test_location_averaging(self):
        """Test 10: GPS location averaging across frames"""
        print("\n" + "="*80)
        print("  TEST 10: GPS Location Averaging")
        print("="*80)
        
        fusion = DataFusion()
        
        # Create detections with GPS data
        locations = [
            "28.6020,-81.2000",
            "28.6022,-81.2002",
            "28.6024,-81.2004"
        ]
        
        for i, loc in enumerate(locations):
            det = Detection(
                class_id=0,
                class_name="person",
                confidence=0.8,
                bbox_normalized=(0.1, 0.1, 0.3, 0.3),
                bbox_pixels=(100, 100, 300, 300),
                location=loc
            )
            fusion.process_detections([det])
            print(f"Frame {i+1} location: {loc}")
        
        # Get averaged location
        track = fusion.active_tracks[0]
        avg_location = track.get_average_location()
        
        print(f"\nAveraged location: {avg_location}")
        
        assert avg_location is not None, "Should have averaged location"
        
        # Parse and verify
        lat_str, lon_str = avg_location.split(',')
        avg_lat = float(lat_str.strip())
        avg_lon = float(lon_str.strip())
        
        # Should be approximately in the middle
        assert 28.602 < avg_lat < 28.603, "Averaged latitude should be in middle range"
        assert -81.201 < avg_lon < -81.200, "Averaged longitude should be in middle range"
        
        print("✓ GPS location averaging works correctly")


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "#"*80)
    print("#" + " "*24 + "DATA FUSION TEST SUITE" + " "*33 + "#")
    print("#"*80)
    
    test_suite = TestDataFusion()
    
    tests = [
        ("Initialization", test_suite.test_fusion_initialization),
        ("Single Frame", test_suite.test_single_frame_processing),
        ("Multi-Frame Tracking", test_suite.test_multi_frame_tracking),
        ("Confidence Aggregation", test_suite.test_confidence_aggregation),
        ("IoU Calculation", test_suite.test_iou_calculation),
        ("Track Pruning", test_suite.test_track_pruning),
        ("MCP Generation", test_suite.test_mcp_message_generation),
        ("Priority Calculation", test_suite.test_priority_calculation),
        ("Multi-Drone", test_suite.test_multi_drone_tracking),
        ("Location Averaging", test_suite.test_location_averaging),
    ]
    
    passed = 0
    failed = 0
    errors = []
    
    for test_name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            failed += 1
            errors.append((test_name, f"Assertion failed: {e}"))
            print(f"\n✗ TEST FAILED: {test_name}")
        except Exception as e:
            failed += 1
            errors.append((test_name, f"Error: {e}"))
            print(f"\n✗ TEST ERROR: {test_name}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "="*80)
    print("  TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {len(tests)}")
    print(f"Passed: {passed} ✓")
    print(f"Failed: {failed} ✗")
    
    if errors:
        print("\nFailed Tests:")
        for test_name, error in errors:
            print(f"  • {test_name}: {error}")
    
    if failed == 0:
        print("\n" + "="*80)
        print("  ALL TESTS PASSED ✓")
        print("="*80)
        print("\n🎉 DataFusion module is ready for integration!")
        print("\nNext steps:")
        print("  1. Integrate with live camera test (test_agent_a_live_camera.py)")
        print("  2. Test with video sequences")
        print("  3. Test USB communication with MCP messages")
    else:
        print("\n" + "="*80)
        print("  SOME TESTS FAILED ✗")
        print("="*80)
    
    print("\nPrerequisites:")
    print("  1. YOLO model: Agent_A/PerceptionProcessing/yolo_models/rf3v1.pt")
    print("  2. Test image: Agent_A/tests/images/drone_testing1.jpg")
    
    paths = TestDataFusion.get_paths()
    print(f"\nOutputs saved to:")
    print(f"  {paths['output']}/")
    
    return passed, failed


if __name__ == "__main__":
    import sys
    
    try:
        passed, failed = run_all_tests()
        sys.exit(0 if failed == 0 else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)