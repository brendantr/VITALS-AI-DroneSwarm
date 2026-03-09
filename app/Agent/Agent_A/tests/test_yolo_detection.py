# Agent_A/tests/test_yolo_detection.py

import sys
import os
from pathlib import Path

# Get the Agent_A directory
agent_a_dir = Path(__file__).resolve().parent.parent
print(f"Agent_A directory: {agent_a_dir}")

# Add Agent_A to Python path
sys.path.insert(0, str(agent_a_dir))

print(f"Python path: {sys.path[0]}")
print(f"Looking for: {agent_a_dir / 'PerceptionProcessing'}")
print(f"Exists: {(agent_a_dir / 'PerceptionProcessing').exists()}")

# Import with correct capitalization
try:
    from PerceptionProcessing.YoloDetector import YoloDetector  # Note: YoloDetector, not YOLODetector
    from PerceptionProcessing.Detection import Detection
    print("✓ Imports successful!")
except ImportError as e:
    print(f"❌ Import failed: {e}")
    print("\nContents of PerceptionProcessing:")
    pp_dir = agent_a_dir / "PerceptionProcessing"
    if pp_dir.exists():
        for item in pp_dir.iterdir():
            print(f"  - {item.name}")
    sys.exit(1)

import cv2

def test_basic_detection():
    """Test basic YOLO detection"""
    print("\n" + "="*80)
    print("  TEST: Basic Detection")
    print("="*80 + "\n")
    
    # Get paths
    app_dir = agent_a_dir.parent
    model_path = app_dir / "ComputerVision" / "CVModels" / "rf3v1.pt"
    image_path = app_dir / "ComputerVision" / "temp" / "drone_testing1.jpg"
    
    print(f"Model path: {model_path}")
    print(f"Model exists: {model_path.exists()}")
    print(f"Image path: {image_path}")
    print(f"Image exists: {image_path.exists()}")
    
    if not model_path.exists():
        print("\n❌ Model file not found!")
        return
    
    if not image_path.exists():
        print("\n❌ Image file not found!")
        return
    
    # Initialize detector (note: YoloDetector, not YOLODetector)
    print("\nInitializing YoloDetector...")
    detector = YoloDetector(
        model_path=str(model_path),
        confidence_threshold=0.5,
        device="cpu"
    )
    
    # Run detection
    print(f"\nRunning detection on: {image_path.name}")
    detections, annotated_img = detector.detect_from_path(
        str(image_path),
        return_annotated=True
    )
    
    # Print results
    print(f"\n✓ Found {len(detections)} object(s)")
    
    if len(detections) > 0:
        print("\nDetections:")
        print("-" * 80)
        for i, det in enumerate(detections, 1):
            print(f"\n{i}. {det.class_name}")
            print(f"   Confidence:    {det.confidence:.4f} ({det.confidence*100:.2f}%)")
            print(f"   BBox (pixels): {det.bbox_pixels}")
            print(f"   BBox (norm):   ({det.bbox_normalized[0]:.3f}, {det.bbox_normalized[1]:.3f}, "
                  f"{det.bbox_normalized[2]:.3f}, {det.bbox_normalized[3]:.3f})")
    
    # Save annotated image
    output_dir = agent_a_dir / "output"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "test_annotated.jpg"
    
    cv2.imwrite(str(output_path), annotated_img)
    print(f"\n✓ Saved annotated image to: {output_path}")
    
    return detections


def test_to_dict():
    """Test Detection.to_dict()"""
    print("\n" + "="*80)
    print("  TEST: to_dict() Method")
    print("="*80 + "\n")
    
    app_dir = agent_a_dir.parent
    model_path = app_dir / "ComputerVision" / "CVModels" / "rf3v1.pt"
    image_path = app_dir / "ComputerVision" / "temp" / "drone_testing1.jpg"
    
    detector = YoloDetector(
        model_path=str(model_path),
        confidence_threshold=0.5,
        device="cpu"
    )
    
    detections, _ = detector.detect_from_path(str(image_path), return_annotated=False)
    
    if len(detections) == 0:
        print("No detections found")
        return
    
    det = detections[0]
    print(f"Detection object: {det}")
    print("\nAs dictionary:")
    print("-" * 80)
    
    import json
    print(json.dumps(det.to_dict(), indent=2))


def test_enrichment():
    """Test Detection.enrich()"""
    print("\n" + "="*80)
    print("  TEST: Detection Enrichment")
    print("="*80 + "\n")
    
    app_dir = agent_a_dir.parent
    model_path = app_dir / "ComputerVision" / "CVModels" / "rf3v1.pt"
    image_path = app_dir / "ComputerVision" / "temp" / "drone_testing1.jpg"
    
    detector = YoloDetector(
        model_path=str(model_path),
        confidence_threshold=0.5,
        device="cpu"
    )
    
    detections, _ = detector.detect_from_path(str(image_path), return_annotated=False)
    
    if len(detections) == 0:
        print("No detections found")
        return
    
    det = detections[0]
    
    print("Before enrichment:")
    print(f"  drone_id: {det.drone_id}")
    print(f"  location: {det.location}")
    print(f"  caption:  {det.caption}")
    
    det.enrich(
        drone_id=42,
        location="28.6024,-81.2001",
        caption="Test caption from enrichment"
    )
    
    print("\nAfter enrichment:")
    print(f"  drone_id: {det.drone_id}")
    print(f"  location: {det.location}")
    print(f"  caption:  {det.caption}")


if __name__ == "__main__":
    print("\n" + "#"*80)
    print("#" + " "*24 + "YOLO DETECTOR TEST SUITE" + " "*32 + "#")
    print("#"*80)
    
    try:
        test_basic_detection()
        test_to_dict()
        test_enrichment()
        
        print("\n" + "="*80)
        print("  ALL TESTS COMPLETE ✓")
        print("="*80)
        print(f"\nOutputs saved to: {agent_a_dir / 'output'}")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()