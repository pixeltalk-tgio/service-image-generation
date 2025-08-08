# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Project: PixelTalk Audio-to-Art Service

## Commands
- **Start all services**: `./deploy.sh start`
- **Stop services**: `./deploy.sh stop`
- **Restart**: `./deploy.sh restart`
- **View logs**: `./deploy.sh logs` or `./deploy.sh follow` (real-time)
- **Check status**: `./deploy.sh status`
- **Run tests**: `./deploy.sh test` or `uv run pytest services/tests/`
- **Install deps**: `uv sync`
- **Clean up**: `./deploy.sh clean`
- **Lint**: `uv run ruff check .`
- **Format**: `uv run black .`
- **Type check**: `uv run mypy services/`

## Tech Stack
- Python 3.10+ with async/await patterns
- FastAPI for REST API (port 8000)
- Streamlit for web UI (port 8501)
- Neon PostgreSQL with PostgREST client
- OpenAI APIs (Whisper, GPT-4, DALL-E 3)
- Google Vertex AI (Veo 3 for video generation)
- UV for package management
- Structured logging with request tracking
- Pydantic for structured outputs

## Architecture Overview

### Processing Pipeline
1. **Upload**: Audio file → FastAPI `/upload` endpoint with generation_mode → Returns session ID
2. **Queue**: Task queued in `AudioProcessor` async worker
3. **Process**: Sequential stages with status updates:
   - `transcribing` - Whisper API
   - `summarizing` - GPT-4 generates summary
   - `generating_image` - DALL-E 3 creates artwork (if mode includes image)
   - `generating_video` - Veo 3 creates 8-second video (if mode includes video)
   - `generating_title` - GPT-4 vision analyzes image/summary
   - `storing` - Save to database
   - `completed` - Results ready
4. **Retrieve**: Poll `/status/{session_id}` for progress/results

### Key Components
- `main.py` - FastAPI server with request tracking middleware
- `app.py` - Streamlit UI with progressive polling
- `services/audio_processor.py` - Async queue worker for pipeline
- `services/db/neon.py` - Database operations (async PostgREST)
- `configs/prompts.py` - AI prompt templates

## Code Patterns

### Async Operations
```python
# All I/O operations use async/await
response = await asyncio.to_thread(openai_client.images.generate, ...)
await db.update_status(session_id, "processing")
```

### Status Updates
```python
# Each processing stage updates status in DB
await db.update_status(session_id, "transcribing")
# ... perform work ...
await db.update_status(session_id, "summarizing")
```

### Error Handling
```python
try:
    # processing logic
except Exception as e:
    logger.error(f"Failed for {session_id}: {e}")
    await db.update_status(session_id, "failed", {"error": str(e)})
    raise HTTPException(status_code=500, detail="Processing failed")
```

## Database Schema

Primary tables in Neon PostgreSQL:
- `completed_results` - Final processing results
- `update_status` - Processing stage tracking
- `sessions` - User session management
- `openai_responses` - API usage metrics

## Environment Variables
Required in `.env`:
```
OPENAI_API_KEY=sk-...
NEON_DATA_API_URL=https://...
NEON_API_KEY=...
NEON_SCHEMA=public  # optional
```

## Testing
- Test files in `services/tests/`
- Run single test: `uv run pytest services/tests/test_audio_processor.py -v`
- Integration tests available for full pipeline

## Important Notes

### Database Migration
System is migrating from Firebase to Neon. Firebase code remains for backwards compatibility but Neon is primary.

### Logging
- Logs saved to `logs/` directory
- Backend: `logs/backend.log`
- Frontend: `logs/frontend.log`
- Structured logging with request IDs for tracing

### Progressive Polling
Frontend uses backoff intervals: [1, 1, 2, 2, 3, 3, 5, 5, 5, 10] seconds to reduce server load during long image generation (~60-120s).

### Local Storage
Generated images saved locally in `generated_images/` directory, not cloud storage.