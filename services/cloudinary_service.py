"""
Cloudinary Service for media upload and management.
Handles audio, image, and video uploads with user-based folder organization.
"""

import cloudinary
import cloudinary.uploader
import cloudinary.api
from cloudinary.exceptions import Error as CloudinaryError
from datetime import datetime, timedelta
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, List, Any
import os
import logging
import hashlib

logger = logging.getLogger(__name__)


class CloudinaryService:
    """Async wrapper for Cloudinary operations with user-based folder organization"""
    
    def __init__(self, max_workers: int = 3):
        """Initialize Cloudinary with config from environment"""
        # Configuration is auto-loaded from CLOUDINARY_URL env var
        cloudinary.config(
            secure=True,  # Always use HTTPS URLs
            api_proxy=os.getenv("HTTP_PROXY") if os.getenv("HTTP_PROXY") else None
        )
        
        # Thread pool for async operations
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        # Upload preset for consistent settings
        self.upload_preset = os.getenv("CLOUDINARY_UPLOAD_PRESET", "pixeltalk_media")
        
        # Base folder for organization
        self.base_folder = os.getenv("CLOUDINARY_BASE_FOLDER", "pixeltalk")
        
        logger.info(f"CloudinaryService initialized with base folder: {self.base_folder}")
    
    def _get_user_folder(self, session_id: str, user_id: Optional[str] = None) -> str:
        """
        Generate user-specific folder path.
        If user_id is provided, use it. Otherwise, derive from session_id.
        """
        if user_id:
            # Use actual user ID if provided
            user_folder = f"user_{user_id}"
        else:
            # Create a consistent user folder from session_id (first 8 chars)
            # This ensures all content from same "user session" goes to same folder
            user_hash = hashlib.md5(session_id.encode()).hexdigest()[:8]
            user_folder = f"user_{user_hash}"
        
        return user_folder
    
    async def _async_upload(self, file: Any, **options) -> Dict:
        """Execute Cloudinary upload in thread pool"""
        loop = asyncio.get_event_loop()
        
        # Add upload preset if configured and not 'none'
        if self.upload_preset and self.upload_preset != 'none' and "upload_preset" not in options:
            options["upload_preset"] = self.upload_preset
        
        # Auto-detect large files and use chunked upload
        if hasattr(file, 'size') and file.size > 20000000:
            upload_func = cloudinary.uploader.upload_large
        elif isinstance(file, bytes) and len(file) > 20000000:
            upload_func = cloudinary.uploader.upload_large
        else:
            upload_func = cloudinary.uploader.upload
        
        try:
            # Note: Cloudinary SDK expects dict params, not kwargs
            result = await loop.run_in_executor(
                self.executor,
                lambda: upload_func(file, **options)
            )
            return result
        except CloudinaryError as e:
            logger.error(f"Cloudinary upload failed: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected upload error: {e}")
            raise
    
    async def upload_audio(
        self,
        audio_bytes: bytes,
        session_id: str,
        user_id: Optional[str] = None,
        filename: str = "recording.wav"
    ) -> Dict:
        """Upload audio recording to Cloudinary in user-specific folder"""
        
        user_folder = self._get_user_folder(session_id, user_id)
        date_path = datetime.now().strftime("%Y/%m/%d")
        
        # Organize: base/users/user_xxx/audio/YYYY/MM/DD/session_xxx.wav
        folder_path = f"{self.base_folder}/users/{user_folder}/audio/{date_path}"
        # Don't include folder_path in public_id - Cloudinary combines them
        public_id = f"{session_id}_audio"
        
        logger.info(f"Uploading audio to: {public_id}")
        
        result = await self._async_upload(
            file=audio_bytes,
            public_id=public_id,
            resource_type="video",  # Audio uses video type in Cloudinary
            folder=folder_path,
            tags=[
                f"session_{session_id}",
                f"user_{user_folder}",
                "audio_recording",
                "pixeltalk",
                f"date_{datetime.now().strftime('%Y-%m-%d')}"
            ],
            context={
                "session_id": session_id,
                "user_folder": user_folder,
                "type": "audio_recording",
                "filename": filename,
                "created_at": datetime.now().isoformat()
            }
        )
        
        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "duration": result.get("duration", 0),
            "format": result["format"],
            "size": result.get("bytes", 0),
            "folder": folder_path
        }
    
    async def upload_image(
        self,
        image_bytes: bytes,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict:
        """Upload generated image with optimizations in user-specific folder"""
        
        if metadata is None:
            metadata = {}
        
        user_folder = self._get_user_folder(session_id, user_id)
        date_path = datetime.now().strftime("%Y/%m/%d")
        
        # Organize: base/users/user_xxx/images/YYYY/MM/DD/session_xxx.png
        folder_path = f"{self.base_folder}/users/{user_folder}/images/{date_path}"
        # Don't include folder_path in public_id - Cloudinary combines them
        public_id = f"{session_id}_image"
        
        logger.info(f"Uploading image to: {public_id}")
        
        result = await self._async_upload(
            file=image_bytes,
            public_id=public_id,
            resource_type="image",
            folder=folder_path,
            tags=[
                f"session_{session_id}",
                f"user_{user_folder}",
                "generated_image",
                "pixeltalk",
                f"date_{datetime.now().strftime('%Y-%m-%d')}"
            ],
            context={
                "session_id": session_id,
                "user_folder": user_folder,
                "title": str(metadata.get("title", ""))[:255],  # Cloudinary has limits
                "prompt": str(metadata.get("prompt", ""))[:255],
                "created_at": datetime.now().isoformat()
            },
            # Optimization parameters
            quality="auto:good",  # Automatic quality optimization
            fetch_format="auto",  # Auto-format selection (WebP, AVIF, etc.)
            flags="progressive",  # Progressive loading
            # Generate responsive versions
            eager=[
                {"width": 1920, "height": 1080, "crop": "fit", "quality": "auto:best"},  # Full HD
                {"width": 1280, "height": 720, "crop": "fit", "quality": "auto:good"},   # HD
                {"width": 640, "height": 360, "crop": "fit", "quality": "auto:eco"}      # Mobile
            ],
            eager_async=True  # Process transformations asynchronously
        )
        
        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "width": result.get("width"),
            "height": result.get("height"),
            "format": result["format"],
            "size": result.get("bytes", 0),
            "folder": folder_path,
            "eager": result.get("eager", [])  # URLs for different sizes
        }
    
    async def upload_video(
        self,
        video_bytes: bytes,
        session_id: str,
        user_id: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> Dict:
        """Upload generated video with processing in user-specific folder"""
        
        if metadata is None:
            metadata = {}
        
        user_folder = self._get_user_folder(session_id, user_id)
        date_path = datetime.now().strftime("%Y/%m/%d")
        
        # Organize: base/users/user_xxx/videos/YYYY/MM/DD/session_xxx.mp4
        folder_path = f"{self.base_folder}/users/{user_folder}/videos/{date_path}"
        # Don't include folder_path in public_id - Cloudinary combines them
        public_id = f"{session_id}_video"
        
        logger.info(f"Uploading video to: {public_id}")
        
        result = await self._async_upload(
            file=video_bytes,
            public_id=public_id,
            resource_type="video",
            folder=folder_path,
            tags=[
                f"session_{session_id}",
                f"user_{user_folder}",
                "generated_video",
                "pixeltalk",
                f"date_{datetime.now().strftime('%Y-%m-%d')}"
            ],
            context={
                "session_id": session_id,
                "user_folder": user_folder,
                "title": str(metadata.get("title", ""))[:255],
                "prompt": str(metadata.get("prompt", ""))[:255],
                "created_at": datetime.now().isoformat()
            },
            # Video optimization
            video_codec="auto",  # Automatic codec selection
            audio_codec="auto",
            # Generate multiple formats
            eager=[
                {"width": 1280, "height": 720, "video_codec": "h264", "format": "mp4"},  # HD MP4
                {"width": 640, "height": 360, "video_codec": "h264", "format": "mp4"},   # Mobile MP4
            ],
            eager_async=True
        )
        
        return {
            "url": result["secure_url"],
            "public_id": result["public_id"],
            "duration": result.get("duration", 0),
            "width": result.get("width"),
            "height": result.get("height"),
            "format": result["format"],
            "size": result.get("bytes", 0),
            "folder": folder_path,
            "thumbnail_url": self._get_video_thumbnail_url(result["public_id"]),
            "eager": result.get("eager", [])  # URLs for different formats
        }
    
    def _get_video_thumbnail_url(self, public_id: str) -> str:
        """Generate thumbnail URL for video"""
        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="video",
            format="jpg",
            transformation=[
                {"width": 1280, "height": 720, "crop": "fill", "page": 1}
            ]
        )
        return url
    
    async def get_user_resources(self, user_id: str, resource_type: str = "image") -> List[Dict]:
        """Get all resources for a specific user"""
        loop = asyncio.get_event_loop()
        user_folder = f"user_{user_id}" if not user_id.startswith("user_") else user_id
        
        try:
            result = await loop.run_in_executor(
                self.executor,
                lambda: cloudinary.api.resources_by_tag(
                    f"user_{user_folder}",
                    max_results=100,
                    resource_type=resource_type
                )
            )
            
            return result.get("resources", [])
            
        except CloudinaryError as e:
            logger.error(f"Failed to get resources for user {user_id}: {e}")
            return []
    
    async def get_session_resources(self, session_id: str) -> Dict:
        """Get all URLs for a session"""
        loop = asyncio.get_event_loop()
        
        try:
            # Search for all resources with this session_id tag
            video_result = await loop.run_in_executor(
                self.executor,
                lambda: cloudinary.api.resources_by_tag(
                    f"session_{session_id}",
                    max_results=10,
                    resource_type="video"  # Includes audio
                )
            )
            
            image_result = await loop.run_in_executor(
                self.executor,
                lambda: cloudinary.api.resources_by_tag(
                    f"session_{session_id}",
                    max_results=10,
                    resource_type="image"
                )
            )
            
            resources = {}
            
            # Process video/audio resources
            for resource in video_result.get("resources", []):
                if "audio_recording" in resource.get("tags", []):
                    resources["audio"] = {
                        "url": resource["secure_url"],
                        "duration": resource.get("duration", 0),
                        "size": resource.get("bytes", 0)
                    }
                elif "generated_video" in resource.get("tags", []):
                    resources["video"] = {
                        "url": resource["secure_url"],
                        "duration": resource.get("duration", 0),
                        "size": resource.get("bytes", 0),
                        "thumbnail_url": self._get_video_thumbnail_url(resource["public_id"])
                    }
            
            # Process image resources
            for resource in image_result.get("resources", []):
                if "generated_image" in resource.get("tags", []):
                    resources["image"] = {
                        "url": resource["secure_url"],
                        "width": resource.get("width"),
                        "height": resource.get("height"),
                        "size": resource.get("bytes", 0)
                    }
            
            return resources
            
        except CloudinaryError as e:
            logger.error(f"Failed to get resources for session {session_id}: {e}")
            return {}
    
    async def delete_session_resources(self, session_id: str) -> bool:
        """Delete all resources for a session"""
        loop = asyncio.get_event_loop()
        
        try:
            # Delete by tag (most efficient method)
            result = await loop.run_in_executor(
                self.executor,
                lambda: cloudinary.api.delete_resources_by_tag(f"session_{session_id}")
            )
            
            deleted_count = len(result.get("deleted", {}))
            logger.info(f"Deleted {deleted_count} resources for session {session_id}")
            return deleted_count > 0
            
        except CloudinaryError as e:
            logger.error(f"Failed to delete resources for session {session_id}: {e}")
            return False
    
    async def cleanup_old_resources(self, days: int = 30) -> Dict:
        """Delete resources older than specified days"""
        loop = asyncio.get_event_loop()
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        
        try:
            # Search for old resources
            result = await loop.run_in_executor(
                self.executor,
                lambda: cloudinary.api.resources(
                    type="upload",
                    prefix=self.base_folder,
                    max_results=500,
                    tags=True
                )
            )
            
            old_resources = []
            for resource in result.get("resources", []):
                created_at = resource.get("created_at", "")
                if created_at and created_at < cutoff_date:
                    old_resources.append(resource["public_id"])
            
            if old_resources:
                # Delete in batches of 100
                deleted_count = 0
                for i in range(0, len(old_resources), 100):
                    batch = old_resources[i:i+100]
                    delete_result = await loop.run_in_executor(
                        self.executor,
                        lambda b=batch: cloudinary.api.delete_resources(b)
                    )
                    deleted_count += len(delete_result.get("deleted", {}))
                
                logger.info(f"Cleanup: Deleted {deleted_count} resources older than {days} days")
                return {
                    "deleted_count": deleted_count,
                    "message": f"Deleted {deleted_count} resources older than {days} days"
                }
            
            return {"deleted_count": 0, "message": "No old resources found"}
            
        except CloudinaryError as e:
            logger.error(f"Cleanup failed: {e}")
            return {"error": str(e)}
    
    def __del__(self):
        """Cleanup thread pool on deletion"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)