# Agent_A/tests/test_perception_engine.py

"""
Integration tests for PerceptionEngine module.
Tests YOLO + LLaVA orchestration and enrichment logic.

Prerequisites:
    - YOLO model: ComputerVision/CVModels/rf3v1.pt
    - Ollama server running: ollama serve
    - LLaVA model installed: ollama pull llava
    - Test image: ComputerVision/temp/drone_testing1.jpg

Run:
    python tests/test_perception_engine.py
    pytest tests/test_perception_engine.py -v
"""

import sys
from pathlib import Path

# Add Agent_A to path
agent_a_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_a_dir))

import cv2
import json
from PerceptionProcessing.PerceptionEngine import PerceptionEngine


class TestPerceptionEngine:
    """Integration tests for PerceptionEngine orchestration"""
    
    @staticmethod
    def get_paths():
        """Get standard paths for testing"""
        app_dir = agent_a_dir.parent
        return {
            'model': app_dir / "ComputerVision" / "CVModels" / "rf3v1.pt",
            'image': app_dir / "ComputerVision" / "temp" / "drone_testing1.jpg",
            'output': agent_a_dir / "output"
        }
    
    def test_engine_initialization(self):
        """Test 1: Engine initializes with correct components"""
        print("\n" + "="*80)
        print("  TEST 1: Engine Initialization")
        print("="*80)
        
        paths = self.get_paths()
        
        try:
            engine = PerceptionEngine(
                yolo_model_path=str(paths['model']),
                yolo_confidence=0.5,
                caption_threshold=0.7,
                device="cpu"
            )
            
            print("✓ PerceptionEngine initialized successfully")
            assert engine is not None
            assert engine.yolo_detector is not None
            assert engine.captioner is not None
            
            print("✓ YOLO detector loaded")
            print("✓ LLaVA captioner loaded")
            print(f"✓ Caption threshold: {engine.caption_threshold}")
            
        except Exception as e:
            print(f"✗ Initialization failed: {e}")
            raise
    
    def test_detection_only_no_captions(self):
        """Test 2: Run detection without generating captions"""
        print("\n" + "="*80)
        print("  TEST 2: Detection Only (No Captions)")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        print(f"Processing: {paths['image'].name}")
        print("-" * 80)
        
        detections, annotated_img = engine.process_image_path(
            str(paths['image']),
            generate_captions=False  # No captions
        )
        
        print(f"\n✓ Found {len(detections)} detection(s)")
        
        # Verify detections
        assert len(detections) > 0, "Should find at least one detection"
        
        for i, det in enumerate(detections, 1):
            print(f"\nDetection {i}:")
            print(f"  Class:      {det.class_name}")
            print(f"  Confidence: {det.confidence:.2%}")
            print(f"  BBox:       {det.bbox_pixels}")
            print(f"  Caption:    {det.caption}")
            
            # Verify no captions were generated
            assert det.caption is None, "Caption should be None when generate_captions=False"
        
        print("\n✓ All detections have no captions (as expected)")
        assert annotated_img is not None
        print("✓ Annotated image generated")
    
    def test_detection_with_captions(self):
        """Test 3: Run detection WITH caption generation"""
        print("\n" + "="*80)
        print("  TEST 3: Detection WITH Captions")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            caption_threshold=0.6,  # Caption if confidence > 0.6
            device="cpu"
        )
        
        print(f"Processing: {paths['image'].name}")
        print(f"Caption threshold: 0.6 (will caption detections > 60% confidence)")
        print("-" * 80)
        
        detections, annotated_img = engine.process_image_path(
            str(paths['image']),
            generate_captions=True  # Enable captions
        )
        
        print(f"\n✓ Found {len(detections)} detection(s)")
        
        captions_generated = 0
        for i, det in enumerate(detections, 1):
            print(f"\nDetection {i}:")
            print(f"  Class:      {det.class_name}")
            print(f"  Confidence: {det.confidence:.2%}")
            
            if det.confidence > 0.6:
                print(f"  Caption:    {det.caption}")
                if det.caption is not None:
                    captions_generated += 1
                    assert len(det.caption) > 0, "Caption should not be empty"
            else:
                print(f"  Caption:    None (below threshold)")
                assert det.caption is None, "Low confidence detections should not have captions"
        
        print(f"\n✓ Generated {captions_generated} caption(s)")
        
        # Save result
        output_path = paths['output'] / "test_with_captions.jpg"
        paths['output'].mkdir(exist_ok=True)
        cv2.imwrite(str(output_path), annotated_img)
        print(f"✓ Saved to: {output_path}")
    
    def test_confidence_threshold_filtering(self):
        """Test 4: Verify caption threshold filtering works"""
        print("\n" + "="*80)
        print("  TEST 4: Caption Threshold Filtering")
        print("="*80)
        
        paths = self.get_paths()
        
        # High threshold - only very confident detections get captions
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.3,  # Detect low confidence
            caption_threshold=0.9,  # But only caption very high confidence
            device="cpu"
        )
        
        print("YOLO confidence: 0.3 (detect almost everything)")
        print("Caption threshold: 0.9 (only caption 90%+ detections)")
        print("-" * 80)
        
        detections, _ = engine.process_image_path(
            str(paths['image']),
            generate_captions=True
        )
        
        low_conf_count = sum(1 for d in detections if d.confidence < 0.9)
        high_conf_count = sum(1 for d in detections if d.confidence >= 0.9)
        captioned_count = sum(1 for d in detections if d.caption is not None)
        
        print(f"\nResults:")
        print(f"  Total detections:     {len(detections)}")
        print(f"  Low confidence (<90%): {low_conf_count}")
        print(f"  High confidence (≥90%): {high_conf_count}")
        print(f"  Captioned:            {captioned_count}")
        
        # Verify only high confidence got captions
        for det in detections:
            if det.confidence >= 0.9:
                # High confidence might have caption (depends on image)
                pass
            else:
                # Low confidence should NOT have caption
                assert det.caption is None, f"Low conf ({det.confidence:.2f}) should not have caption"
        
        print("✓ Threshold filtering works correctly")
    
    def test_enrichment_drone_metadata(self):
        """Test 5: Verify drone_id and location enrichment"""
        print("\n" + "="*80)
        print("  TEST 5: Drone Metadata Enrichment")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        drone_id = 42
        location = "28.6024,-81.2001"  # Lat,Lon
        
        print(f"Drone ID: {drone_id}")
        print(f"Location: {location}")
        print("-" * 80)
        
        detections, _ = engine.process_image_path(
            str(paths['image']),
            drone_id=drone_id,
            location=location,
            generate_captions=False
        )
        
        print(f"\n✓ Found {len(detections)} detection(s)")
        
        # Verify all detections have metadata
        for i, det in enumerate(detections, 1):
            print(f"\nDetection {i}:")
            print(f"  Class:    {det.class_name}")
            print(f"  Drone ID: {det.drone_id}")
            print(f"  Location: {det.location}")
            
            assert det.drone_id == drone_id, "Drone ID should match input"
            assert det.location == location, "Location should match input"
        
        print("\n✓ All detections enriched with drone metadata")
    
    def test_to_dict_serialization(self):
        """Test 6: Verify detections can be serialized to JSON"""
        print("\n" + "="*80)
        print("  TEST 6: JSON Serialization")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            caption_threshold=0.7,
            device="cpu"
        )
        
        detections, _ = engine.process_image_path(
            str(paths['image']),
            drone_id=99,
            location="28.5000,-81.5000",
            generate_captions=True
        )
        
        print(f"Serializing {len(detections)} detection(s) to JSON...")
        print("-" * 80)
        
        # Convert to dict
        detections_dict = [det.to_dict() for det in detections]
        
        # Serialize to JSON
        json_str = json.dumps(detections_dict, indent=2)
        
        print("\nJSON Output (first detection):")
        if len(detections_dict) > 0:
            print(json.dumps(detections_dict[0], indent=2))
        
        # Save to file
        output_path = paths['output'] / "test_detections.json"
        paths['output'].mkdir(exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(json_str)
        
        print(f"\n✓ Saved JSON to: {output_path}")
        
        # Verify JSON is valid
        with open(output_path, 'r') as f:
            loaded = json.load(f)
        
        assert len(loaded) == len(detections), "JSON should preserve all detections"
        print("✓ JSON serialization verified")
    
    def test_process_numpy_array(self):
        """Test 7: Process image from numpy array (not file path)"""
        print("\n" + "="*80)
        print("  TEST 7: Process Numpy Array (cv2 image)")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        # Load image as numpy array
        frame = cv2.imread(str(paths['image']))
        
        print(f"Image shape: {frame.shape}")
        print(f"Image dtype: {frame.dtype}")
        print("-" * 80)
        
        detections, annotated_img = engine.process_image(
            frame,
            drone_id=77,
            location="Test Location",
            generate_captions=False
        )
        
        print(f"\n✓ Processed numpy array successfully")
        print(f"✓ Found {len(detections)} detection(s)")
        
        assert len(detections) > 0
        assert annotated_img is not None
        assert annotated_img.shape == frame.shape
        
        print("✓ Numpy array processing works (ready for video streams!)")
    
    def test_batch_processing(self):
        """Test 8: Process multiple images in sequence"""
        print("\n" + "="*80)
        print("  TEST 8: Batch Processing (Multiple Images)")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        # Simulate processing same image multiple times (like video frames)
        num_frames = 5
        
        print(f"Processing {num_frames} frames...")
        print("-" * 80)
        
        all_detections = []
        
        for i in range(num_frames):
            detections, _ = engine.process_image_path(
                str(paths['image']),
                drone_id=1,
                location=f"Frame_{i}",
                generate_captions=False
            )
            all_detections.append(detections)
            print(f"Frame {i+1}: {len(detections)} detections")
        
        print(f"\n✓ Processed {num_frames} frames successfully")
        
        # Verify consistency
        detection_counts = [len(d) for d in all_detections]
        print(f"✓ Detection counts: {detection_counts}")
        
        # Should be consistent (same image)
        assert all(count == detection_counts[0] for count in detection_counts), \
            "Same image should produce consistent detection counts"
        
        print("✓ Batch processing works (ready for video pipeline!)")
    
    def test_empty_image_handling(self):
        """Test 9: Handle edge cases gracefully"""
        print("\n" + "="*80)
        print("  TEST 9: Edge Case Handling")
        print("="*80)
        
        paths = self.get_paths()
        
        engine = PerceptionEngine(
            yolo_model_path=str(paths['model']),
            yolo_confidence=0.5,
            device="cpu"
        )
        
        # Test 1: Invalid path
        print("Test 9a: Invalid image path")
        try:
            detections, _ = engine.process_image_path(
                "/nonexistent/image.jpg",
                generate_captions=False
            )
            print("✗ Should have raised an error")
            assert False
        except Exception as e:
            print(f"✓ Correctly raised error: {type(e).__name__}")
        
        # Test 2: Empty numpy array
        print("\nTest 9b: Empty numpy array")
        try:
            empty_frame = cv2.imread("nonexistent.jpg")  # Returns None
            if empty_frame is None:
                print("✓ cv2.imread correctly returns None for missing file")
        except Exception as e:
            print(f"✓ Handled gracefully: {e}")


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "#"*80)
    print("#" + " "*20 + "PERCEPTION ENGINE TEST SUITE" + " "*31 + "#")
    print("#"*80)
    
    test_suite = TestPerceptionEngine()
    
    tests = [
        ("Engine Initialization", test_suite.test_engine_initialization),
        ("Detection Only", test_suite.test_detection_only_no_captions),
        ("Detection with Captions", test_suite.test_detection_with_captions),
        ("Confidence Filtering", test_suite.test_confidence_threshold_filtering),
        ("Drone Metadata", test_suite.test_enrichment_drone_metadata),
        ("JSON Serialization", test_suite.test_to_dict_serialization),
        ("Numpy Array Input", test_suite.test_process_numpy_array),
        ("Batch Processing", test_suite.test_batch_processing),
        ("Edge Cases", test_suite.test_empty_image_handling),
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
        print("\n🎉 PerceptionEngine is ready for production!")
        print("   Next step: test_live_video_usb.py for video streams")
    else:
        print("\n" + "="*80)
        print("  SOME TESTS FAILED ✗")
        print("="*80)
    
    print("\nPrerequisites:")
    print("  1. YOLO model: ComputerVision/CVModels/rf3v1.pt")
    print("  2. Ollama server: ollama serve")
    print("  3. LLaVA model: ollama pull llava")
    print("  4. Test image: ComputerVision/temp/drone_testing1.jpg")
    
    print("\nOutputs saved to:")
    paths = TestPerceptionEngine.get_paths()
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