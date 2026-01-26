import torch
import numpy as np
from pathlib import Path
from typing import Optional, Union, List
from PIL import Image
import io
import base64

class LLaVACaptioner:
    """
    LLaVA-based image captioning for Agent A
    
    Generates natural language descriptions of detected objects/scenes
    to provide semantic context beyond pure object detection.
    """
    
    def __init__(
        self,
        model_name: str = "llava-v1.5-7b",
        device: str = "cpu",
        max_tokens: int = 150,
        temperature: float = 0.7
    ):
        """
        Initialize LLaVA captioner
        
        Args:
            model_name: LLaVA model variant to use
            device: Device to run inference on ('cuda' or 'cpu')
            max_tokens: Maximum tokens in generated caption
            temperature: Sampling temperature (higher = more creative)
        """
        self.model_name = model_name
        self.device = device
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        print(f"Initializing LLaVA Captioner...")
        print(f"  Model: {model_name}")
        print(f"  Device: {device}")
        
        # Model will be loaded via Ollama API
        self.model_loaded = True
        
        print("LLaVA Captioner initialized (using Ollama API)")
    
    def caption_image(
        self,
        image: Union[str, np.ndarray, Image.Image],
        prompt: Optional[str] = None,
        focus_bbox: Optional[tuple] = None
    ) -> str:
        """
        Generate caption for an image
        
        Args:
            image: Image as file path, numpy array (BGR), or PIL Image
            prompt: Optional custom prompt (default: general description)
            focus_bbox: Optional (x_min, y_min, x_max, y_max) to crop/focus
        
        Returns:
            Generated caption string
        """
        # Load/convert image to PIL
        pil_image = self._prepare_image(image)
        
        # Crop to focus area if specified
        if focus_bbox is not None:
            pil_image = self._crop_to_bbox(pil_image, focus_bbox)
        
        # Generate caption using Ollama API
        caption = self._generate_caption_ollama(pil_image, prompt)
        
        return caption
    
    def caption_detection(
        self,
        image: Union[str, np.ndarray],
        detection_bbox: tuple,
        class_name: str,
        confidence: float,
        context_margin: float = 0.2
    ) -> str:
        """
        Generate contextual caption for a specific detection
        
        Args:
            image: Full image
            detection_bbox: (x_min, y_min, x_max, y_max) in pixels
            class_name: Detected object class
            confidence: Detection confidence
            context_margin: Margin around bbox to include context (0.2 = 20%)
        
        Returns:
            Detailed caption describing the detection and context
        """
        # Expand bbox to include context
        expanded_bbox = self._expand_bbox(detection_bbox, context_margin)
        
        # Create focused prompt
        prompt = (
            f"Describe what you see in this image, focusing on the {class_name}. "
            f"Include details about the {class_name}'s appearance, condition, "
            f"position, and surrounding environment. Be specific and factual."
        )
        
        caption = self.caption_image(
            image=image,
            prompt=prompt,
            focus_bbox=expanded_bbox
        )
        
        # Add metadata prefix
        full_caption = f"{class_name} (conf: {confidence:.2f}): {caption}"
        
        return full_caption
    
    def batch_caption(
        self,
        images: List[Union[str, np.ndarray]],
        prompt: Optional[str] = None
    ) -> List[str]:
        """
        Generate captions for multiple images
        
        Args:
            images: List of images
            prompt: Optional custom prompt for all images
        
        Returns:
            List of generated captions
        """
        captions = []
        
        for i, image in enumerate(images):
            print(f"Captioning image {i+1}/{len(images)}...")
            caption = self.caption_image(image, prompt)
            captions.append(caption)
        
        return captions
    
    def _prepare_image(
        self,
        image: Union[str, np.ndarray, Image.Image]
    ) -> Image.Image:
        """
        Convert various image formats to PIL Image
        
        Args:
            image: Image in various formats
        
        Returns:
            PIL Image object
        """
        if isinstance(image, str):
            # Load from file path
            return Image.open(image).convert('RGB')
        
        elif isinstance(image, np.ndarray):
            # Convert numpy array to PIL RGB
            if len(image.shape) == 3 and image.shape[2] == 3:
                # Convert BGR to RGB
                image_rgb = image[:, :, ::-1]
            else:
                image_rgb = image
            return Image.fromarray(image_rgb)
        
        elif isinstance(image, Image.Image):
            return image.convert('RGB')
        
        else:
            raise TypeError(f"Unsupported image type: {type(image)}")
    
    def _crop_to_bbox(
        self,
        image: Image.Image,
        bbox: tuple
    ) -> Image.Image:
        """
        Crop image to bounding box
        
        Args:
            image: PIL Image
            bbox: (x_min, y_min, x_max, y_max) in pixels
        
        Returns:
            Cropped PIL Image
        """
        x_min, y_min, x_max, y_max = bbox
        
        # Clamp to image bounds
        x_min = max(0, int(x_min))
        y_min = max(0, int(y_min))
        x_max = min(image.width, int(x_max))
        y_max = min(image.height, int(y_max))
        
        return image.crop((x_min, y_min, x_max, y_max))
    
    def _expand_bbox(
        self,
        bbox: tuple,
        margin: float
    ) -> tuple:
        """
        Expand bounding box by margin percentage
        
        Args:
            bbox: (x_min, y_min, x_max, y_max)
            margin: Expansion factor (0.2 = 20% larger)
        
        Returns:
            Expanded bounding box
        """
        x_min, y_min, x_max, y_max = bbox
        
        width = x_max - x_min
        height = y_max - y_min
        
        x_margin = width * margin / 2
        y_margin = height * margin / 2
        
        return (
            x_min - x_margin,
            y_min - y_margin,
            x_max + x_margin,
            y_max + y_margin
        )
    
    def _generate_caption_ollama(
        self,
        image: Image.Image,
        prompt: Optional[str] = None
    ) -> str:
        """
        Generate caption using Ollama API
        
        Args:
            image: PIL Image
            prompt: Optional custom prompt
        
        Returns:
            Generated caption
        """
        import requests
        import json
        
        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Default prompt for SAR context
        if prompt is None:
            prompt = (
                "Describe this image in detail. Focus on identifying people, "
                "objects, and environmental conditions that would be relevant "
                "for search and rescue operations. Be specific about colors, "
                "positions, and any visible distress signals."
            )
        
        # Prepare Ollama API request
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llava",  # Use the LLaVA model in Ollama
            "prompt": prompt,
            "images": [img_base64],
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            caption = result.get("response", "").strip()
            
            if not caption:
                print("⚠ Warning: Empty caption generated")
                caption = "No description available"
            
            return caption
            
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to Ollama. Is it running?")
            print("Start Ollama with: ollama serve")
            return "Error: Ollama not available"
        
        except requests.exceptions.Timeout:
            print("Error: Caption generation timed out")
            return "Error: Caption timeout"
        
        except Exception as e:
            print(f"Error generating caption: {e}")
            return f"Error: {str(e)}"