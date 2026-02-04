def detect(image_path: str):
    # Test to make sure the YOLO backend is working
    return [
        {
            "label": "test_object",
            "confidence": 0.99,
            "bounding_box": [50, 50, 150, 150],
        }
    ]