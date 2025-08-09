"""
PixelTalk Audio Processing Service
Handles audio transcription, summarization, and image generation
"""

from fastapi import FastAPI, HTTPException, UploadFile, File, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional
import logging
import uuid
import os
import time
import json
from contextvars import ContextVar

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Initialize production environment if needed
if os.getenv('ENVIRONMENT') == 'production':
    import startup
    startup.initialize_production()

from services.audio_processor import processor
from database import db
from database.datadog import datadog_logger

# Configure structured logging
request_id_var: ContextVar[str] = ContextVar('request_id', default='')
app_start_time = time.time()

class StructuredLogger:
    def __init__(self, name):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] - %(message)s',
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        self.logger.addHandler(handler)
    
    def _log(self, level, message, **kwargs):
        extra = {'request_id': request_id_var.get()}
        if kwargs:
            message = f"{message} | {json.dumps(kwargs)}"
        getattr(self.logger, level)(message, extra=extra)
    
    def info(self, message, **kwargs):
        self._log('info', message, **kwargs)
    
    def error(self, message, **kwargs):
        self._log('error', message, **kwargs)
    
    def warning(self, message, **kwargs):
        self._log('warning', message, **kwargs)
    
    def debug(self, message, **kwargs):
        self._log('debug', message, **kwargs)

logger = StructuredLogger(__name__)


# Lifecycle management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle"""
    # Startup
    logger.info("Starting audio processor...")
    await processor.start()
    logger.info("Audio processor started successfully")
    
    yield
    
    # Shutdown
    logger.info("Stopping audio processor...")
    await processor.stop()
    logger.info("Audio processor stopped")


# Create FastAPI app
app = FastAPI(
    title="PixelTalk Audio Processing Service",
    description="Processes audio recordings into AI-generated artwork",
    version="2.0.0",
    lifespan=lifespan
)

# Request tracking middleware
@app.middleware("http")
async def add_request_tracking(request: Request, call_next):
    # Generate request ID
    req_id = str(uuid.uuid4())[:8]
    request_id_var.set(req_id)
    
    # Track request start
    start_time = time.time()
    
    # Log incoming request
    logger.info(f"Request started", 
                method=request.method, 
                path=request.url.path,
                client=request.client.host if request.client else "unknown")
    
    # Process request
    response = await call_next(request)
    
    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000
    
    # Log completion
    logger.info(f"Request completed",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration_ms, 2))
    
    # Track metrics (commented out for now)
    # await datadog_logger.track_metric(
    #     "api.request.duration",
    #     duration_ms,
    #     tags={"endpoint": request.url.path, "method": request.method, "status": response.status_code}
    # )
    
    # Add request ID to response headers
    response.headers["X-Request-ID"] = req_id
    return response

# Add CORS middleware (configure as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Response models
class ProcessingResponse(BaseModel):
    """Response for audio upload"""
    session_id: str
    status: str
    message: str


class StatusResponse(BaseModel):
    """Response for status check"""
    session_id: str
    status: str
    stage: Optional[str] = None
    result: Optional[dict] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    service: str
    database: bool
    processor: bool



# Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check service health"""
    try:
        # Check database connection
        db_status = await db.test_connection()
        
        # Check processor status (if it has a worker running)
        processor_status = processor.worker_task is not None and not processor.worker_task.done()
        
        return HealthResponse(
            status="healthy" if db_status and processor_status else "degraded",
            service="audio-processing",
            database=db_status,
            processor=processor_status
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            service="audio-processing",
            database=False,
            processor=False
        )


@app.post("/upload", response_model=ProcessingResponse)
async def upload_audio(
    file: UploadFile = File(...),
    generation_mode: str = Form("image")
):
    """
    Upload audio file for processing
    
    - Accepts audio file and generation mode
    - Queues for processing
    - Returns session ID for tracking
    
    Generation modes:
    - "image": Generate static image only (default)
    - "video": Generate video only
    - "both": Generate both image and video
    """
    # Check file extension (basic validation)
    allowed_extensions = {'.wav', '.mp3', '.m4a', '.webm', '.ogg'}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Validate generation mode
    if generation_mode not in ["image", "video", "both"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid generation mode. Must be 'image', 'video', or 'both'"
        )
    
    # Generate session ID
    session_id = str(uuid.uuid4())
    
    try:
        # Queue audio for processing with generation mode (non-blocking)
        await processor.process_audio(session_id, file, generation_mode)
        
        logger.info(f"Audio queued for processing: {session_id} (mode: {generation_mode})")
        
        return ProcessingResponse(
            session_id=session_id,
            status="processing",
            message="Audio queued for processing"
        )
        
    except Exception as e:
        logger.error(f"Failed to queue audio {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to process audio")


@app.get("/status/{session_id}", response_model=StatusResponse)
async def get_status(session_id: str):
    """
    Get processing status for a session
    
    - Returns current processing stage
    - Returns result when completed
    - Returns error if failed
    """
    try:
        # Get latest status updates
        updates = await db.get_status_updates(session_id)
        
        if not updates:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get latest status
        latest = updates[-1]
        current_status = latest.get('status', 'unknown')
        
        # Check if completed
        if current_status == 'completed':
            # Get the full result
            result = await db.get_session_results(session_id)
            return StatusResponse(
                session_id=session_id,
                status="completed",
                result=result
            )
        elif current_status == 'failed':
            # Get error info
            error_info = latest.get('additional_info', {})
            return StatusResponse(
                session_id=session_id,
                status="failed",
                error=error_info.get('error', 'Unknown error')
            )
        else:
            # Still processing
            return StatusResponse(
                session_id=session_id,
                status="processing",
                stage=current_status
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get status")



@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "PixelTalk Audio Processing",
        "version": "2.0.0",
        "endpoints": {
            "health": "/health",
            "upload": "/upload",
            "status": "/status/{session_id}",
            "docs": "/docs"
        }
    }


# Run the application
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")
    
    logger.info(f"Starting server on {host}:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=False,  # Set to True for development
        log_level="info"
    )