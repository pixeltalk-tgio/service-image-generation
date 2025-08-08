"""
Video Prompt Generator using OpenAI Structured Outputs
Generates structured prompts for Google Veo 3 video generation
"""

import json
import logging
from typing import Dict, Any, List
from pydantic import BaseModel, Field
from openai import OpenAI
import asyncio

logger = logging.getLogger(__name__)


class VideoPrompt(BaseModel):
    """Structured schema for video generation prompts"""
    
    description: str = Field(
        description="Detailed narrative of the video sequence (100-200 words)"
    )
    style: str = Field(
        description="Visual style keywords (e.g., 'cinematic, dynamic, magical futurism')"
    )
    camera: str = Field(
        description="Camera movements and perspectives throughout the video"
    )
    lighting: str = Field(
        description="Lighting conditions and transitions"
    )
    environment: str = Field(
        description="Setting and environmental changes"
    )
    elements: List[str] = Field(
        description="List of 8-12 specific visual elements and actions",
        min_length=8,
        max_length=12
    )
    motion: str = Field(
        description="Movement dynamics and timing"
    )
    ending: str = Field(
        description="Final frame composition"
    )
    text: str = Field(
        description="Text overlay specification or 'none'",
        default="none"
    )
    keywords: List[str] = Field(
        description="5-10 key visual concepts",
        min_length=5,
        max_length=10
    )


class VideoPromptGenerator:
    """Generates structured video prompts from audio summaries"""
    
    def __init__(self, openai_client: OpenAI):
        """Initialize with OpenAI client
        
        Args:
            openai_client: Initialized OpenAI client
        """
        self.client = openai_client
        self.model = "gpt-4o-2024-08-06"  # Model with 100% structured output reliability
        
        # System prompt for video generation
        self.system_prompt = """You are a cinematic video prompt engineer for Google Veo 3. 
        Transform audio summaries into detailed, cinematic video generation prompts.
        
        You create immersive, dynamic video narratives that capture the essence of the audio content.
        
        Guidelines for each field:
        - description: Create a detailed narrative that unfolds over 8 seconds. Include specific visual sequences, transitions, and key moments. Be cinematic and engaging.
        - style: Use 3-5 style keywords that define the overall aesthetic (e.g., "cinematic, ethereal, hyperrealistic")
        - camera: Describe camera movements from start to finish (e.g., "starts with close-up, slowly pulls back to reveal wide landscape")
        - lighting: Describe the lighting mood and any changes (e.g., "golden hour transitioning to blue twilight")
        - environment: Describe the setting and how it evolves during the video
        - elements: List 8-12 specific visual elements that appear in the video, be very detailed
        - motion: Describe the pace and rhythm of movement in the scene
        - ending: Describe the final frame that viewers will remember
        - text: Usually "none" unless the content specifically requires text overlay
        - keywords: 5-10 keywords that capture the essence of the video
        
        Create videos that are visually striking, emotionally resonant, and perfectly matched to the audio content's mood and message."""
    
    async def generate_video_prompt(
        self,
        summary: str,
        image_prompt: str,
        transcript: str = None
    ) -> Dict[str, Any]:
        """Generate structured video prompt from audio summary
        
        Args:
            summary: Summary of the audio content
            image_prompt: Related image generation prompt for context
            transcript: Optional full transcript for additional context
        
        Returns:
            Dict containing structured video prompt
        """
        # Build user prompt
        user_prompt_parts = [
            "Create a cinematic 8-second video prompt based on this content:",
            f"\nAudio Summary: {summary}"
        ]
        
        if image_prompt:
            user_prompt_parts.append(f"\nRelated Visual Concept: {image_prompt}")
        
        if transcript:
            # Include first 200 chars of transcript for context
            user_prompt_parts.append(f"\nTranscript excerpt: {transcript[:200]}...")
        
        user_prompt_parts.append(
            "\nTransform this into an engaging, cinematic video narrative with rich visual details. "
            "The video should capture the emotional essence and key themes of the audio."
        )
        
        user_prompt = "\n".join(user_prompt_parts)
        
        try:
            # Use structured output with Pydantic model
            logger.info("Generating structured video prompt...")
            
            completion = await asyncio.to_thread(
                self.client.beta.chat.completions.parse,
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format=VideoPrompt,
                temperature=0.8,  # Some creativity for video prompts
                max_tokens=1500
            )
            
            # Extract the parsed response
            video_prompt = completion.choices[0].message.parsed
            
            # Convert to dict
            prompt_dict = video_prompt.model_dump()
            
            logger.info(f"Generated video prompt with {len(prompt_dict['elements'])} elements")
            
            return prompt_dict
            
        except Exception as e:
            logger.error(f"Failed to generate video prompt: {e}")
            # Re-raise the exception to be handled by the caller
            raise
    
    def format_for_veo(self, structured_prompt: Dict[str, Any]) -> str:
        """Convert structured prompt to optimized Veo text prompt
        
        Args:
            structured_prompt: Structured prompt dict
        
        Returns:
            Optimized text prompt for Veo
        """
        # Format into cohesive narrative for Veo
        prompt_parts = []
        
        # Lead with description
        prompt_parts.append(structured_prompt['description'])
        
        # Add style directive
        prompt_parts.append(f"Visual style: {structured_prompt['style']}.")
        
        # Add camera movement
        prompt_parts.append(f"Camera: {structured_prompt['camera']}.")
        
        # Add lighting
        prompt_parts.append(f"Lighting: {structured_prompt['lighting']}.")
        
        # Add environment if different from description
        if structured_prompt['environment']:
            prompt_parts.append(f"Setting: {structured_prompt['environment']}.")
        
        # Add key elements as natural language
        if structured_prompt['elements']:
            elements_text = "The scene includes " + ", ".join(structured_prompt['elements'][:5])
            if len(structured_prompt['elements']) > 5:
                elements_text += f", and {len(structured_prompt['elements']) - 5} more detailed elements"
            prompt_parts.append(elements_text + ".")
        
        # Add motion description
        prompt_parts.append(f"Motion: {structured_prompt['motion']}.")
        
        # Add ending
        prompt_parts.append(f"The video ends with {structured_prompt['ending']}.")
        
        # Add keywords for emphasis
        if structured_prompt['keywords']:
            prompt_parts.append("Keywords: " + ", ".join(structured_prompt['keywords']) + ".")
        
        # Specify no text if needed
        if structured_prompt.get('text', 'none').lower() == 'none':
            prompt_parts.append("No text overlays.")
        
        return " ".join(prompt_parts)