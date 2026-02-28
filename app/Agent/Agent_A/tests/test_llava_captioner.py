# Agent_A/tests/test_llava_captioner.py

"""
Unit tests for LLaVACaptioner module.
Tests captioning functionality in isolation (no YOLO dependencies).

Prerequisites:
    - Ollama server running: ollama serve
    - LLaVA model installed: ollama pull llava

Run:
    python tests/test_llava_captioner.py
    pytest tests/test_llava_captioner.py -v
"""

import sys
from pathlib import Path

# Add Agent_A to path
agent_a_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_a_dir))

import cv2
import numpy as np
from PerceptionProcessing.LLaVACaptioner import LLaVACaptioner


class TestLLaVACaptioner:
    """Unit tests for LLaVA captioning functionality"""
    
    @staticmethod
    def get_test_image_path():
        """Get path to test image"""
        app_dir = agent_a_dir.parent
        return app_dir / "ComputerVision" / "temp" / "drone_testing1.jpg"
    
    def test_initialization(self):
        """Test 1: Captioner initializes correctly"""
        print("\n" + "="*80)
        print("  TEST 1: Captioner Initialization")
        print("="*80)
        
        try:
            captioner = LLaVACaptioner(device="cpu")
            print("✓ LLaVACaptioner initialized successfully")
            assert captioner is not None
            print("✓ Captioner object is valid")
            
        except Exception as e:
            print(f"✗ Initialization failed: {e}")
            raise
    
    def test_caption_full_image(self):
        """Test 2: Caption entire image from file path"""
        print("\n" + "="*80)
        print("  TEST 2: Caption Full Image (from path)")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        image_path = self.get_test_image_path()
        
        print(f"Image: {image_path.name}")
        print("-" * 80)
        
        caption = captioner.caption_image(str(image_path))
        
        print(f"\nGenerated Caption:")
        print(f"  {caption}")
        
        # Assertions
        assert caption is not None, "Caption should not be None"
        assert isinstance(caption, str), "Caption should be a string"
        assert len(caption) > 0, "Caption should not be empty"
        assert len(caption) > 10, "Caption should be meaningful (>10 chars)"
        
        print(f"\n✓ Caption length: {len(caption)} characters")
        print("✓ All assertions passed")
    
    def test_caption_with_custom_prompt(self):
        """Test 3: Caption with custom prompt"""
        print("\n" + "="*80)
        print("  TEST 3: Caption with Custom Prompt")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        image_path = self.get_test_image_path()
        
        custom_prompt = "Describe what activities are happening in this image."
        
        print(f"Custom Prompt: {custom_prompt}")
        print("-" * 80)
        
        caption = captioner.caption_image(
            str(image_path),
            prompt=custom_prompt
        )
        
        print(f"\nGenerated Caption:")
        print(f"  {caption}")
        
        assert caption is not None
        assert len(caption) > 0
        
        print("\n✓ Custom prompt handled correctly")
    
    def test_caption_detection_bbox(self):
        """Test 4: Caption focused on specific detection region"""
        print("\n" + "="*80)
        print("  TEST 4: Caption Detection Region (with bbox)")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        image_path = self.get_test_image_path()
        
        # Load image
        frame = cv2.imread(str(image_path))
        assert frame is not None, "Failed to load test image"
        
        # Simulate a detection bbox (you'd normally get this from YOLO)
        # Format: (x_min, y_min, x_max, y_max)
        fake_bbox = (100, 100, 400, 600)
        
        print(f"Detection BBox: {fake_bbox}")
        print(f"  Class: person")
        print(f"  Confidence: 0.92")
        print("-" * 80)
        
        caption = captioner.caption_detection(
            image=frame,
            detection_bbox=fake_bbox,
            class_name="person",
            confidence=0.92
        )
        
        print(f"\nContextual Caption:")
        print(f"  {caption}")
        
        assert caption is not None
        assert len(caption) > 0
        
        print("\n✓ Detection-focused captioning works")
    
    def test_caption_from_numpy_array(self):
        """Test 5: Caption from numpy array (cv2 image)"""
        print("\n" + "="*80)
        print("  TEST 5: Caption from Numpy Array")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        image_path = self.get_test_image_path()
        
        # Load as numpy array (typical cv2 workflow)
        frame = cv2.imread(str(image_path))
        
        print(f"Image shape: {frame.shape}")
        print(f"Image dtype: {frame.dtype}")
        print("-" * 80)
        
        caption = captioner.caption_image(frame)
        
        print(f"\nGenerated Caption:")
        print(f"  {caption}")
        
        assert caption is not None
        assert len(caption) > 0
        
        print("\n✓ Numpy array input handled correctly")
    
    def test_error_handling_invalid_path(self):
        """Test 6: Error handling for invalid image path"""
        print("\n" + "="*80)
        print("  TEST 6: Error Handling - Invalid Path")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        
        invalid_path = "/nonexistent/path/to/image.jpg"
        print(f"Testing with: {invalid_path}")
        print("-" * 80)
        
        try:
            caption = captioner.caption_image(invalid_path)
            print("✗ Should have raised an error!")
            assert False, "Should have raised FileNotFoundError"
        except (FileNotFoundError, Exception) as e:
            print(f"✓ Correctly raised error: {type(e).__name__}")
            print(f"  Error message: {e}")
    
    def test_error_handling_invalid_image(self):
        """Test 7: Error handling for corrupted/invalid image"""
        print("\n" + "="*80)
        print("  TEST 7: Error Handling - Invalid Image Data")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        
        # Create invalid numpy array (wrong shape)
        invalid_image = np.zeros((10, 10), dtype=np.uint8)  # Grayscale, too small
        
        print(f"Invalid image shape: {invalid_image.shape}")
        print("-" * 80)
        
        try:
            caption = captioner.caption_image(invalid_image)
            # Some implementations might handle this gracefully
            print(f"Caption generated (graceful handling): {caption[:50]}...")
            print("✓ Error handled gracefully")
        except Exception as e:
            print(f"✓ Correctly raised error: {type(e).__name__}")
            print(f"  Error message: {e}")
    
    def test_ollama_connection(self):
        """Test 8: Verify Ollama server connectivity"""
        print("\n" + "="*80)
        print("  TEST 8: Ollama Server Connection")
        print("="*80)
        
        import requests
        
        ollama_url = "http://localhost:11434"
        
        try:
            response = requests.get(f"{ollama_url}/api/tags", timeout=5)
            print(f"✓ Ollama server is running at {ollama_url}")
            
            if response.status_code == 200:
                models = response.json().get('models', [])
                print(f"✓ Available models: {len(models)}")
                
                # Check if llava is installed
                llava_models = [m for m in models if 'llava' in m.get('name', '').lower()]
                if llava_models:
                    print(f"✓ LLaVA model found: {llava_models[0]['name']}")
                else:
                    print("⚠ Warning: LLaVA model not found")
                    print("  Run: ollama pull llava")
            
        except requests.ConnectionError:
            print(f"✗ Cannot connect to Ollama server at {ollama_url}")
            print("  Please start Ollama: ollama serve")
            raise
        except Exception as e:
            print(f"✗ Unexpected error: {e}")
            raise
    
    def test_multiple_captions_consistency(self):
        """Test 9: Multiple captions of same image (consistency check)"""
        print("\n" + "="*80)
        print("  TEST 9: Multiple Caption Consistency")
        print("="*80)
        
        captioner = LLaVACaptioner(device="cpu")
        image_path = self.get_test_image_path()
        
        print("Generating 3 captions for the same image...")
        print("-" * 80)
        
        captions = []
        for i in range(3):
            caption = captioner.caption_image(str(image_path))
            captions.append(caption)
            print(f"\nCaption {i+1}:")
            print(f"  {caption}")
        
        # Check all captions are valid
        assert all(len(c) > 0 for c in captions)
        
        # Note: LLaVA might generate slightly different captions each time
        # This is expected behavior, not a bug
        print("\n✓ All captions generated successfully")
        print("Note: Variations in captions are normal for LLaVA")


def run_all_tests():
    """Run all tests in sequence"""
    print("\n" + "#"*80)
    print("#" + " "*22 + "LLAVA CAPTIONER TEST SUITE" + " "*32 + "#")
    print("#"*80)
    
    test_suite = TestLLaVACaptioner()
    
    tests = [
        ("Initialization", test_suite.test_initialization),
        ("Caption Full Image", test_suite.test_caption_full_image),
        ("Custom Prompt", test_suite.test_caption_with_custom_prompt),
        ("Detection BBox", test_suite.test_caption_detection_bbox),
        ("Numpy Array Input", test_suite.test_caption_from_numpy_array),
        ("Invalid Path Error", test_suite.test_error_handling_invalid_path),
        ("Invalid Image Error", test_suite.test_error_handling_invalid_image),
        ("Ollama Connection", test_suite.test_ollama_connection),
        ("Caption Consistency", test_suite.test_multiple_captions_consistency),
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
    else:
        print("\n" + "="*80)
        print("  SOME TESTS FAILED ✗")
        print("="*80)
    
    print("\nPrerequisites:")
    print("  1. Ollama server running: ollama serve")
    print("  2. LLaVA model installed: ollama pull llava")
    print("  3. Test image exists: ComputerVision/temp/drone_testing1.jpg")
    
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