"""
Simple queue-based audio processor
Handles audio workflow with async workers
"""

import asyncio
import logging
import os
import time
import traceback
from typing import Dict, Any
from datetime import datetime
import tempfile
import base64

from database import db
from configs.client_openai import initialize_openai_client
from services.video_prompt import VideoPromptGenerator
from configs.client_veo import VeoClient
from services.cloudinary_service import CloudinaryService

# Configure structured logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Initialize OpenAI client
openai_client = initialize_openai_client()

# Initialize video-related clients (lazy initialization)
video_prompt_generator = None
veo_client = None

# Initialize Cloudinary service (if enabled)
cloudinary_service = None
if os.getenv('USE_CLOUDINARY', 'false').lower() == 'true':
    try:
        cloudinary_service = CloudinaryService()
        logger.info("Cloudinary service initialized")
    except Exception as e:
        logger.warning(f"Cloudinary initialization failed, using local storage: {e}")
        cloudinary_service = None


class AudioProcessor:
    """Simple async queue processor for audio workflows"""
    
    def __init__(self):
        self.queue = asyncio.Queue()
        self.worker_task = None
        
    async def start(self):
        """Start the worker"""
        self.worker_task = asyncio.create_task(self._worker())
        logger.info("Audio processor started")
    
    async def stop(self):
        """Stop the worker"""
        if self.worker_task:
            self.worker_task.cancel()
            try:
                await self.worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Audio processor stopped")
    
    async def process_audio(self, session_id: str, audio_file, generation_mode: str = "image"):
        """Add audio to processing queue
        
        Args:
            session_id: Unique session identifier
            audio_file: Audio file to process
            generation_mode: "image", "video", or "both" (default: "image")
        """
        # Read the file content before queuing (to avoid closed file issues)
        audio_content = await audio_file.read()
        await self.queue.put({
            'session_id': session_id,
            'audio_content': audio_content,
            'filename': audio_file.filename,
            'generation_mode': generation_mode,
            'timestamp': datetime.now()
        })
        logger.info(f"Queued audio for session {session_id} with mode: {generation_mode}")
    
    async def _worker(self):
        """Main worker that processes audio from queue"""
        while True:
            try:
                # Get task from queue
                task = await self.queue.get()
                session_id = task['session_id']
                audio_content = task['audio_content']
                filename = task['filename']
                generation_mode = task.get('generation_mode', 'image')
                
                logger.info(f"Processing {session_id} with mode: {generation_mode}")
                
                # Process the audio through all stages
                await self._process_task(session_id, audio_content, filename, generation_mode)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await db.update_status(session_id, "failed", {"error": str(e)})
    
    async def _process_task(self, session_id: str, audio_content: bytes, filename: str, generation_mode: str = "image"):
        """Process a single audio task through all stages
        
        Args:
            session_id: Unique session identifier
            audio_content: Raw audio file bytes
            filename: Original filename
            generation_mode: "image", "video", or "both"
        """
        current_stage = "initialization"
        process_start = time.time()
        stage_timings = {}
        
        # Extract user_id from session if available (you can modify this based on your session structure)
        # For now, we'll use None and let Cloudinary derive it from session_id
        user_id = None
        
        try:
            # Log start of processing
            logger.info(f"Starting audio processing for session {session_id}: {filename} ({len(audio_content)} bytes)")
            
            # Stage 1: Transcribe
            current_stage = "transcription"
            stage_start = time.time()
            await db.update_status(session_id, "transcribing")
            
            transcript = await self._transcribe(audio_content, filename)
            stage_timings['transcription_ms'] = (time.time() - stage_start) * 1000
            
            logger.info(f"Transcription completed for {session_id} - {stage_timings['transcription_ms']:.2f}ms, {len(transcript)} chars")
            
            # Stage 2: Summarize
            current_stage = "summarization"
            stage_start = time.time()
            await db.update_status(session_id, "summarizing")
            
            summary = await self._summarize(transcript, session_id)
            stage_timings['summarization_ms'] = (time.time() - stage_start) * 1000
            
            logger.info(f"Summarization completed for {session_id} - {stage_timings['summarization_ms']:.2f}ms, {len(summary)} chars")
            
            # Stage 3: Generate media (image and/or video)
            current_stage = "media_generation"
            stage_start = time.time()
            
            image_url = None
            image_prompt = None
            image_base64 = None
            video_url = None
            video_prompt = None
            
            # Determine what to generate
            generate_image = generation_mode in ["image", "both"]
            generate_video = generation_mode in ["video", "both"]
            
            if generation_mode == "both":
                # Parallel generation for "both" mode
                await db.update_status(session_id, "generating_media", {
                    "image": "in_progress",
                    "video": "in_progress"
                })
                
                # First, generate the image prompt (needed for both)
                prompt_start = time.time()
                image_prompt = await self._generate_image_prompt(summary, session_id)
                stage_timings['prompt_generation_ms'] = (time.time() - prompt_start) * 1000
                logger.info(f"Prompt generated for {session_id} - {stage_timings['prompt_generation_ms']:.2f}ms")
                
                # Create parallel tasks
                image_task = self._generate_image_from_prompt(image_prompt, summary, session_id)
                video_task = self._generate_video(summary, image_prompt, transcript, session_id)
                
                # Run both in parallel
                try:
                    results = await asyncio.gather(image_task, video_task, return_exceptions=True)
                    
                    # Handle image result
                    if isinstance(results[0], Exception):
                        logger.error(f"Image generation failed: {results[0]}")
                        await db.update_status(session_id, "generating_media", {
                            "image": "failed",
                            "video": "in_progress",
                            "image_error": str(results[0])
                        })
                    else:
                        image_url, _, image_base64 = results[0]
                        await db.update_status(session_id, "generating_media", {
                            "image": "completed",
                            "video": "in_progress"
                        })
                    
                    # Handle video result
                    if isinstance(results[1], Exception):
                        logger.error(f"Video generation failed: {results[1]}")
                        await db.update_status(session_id, "generating_media", {
                            "image": "completed" if image_url else "failed",
                            "video": "failed",
                            "video_error": str(results[1])
                        })
                    else:
                        video_url, video_prompt = results[1]
                        
                except Exception as e:
                    logger.error(f"Parallel generation failed: {e}")
                    raise
                
                stage_timings['media_generation_ms'] = (time.time() - stage_start) * 1000
                logger.info(f"Parallel media generation completed for {session_id} - {stage_timings['media_generation_ms']:.2f}ms")
                
            elif generate_image:
                # Image only mode
                await db.update_status(session_id, "generating_image")
                image_url, image_prompt, image_base64 = await self._generate_image(summary, session_id)
                stage_timings['image_generation_ms'] = (time.time() - stage_start) * 1000
                logger.info(f"Image generation completed for {session_id} - {stage_timings['image_generation_ms']:.2f}ms")
                
            elif generate_video:
                # Video only mode
                await db.update_status(session_id, "generating_video")
                # Still need an image prompt for video generation
                image_prompt = await self._generate_image_prompt(summary, session_id)
                video_url, video_prompt = await self._generate_video(summary, image_prompt, transcript, session_id)
                stage_timings['video_generation_ms'] = (time.time() - stage_start) * 1000
                logger.info(f"Video generation completed for {session_id} - {stage_timings['video_generation_ms']:.2f}ms")
            
            # Stage 5: Generate title
            current_stage = "title_generation"
            stage_start = time.time()
            await db.update_status(session_id, "generating_title")
            
            # Generate title using unified method
            title = await self._generate_title(
                image_base64=image_base64,
                summary=summary,
                visual_prompt=video_prompt or image_prompt,
                session_id=session_id
            )
            stage_timings['title_generation_ms'] = (time.time() - stage_start) * 1000
            
            logger.info(f"Title generation completed for {session_id} - {stage_timings['title_generation_ms']:.2f}ms: '{title}'")
            
            # Stage 6: Store results
            current_stage = "storing_results"
            await db.update_status(session_id, "storing")
            
            result_data = {
                'transcript': transcript,
                'summary': summary,
                'title': title,
                'generation_mode': generation_mode,
                'status': 'completed'
            }
            
            # Add media URLs based on what was generated
            if image_url:
                result_data['image_url'] = image_url
                result_data['image_prompt'] = image_prompt
            if video_url:
                result_data['video_url'] = video_url
                result_data['video_prompt'] = video_prompt
            
            await db.notify_user(session_id, result_data)
            
            # Final status update to mark as completed
            await db.update_status(session_id, "completed")
            
            # Calculate total processing time
            total_time_ms = (time.time() - process_start) * 1000
            stage_timings['total_ms'] = total_time_ms
            
            # Log final timing summary
            timing_summary = ', '.join([f"{k}: {v:.2f}ms" for k, v in stage_timings.items()])
            logger.info(f"Processing completed successfully for {session_id} - {timing_summary}")
            
        except Exception as e:
            # Enhanced error tracking with stack trace
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "current_stage": current_stage,
                "session_id": session_id,
                "traceback": traceback.format_exc(),
                "processing_time_ms": (time.time() - process_start) * 1000
            }
            
            logger.error(f"Processing failed for {session_id} at stage: {current_stage} - {str(e)}\n{traceback.format_exc()}")
            
            # Update status with error info
            await db.update_status(session_id, "failed", {
                "error": str(e),
                "stage": current_stage
            })
            raise
    
    async def _transcribe(self, audio_content: bytes, filename: str) -> str:
        """Transcribe audio using Whisper"""
        start_time = time.time()
        try:
            # Get file extension from filename
            ext = os.path.splitext(filename)[1] or '.wav'
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp.write(audio_content)
                tmp_path = tmp.name
            
            # Transcribe
            with open(tmp_path, 'rb') as audio:
                response = await asyncio.to_thread(
                    openai_client.audio.transcriptions.create,
                    model=os.getenv('WHISPER_MODEL', 'whisper-1'),
                    file=audio
                )
            
            # Cleanup
            os.unlink(tmp_path)
            
            # Log API performance
            api_latency_ms = (time.time() - start_time) * 1000
            logger.info(f"Whisper API call completed - {api_latency_ms:.2f}ms")
            
            return response.text
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    async def _summarize(self, transcript: str, session_id: str = None) -> str:
        """Summarize transcript using GPT-5"""
        start_time = time.time()
        try:
            # Handle empty or very short transcripts
            if not transcript or len(transcript.strip()) < 5:
                logger.warning(f"Transcript too short or empty for session {session_id}: '{transcript}'")
                return "Audio content was too brief or unclear to summarize."
            
            response = await asyncio.to_thread(
                openai_client.responses.create,
                model=os.getenv('GPT_TEXT_MODEL', 'gpt-5'),
                # reasoning={"effort": "medium"},
                instructions="Create a concise 2-3 sentence summary that captures the key points and main theme.",
                input=transcript
            )
            
            # Track API performance
            api_latency_ms = (time.time() - start_time) * 1000
            
            # Track usage if session_id provided
            if session_id and hasattr(response, 'usage') and response.usage:
                # Handle different response formats safely
                try:
                    # New responses.create format has input_tokens, output_tokens, total_tokens
                    if hasattr(response.usage, 'total_tokens'):
                        total_tokens = response.usage.total_tokens
                        completion_tokens = getattr(response.usage, 'output_tokens', 0)
                        prompt_tokens = getattr(response.usage, 'input_tokens', 0)
                    else:
                        # Fallback
                        total_tokens = 0
                        completion_tokens = 0
                        prompt_tokens = 0
                    
                    logger.info(f"GPT-5 summarization completed - {api_latency_ms:.2f}ms")
                    
                    # Only store usage if we have valid token counts
                    if total_tokens > 0:
                        await db.store_openai_usage(
                            session_id=session_id,
                            openai_id=getattr(response, 'id', 'unknown'),
                            request_type="summarization",
                            model_used=getattr(response, 'model', 'gpt-5'),
                            tokens={
                                'completion_tokens': completion_tokens,
                                'prompt_tokens': prompt_tokens,
                                'total_tokens': total_tokens
                            }
                        )
                except AttributeError as e:
                    # Skip usage tracking if attributes are missing
                    logger.info(f"GPT-5 summarization completed - {api_latency_ms:.2f}ms (usage tracking skipped: {e})")
            
            return response.output_text
            
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            raise
    
    async def _generate_image(self, summary: str, session_id: str = None) -> tuple[str, str, str]:
        """Generate image using gpt-image-1
        Returns: (image_url, prompt_used, base64_image)
        """
        try:
            # First generate a prompt
            prompt = await self._generate_image_prompt(summary, session_id)
            # Then generate the image
            return await self._generate_image_from_prompt(prompt, summary, session_id)
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise
    
    async def _generate_image_from_prompt(self, prompt: str, summary: str, session_id: str = None) -> tuple[str, str, str]:
        """Generate image from a given prompt
        Returns: (image_url, prompt_used, base64_image)
        """
        try:
            
            # Generate image with GPT image model
            logger.info(f"Generating image with prompt: {prompt[:100]}...")
            image_response = await asyncio.to_thread(
                openai_client.images.generate,
                model=os.getenv('GPT_IMAGE_MODEL', 'gpt-image-1'),
                prompt=prompt,
                size="1024x1024",
                quality="auto",
                n=1
            )
            
            # Get the image data
            image_data = image_response.data[0]
            # For URL response, we need to download and convert to base64
            if hasattr(image_data, 'url') and image_data.url:
                import aiohttp
                import ssl
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_data.url, ssl=ssl_context) as resp:
                        image_bytes = await resp.read()
                        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            else:
                # Should have b64_json if response_format was set
                image_base64 = getattr(image_data, 'b64_json', '')
                if not image_base64:
                    raise ValueError("No image data received from API")
                image_bytes = base64.b64decode(image_base64)
            
            revised_prompt = image_data.revised_prompt if hasattr(image_data, 'revised_prompt') else prompt
            
            # image_bytes already decoded above
            
            # Upload to Cloudinary if enabled, otherwise save locally
            if cloudinary_service:
                try:
                    logger.info(f"Uploading image to Cloudinary for session {session_id}")
                    upload_result = await cloudinary_service.upload_image(
                        image_bytes=image_bytes,
                        session_id=session_id,
                        user_id=None,  # Will derive from session_id
                        metadata={
                            "title": summary[:100],  # Temporary title from summary
                            "prompt": revised_prompt,
                            "summary": summary
                        }
                    )
                    image_url = upload_result["url"]
                    logger.info(f"Image uploaded to Cloudinary: {image_url}")
                except Exception as e:
                    logger.error(f"Cloudinary upload failed, falling back to local: {e}")
                    # Fallback to local storage
                    os.makedirs("generated_images", exist_ok=True)
                    local_filename = f"generated_images/{session_id}.png" if session_id else "generated_images/test_image.png"
                    with open(local_filename, "wb") as f:
                        f.write(image_bytes)
                    logger.info(f"Saved generated image locally to {local_filename}")
                    image_url = local_filename
            else:
                # Local storage only
                os.makedirs("generated_images", exist_ok=True)
                local_filename = f"generated_images/{session_id}.png" if session_id else "generated_images/test_image.png"
                with open(local_filename, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"Saved generated image to {local_filename}")
                image_url = local_filename
            
            return image_url, revised_prompt, image_base64
            
        except Exception as e:
            logger.error(f"Image generation failed: {e}")
            raise
    
    async def _generate_title(self, image_base64: str = None, summary: str = None, visual_prompt: str = None, session_id: str = None) -> str:
        """Generate title using vision model (with image) or text model (without image)
        
        Args:
            image_base64: Optional base64 encoded image for vision-based title
            summary: Text summary of the content
            visual_prompt: Optional visual concept/prompt when no image available
            session_id: Optional session ID for usage tracking
        """
        try:
            if image_base64:
                # Use vision model to analyze image and summary
                response = await asyncio.to_thread(
                    openai_client.chat.completions.create,
                    model=os.getenv('GPT_VISION_MODEL', 'gpt-5-mini'),
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Based on this image and summary, create a short, catchy title (max 5 words) that captures the essence of both.\n\nSummary: {summary}"
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{image_base64}"
                                    }
                                }
                            ]
                        }
                    ],
                )
            else:
                # Use text-only model when no image available
                response = await asyncio.to_thread(
                    openai_client.responses.create,
                    model=os.getenv('GPT_TEXT_MODEL', 'gpt-5'),
                    # reasoning={"effort": "medium"},
                    instructions="Create a short, catchy title (maximum 5 words) that captures the essence of the content.",
                    input=f"Summary: {summary}\n\nVisual concept: {visual_prompt}" if visual_prompt else summary
                )
            
            # Track title generation usage
            if session_id and hasattr(response, 'usage') and response.usage:
                # Handle different response formats
                if hasattr(response, 'usage') and response.usage:
                    # Handle different response formats
                    usage_data = {}
                    if hasattr(response.usage, 'completion_tokens'):
                        usage_data['completion_tokens'] = response.usage.completion_tokens
                    elif hasattr(response.usage, 'output_tokens'):
                        usage_data['completion_tokens'] = response.usage.output_tokens
                    
                    if hasattr(response.usage, 'prompt_tokens'):
                        usage_data['prompt_tokens'] = response.usage.prompt_tokens
                    elif hasattr(response.usage, 'input_tokens'):
                        usage_data['prompt_tokens'] = response.usage.input_tokens
                    
                    if hasattr(response.usage, 'total_tokens'):
                        usage_data['total_tokens'] = response.usage.total_tokens
                    elif 'completion_tokens' in usage_data and 'prompt_tokens' in usage_data:
                        usage_data['total_tokens'] = usage_data['completion_tokens'] + usage_data['prompt_tokens']
                    
                    if usage_data:
                        await db.store_openai_usage(
                            session_id=session_id,
                            openai_id=response.id,
                            request_type="title_generation",
                            model_used=response.model,
                            tokens=usage_data
                        )
                # Skip usage tracking for new response format for now
            
            # Handle response based on model type
            if image_base64:
                return response.choices[0].message.content
            else:
                return response.output_text
            
        except Exception as e:
            logger.error(f"Title generation failed: {e}")
            raise
    
    async def _generate_image_prompt(self, summary: str, session_id: str = None) -> str:
        """Generate just the image prompt without creating an image
        
        Used for video-only mode to get visual concepts
        """
        try:
            prompt_response = await asyncio.to_thread(
                openai_client.responses.create,
                model=os.getenv('GPT_TEXT_MODEL', 'gpt-5'),
                # reasoning={"effort": "high"},
                instructions="Create an artistic, visually rich image prompt for DALL-E. Be creative and descriptive, focusing on visual elements, colors, composition, and mood. Maximum 100 words.",
                input=summary
            )
            return prompt_response.output_text
        except Exception as e:
            logger.error(f"Image prompt generation failed: {e}")
            raise
        
    async def _generate_video(self, summary: str, image_prompt: str, transcript: str, session_id: str = None) -> tuple[str, dict]:
        """Generate video using Google Veo 3
        
        Returns:
            Tuple of (video_url, video_prompt_dict)
        """
        global video_prompt_generator, veo_client
        
        try:
            # Initialize clients if not already done
            if video_prompt_generator is None:
                video_prompt_generator = VideoPromptGenerator(openai_client)
                logger.info("Initialized video prompt generator")
            
            if veo_client is None:
                # Check if GCP project ID is configured
                gcp_project_id = os.getenv('GCP_PROJECT_ID')
                if not gcp_project_id:
                    logger.error("GCP_PROJECT_ID not configured, skipping video generation")
                    raise ValueError("GCP_PROJECT_ID must be set for video generation")
                
                veo_client = VeoClient(project_id=gcp_project_id)
                logger.info(f"Initialized Veo client for project: {gcp_project_id}")
            
            # Generate structured video prompt
            logger.info(f"Generating video prompt for session {session_id}")
            video_prompt = await video_prompt_generator.generate_video_prompt(
                summary=summary,
                image_prompt=image_prompt,
                transcript=transcript[:500] if transcript else None  # Use first 500 chars of transcript
            )
            
            # Convert to Veo-optimized text
            veo_prompt_text = video_prompt_generator.format_for_veo(video_prompt)
            logger.info(f"Generated Veo prompt: {veo_prompt_text[:100]}...")
            
            # Generate video with Veo
            logger.info(f"Submitting video generation request for session {session_id}")
            
            # Check if we have a GCS bucket configured for video storage
            gcs_bucket = os.getenv('GCS_VIDEO_BUCKET')
            storage_uri = f"gs://{gcs_bucket}/videos/{session_id}/" if gcs_bucket else None
            
            operation = await veo_client.generate_video(
                prompt=veo_prompt_text,
                aspect_ratio="16:9",  # Default to landscape
                resolution="720p",    # Start with 720p for faster generation
                person_generation="allow",
                storage_uri=storage_uri,
                sample_count=1
            )
            
            # Wait for video generation to complete
            logger.info(f"Waiting for video generation to complete for session {session_id}")
            video_result = await veo_client.wait_for_video(
                operation['name'],
                timeout_seconds=90,  # Increased timeout now that status checking works
                poll_interval=10
            )
            
            # Extract video URL and always save locally
            video_url = None
            if video_result.get('status') == 'completed':
                # Video generation completed successfully
                if 'videoUri' in video_result and video_result['videoUri']:
                    # Video is in GCS, download and save locally
                    gcs_uri = video_result['videoUri']
                    logger.info(f"Video available at GCS: {gcs_uri}")
                    # For now, just note the GCS location
                    # TODO: Could download from GCS if needed
                    video_url = f"generated_videos/{session_id}.mp4"
                    # Store GCS URI for reference
                    os.makedirs("generated_videos", exist_ok=True)
                    with open(f"generated_videos/{session_id}_gcs.txt", "w") as f:
                        f.write(gcs_uri)
                    logger.info(f"Video GCS URI saved for session {session_id}")
                    
                elif 'videoBase64' in video_result:
                    # Decode base64 video
                    video_bytes = base64.b64decode(video_result['videoBase64'])
                    
                    # Upload to Cloudinary if enabled, otherwise save locally
                    if cloudinary_service:
                        try:
                            logger.info(f"Uploading video to Cloudinary for session {session_id}")
                            upload_result = await cloudinary_service.upload_video(
                                video_bytes=video_bytes,
                                session_id=session_id,
                                user_id=None,  # Will derive from session_id
                                metadata={
                                    "title": summary[:100],  # Temporary title from summary
                                    "prompt": video_prompt,
                                    "summary": summary
                                }
                            )
                            video_url = upload_result["url"]
                            logger.info(f"Video uploaded to Cloudinary: {video_url}")
                        except Exception as e:
                            logger.error(f"Cloudinary video upload failed, falling back to local: {e}")
                            # Fallback to local storage
                            os.makedirs("generated_videos", exist_ok=True)
                            local_filename = f"generated_videos/{session_id}.mp4"
                            with open(local_filename, "wb") as f:
                                f.write(video_bytes)
                            logger.info(f"Saved generated video locally to {local_filename}")
                            video_url = local_filename
                    else:
                        # Local storage only
                        os.makedirs("generated_videos", exist_ok=True)
                        local_filename = f"generated_videos/{session_id}.mp4"
                        with open(local_filename, "wb") as f:
                            f.write(video_bytes)
                        logger.info(f"Saved generated video to {local_filename}")
                        video_url = local_filename
            
            elif video_result.get('status') in ['submitted', 'timeout', 'error']:
                # Video is still processing or had an issue
                logger.warning(f"Video generation status: {video_result.get('status')}")
                video_url = f"pending:{video_result.get('operation_id', operation.get('name', 'unknown'))}"
                # Store operation ID for later checking
                os.makedirs("generated_videos", exist_ok=True)
                with open(f"generated_videos/{session_id}_operation.txt", "w") as f:
                    f.write(video_result.get('operation_id', operation.get('name', '')))
            else:
                logger.warning(f"Unexpected video result: {video_result}")
                video_url = f"pending:{operation.get('name', 'unknown')}"
            
            logger.info(f"Video generation completed for session {session_id}: {video_url}")
            
            return video_url, video_prompt
            
        except Exception as e:
            logger.error(f"Video generation failed for session {session_id}: {e}")
            # Return None values on failure but don't crash the entire process
            return None, None


# Global processor instance
processor = AudioProcessor()