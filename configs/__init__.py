"""
Configuration module for PixelTalk Audio-to-Art Service.

This module provides configuration utilities and client initialization
for various external services used by the application.

Modules:
    client_openai: OpenAI client initialization and configuration
    client_veo: Google Vertex AI Veo client for video generation
"""

from .client_openai import initialize_openai_client
from .client_veo import VeoClient

__all__ = [
    'initialize_openai_client',
    'VeoClient',
]