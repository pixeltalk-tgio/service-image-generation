"""
Google Veo 3 Video Generation Client
Handles video generation using Google's Vertex AI Veo API
"""

import os
import json
import asyncio
import logging
import base64
from typing import Optional, Dict, Any
from datetime import datetime
import aiohttp

from google.oauth2 import service_account
from google.auth.transport.requests import Request
import google.auth

logger = logging.getLogger(__name__)


class VeoClient:
    """Client for Google Veo 3 video generation"""
    
    def __init__(self, project_id: Optional[str] = None):
        """Initialize Veo client with Google Cloud credentials
        
        Args:
            project_id: Google Cloud project ID. If not provided, uses environment variable
        """
        self.project_id = project_id or os.getenv('GCP_PROJECT_ID')
        if not self.project_id:
            raise ValueError("GCP_PROJECT_ID must be set in environment or passed as parameter")
        
        self.location = os.getenv('VEO_LOCATION', 'us-central1')
        self.model_id = os.getenv('VEO_MODEL_ID', 'veo-3.0-generate-preview')  # Default to Veo 3.0 preview
        self.publisher = 'google'
        
        # Build endpoint URL - using predictLongRunning for video generation
        self.endpoint = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/{self.publisher}/models/{self.model_id}:predictLongRunning"
        )
        
        # Initialize credentials
        self._init_credentials()
        
        logger.info(f"VeoClient initialized for project: {self.project_id}")
    
    def _init_credentials(self):
        """Initialize Google Cloud credentials"""
        # Try to load credentials from service account file if provided
        service_account_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        
        if service_account_path and os.path.exists(service_account_path):
            self.credentials = service_account.Credentials.from_service_account_file(
                service_account_path,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            logger.info("Using service account credentials")
        else:
            # Fall back to default credentials (gcloud auth, etc.)
            self.credentials, _ = google.auth.default(
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            logger.info("Using default application credentials")
    
    def _get_auth_token(self) -> str:
        """Get fresh authentication token"""
        # Always refresh the token to ensure it's valid
        if not self.credentials.valid:
            self.credentials.refresh(Request())
        
        return self.credentials.token
    
    async def generate_video(
        self,
        prompt: str,
        aspect_ratio: str = "16:9",
        resolution: str = "720p",
        duration_seconds: int = 8,
        person_generation: str = "allow",
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        storage_uri: Optional[str] = None,
        sample_count: int = 1
    ) -> Dict[str, Any]:
        """Generate video from text prompt
        
        Args:
            prompt: Text prompt for video generation
            aspect_ratio: "16:9" (landscape) or "9:16" (portrait)
            resolution: "720p" or "1080p" (Veo 3 only)
            duration_seconds: Video length in seconds (5-8 for veo-2.0, default 8)
            person_generation: "allow" or "disallow"
            negative_prompt: Text to discourage from generating
            seed: Random seed for deterministic generation (0-4294967295)
            storage_uri: GCS URI to store output (optional)
            sample_count: Number of videos to generate (1-4)
        
        Returns:
            Dict containing operation name and initial response
        """
        # Build request body
        request_body = {
            "instances": [
                {
                    "prompt": prompt
                }
            ],
            "parameters": {
                "sampleCount": sample_count,
                "aspectRatio": aspect_ratio,
                "resolution": resolution,
                "durationSeconds": duration_seconds,
                "personGeneration": person_generation
            }
        }
        
        # Add optional parameters
        if negative_prompt:
            request_body["parameters"]["negativePrompt"] = negative_prompt
        if seed is not None:
            request_body["parameters"]["seed"] = seed
        if storage_uri:
            request_body["parameters"]["storageUri"] = storage_uri
        
        # Make API request
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self._get_auth_token()}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            logger.info(f"Submitting video generation request for prompt: {prompt[:100]}...")
            
            async with session.post(
                self.endpoint,
                headers=headers,
                json=request_body
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Veo API error: {response.status} - {error_text}")
                    raise Exception(f"Veo API error: {response.status} - {error_text}")
                
                result = await response.json()
                
                logger.info(f"Video generation job submitted: {result.get('name')}")
                
                return result
    
    async def get_operation_status(self, operation_name: str) -> Dict[str, Any]:
        """Check status of a long-running operation using fetchPredictOperation
        
        Args:
            operation_name: The full operation name returned from generate_video
        
        Returns:
            Dict containing operation status and results if complete
        """
        # Build the fetchPredictOperation endpoint URL
        fetch_url = (
            f"https://{self.location}-aiplatform.googleapis.com/v1/"
            f"projects/{self.project_id}/locations/{self.location}/"
            f"publishers/{self.publisher}/models/{self.model_id}:fetchPredictOperation"
        )
        
        # Request body with the operation name
        request_body = {
            "operationName": operation_name
        }
        
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self._get_auth_token()}",
                "Content-Type": "application/json; charset=utf-8"
            }
            
            async with session.post(fetch_url, headers=headers, json=request_body) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Operation status error: {response.status} - {error_text}")
                    raise Exception(f"Operation status error: {response.status} - {error_text}")
                
                return await response.json()
    
    async def wait_for_video(
        self,
        operation_name: str,
        timeout_seconds: int = 120,
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Wait for video generation to complete
        
        NOTE: Operation status checking currently has limitations with Veo API.
        This method will attempt to check status but may fail due to API constraints.
        
        Args:
            operation_name: The operation name from generate_video
            timeout_seconds: Maximum time to wait
            poll_interval: Seconds between status checks
        
        Returns:
            Dict containing video URLs or operation info
        """
        try:
            start_time = asyncio.get_event_loop().time()
            
            while asyncio.get_event_loop().time() - start_time < timeout_seconds:
                try:
                    status = await self.get_operation_status(operation_name)
                    
                    if status.get("done"):
                        if "error" in status:
                            logger.error(f"Video generation failed: {status['error']}")
                            raise Exception(f"Video generation failed: {status['error']}")
                        
                        # Extract video data from response based on Veo API format
                        response_data = status.get("response", {})
                        videos = response_data.get("videos", [])
                        
                        if videos:
                            logger.info(f"Video generation completed successfully")
                            # Return the first video
                            first_video = videos[0]
                            # Check if we have GCS URI or base64 data
                            if "gcsUri" in first_video:
                                return {
                                    "videoUri": first_video["gcsUri"],
                                    "mimeType": first_video.get("mimeType", "video/mp4"),
                                    "status": "completed"
                                }
                            elif "bytesBase64Encoded" in first_video:
                                return {
                                    "videoBase64": first_video["bytesBase64Encoded"],
                                    "mimeType": first_video.get("mimeType", "video/mp4"),
                                    "status": "completed"
                                }
                        else:
                            logger.warning("No videos in response")
                            return response_data
                    
                    # Still processing
                    logger.info(f"Video generation in progress...")
                    
                except Exception as e:
                    logger.error(f"Error checking operation status: {e}")
                    # Don't fail completely, just log and continue
                    pass
                
                await asyncio.sleep(poll_interval)
            
            # Timeout reached
            logger.warning(f"Video generation status check timed out after {timeout_seconds} seconds")
            return {
                "status": "timeout",
                "operation_id": operation_name,
                "message": "Unable to check status. Video may still be processing.",
                "videoUri": None
            }
            
        except Exception as e:
            logger.error(f"Error waiting for video: {e}")
            # Return operation info even on error
            return {
                "status": "error",
                "operation_id": operation_name,
                "message": str(e),
                "videoUri": None
            }
    
