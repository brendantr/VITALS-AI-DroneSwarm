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
        model_name: str = "llava-7b",
        device: str = "cpu",
        max_tokens: int = 50,  # REDUCED from 150 for shorter captions
        temperature: float = 0.7
    ):
        """
        Initialize LLaVA captioner
        Args:
            model_name: LLaVA model variant to use
            device: Device to run inference on ('cuda' or 'cpu')
            max_tokens: Maximum tokens in generated caption (reduced for brevity)
            temperature: Sampling temperature (higher = more creative)
        """
        self.model_name = model_name
        self.device = device
        self.max_tokens = max_tokens
        self.temperature = temperature
        
        print(f"Initializing LLaVA Captioner...")
        print(f"  Model: {model_name}")
        print(f"  Device: {device}")
        print(f"  Max tokens: {max_tokens} (2 sentence max)")
        
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
            context_margin: Margin around bbox to include context
            
        Returns:
            Pure caption (without metadata prefix) - prefix added by Detection object
        """
        # Expand bbox to include context
        expanded_bbox = self._expand_bbox(detection_bbox, context_margin)
        
        # SAR-focused prompt: short, factual, 2 sentences max
        prompt = self._build_sar_prompt(class_name)
        
        # Generate caption
        caption = self.caption_image(
            image=image,
            prompt=prompt,
            focus_bbox=expanded_bbox
        )
        
        # Return PURE caption (no metadata prefix)
        # The Detection object will add the prefix when needed
        return caption
    
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
    
    def _build_sar_prompt(self, class_name: str) -> str:
        """
        Build SAR-focused prompt for specific object class
        
        Optimized for:
        - Short output (2 sentences max)
        - Key SAR-relevant features only
        - No technical camera/image quality descriptions
        
        Args:
            class_name: Detected object class (person, vehicle, etc.)
            
        Returns:
            Optimized prompt string
        """
        # Class-specific SAR prompts
        if class_name.lower() == "person":
            return (
                "In 2 sentences or less: Describe the person's clothing color, "
                "position, and any visible actions or distress signals. "
                "Focus only on SAR-relevant details, no camera quality commentary."
            )
        
        elif class_name.lower() in ["vehicle", "car", "truck", "bus"]:
            return (
                "In 2 sentences or less: Describe the vehicle's color, type, "
                "orientation, and condition. "
                "Focus only on SAR-relevant details, no camera quality commentary."
            )
        
        elif class_name.lower() == "debris":
            return (
                "In 2 sentences or less: Describe the debris type, size, "
                "and any hazards it may pose. "
                "Focus only on SAR-relevant details, no camera quality commentary."
            )
        
        else:
            # Generic SAR prompt
            return (
                f"In 2 sentences or less: Describe this {class_name}'s appearance, "
                f"location, and any notable features for search and rescue. "
                f"Focus only on SAR-relevant details, no camera quality commentary."
            )
    
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
            margin: Expansion factor 
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
            Generated caption (cleaned and trimmed)
        """
        import requests
        import json
        
        # Convert image to base64
        buffered = io.BytesIO()
        image.save(buffered, format="PNG")
        img_base64 = base64.b64encode(buffered.getvalue()).decode()
        
        # Default prompt
        if prompt is None:
            prompt = (
                "In 2 sentences or less: Describe key objects, people, "
                "and environmental conditions relevant for drone search and rescue. "
                "Focus on colors, positions, and hazards only. "
                "Do not describe camera quality or image characteristics."
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
                "num_predict": self.max_tokens  # Limit output length
            }
        }
        
        try:
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            caption = result.get("response", "").strip()
            
            if not caption:
                print("Warning: Empty caption generated")
                caption = "No description available"
            
            # Clean up the caption
            caption = self._clean_caption(caption)
            
            return caption
            
        except requests.exceptions.ConnectionError:
            print("Error: Could not connect to Ollama. Is it running?")
            print("   Start Ollama with: ollama serve")
            return "Error: Ollama not available"
        
        except requests.exceptions.Timeout:
            print("Error: Caption generation timed out")
            return "Error: Caption timeout"
        
        except Exception as e:
            print(f"Error generating caption: {e}")
            return f"Error: {str(e)}"
    
    def _clean_caption(self, caption: str) -> str:
        """
        Clean and filter caption output
        
        Removes:
        - Camera quality commentary
        - Technical image descriptions
        - Unnecessary preambles
        
        Args:
            caption: Raw caption from LLaVA
            
        Returns:
            Cleaned caption
        """
        # Remove common unwanted phrases
        unwanted_phrases = [
            "the image appears to be",
            "this image shows",
            "the image is",
            "it appears to be",
            "the photo shows",
            "the picture shows",
            "captured with a",
            "taken with a",
            "smartphone",
            "low resolution",
            "high resolution",
            "the quality of",
            "image quality",
            "the camera",
            "camera flash",
            "visible in the image",
            "visible in the photo",
            "can be seen in"
        ]
        
        caption_lower = caption.lower()
        
        # Check if caption is mostly unwanted commentary
        unwanted_count = sum(1 for phrase in unwanted_phrases if phrase in caption_lower)
        
        if unwanted_count >= 3:
            # Caption is too focused on image quality, return generic
            return "Scene detected, details unclear."
        
        # Remove unwanted phrases
        for phrase in unwanted_phrases:
            # Case-insensitive replacement
            import re
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            caption = pattern.sub("", caption)
        
        # Clean up whitespace and capitalization
        caption = caption.strip()
        caption = " ".join(caption.split())  # Normalize whitespace
        
        # Ensure first letter is capitalized
        if caption:
            caption = caption[0].upper() + caption[1:]
        
        # Ensure it ends with punctuation
        if caption and caption[-1] not in ".!?":
            caption += "."
        
        # Limit to approximately 2 sentences
        sentences = caption.split('. ')
        if len(sentences) > 2:
            caption = '. '.join(sentences[:2]) + '.'
        
        return caption