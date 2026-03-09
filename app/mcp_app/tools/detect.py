from backends.yolo import detect

def detect_objects(image_path: str):
    objects = detect(image_path)
    return {"objects": objects}