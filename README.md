# PixelTalk Service API

Audio-to-media generation service that transforms audio recordings into images and videos using AI.

## Features

- 🎙️ **Audio Transcription** - Convert speech to text using OpenAI Whisper
- 📝 **Smart Summarization** - Generate concise summaries with GPT-5
- 🎨 **Image Generation** - Create artwork from audio content
- 🎬 **Video Generation** - Generate cinematic videos with Google Veo
- ☁️ **Cloud Storage** - Automatic upload to Cloudinary with user organization
- 🚀 **Async Processing** - Fast, non-blocking API design

## Tech Stack

- **Framework**: FastAPI (Python)
- **AI Models**: OpenAI GPT-5, DALL-E, Whisper
- **Video**: Google Vertex AI (Veo)
- **Database**: Neon (Serverless Postgres)
- **Storage**: Cloudinary
- **Deployment**: Render

## API Endpoints

| Endpoint | Method | Description |
|----------|---------|------------|
| `/` | GET | Service information |
| `/health` | GET | Health check |
| `/upload` | POST | Upload audio for processing |
| `/status/{session_id}` | GET | Check processing status |
| `/docs` | GET | Interactive API documentation |

## Local Development

### Prerequisites
- Python 3.10+
- OpenAI API key
- Neon database
- Cloudinary account
- Google Cloud project (for video)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/YOUR_USERNAME/pixeltalk-service.git
cd pixeltalk-service
```

2. Create `.env` file:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run locally:
```bash
./run_local.sh
# Or with Python directly:
python main.py
```

### Testing

```bash
# Test the service
./test_local_deployment.sh

# Run with Streamlit UI (if available)
./run_local_with_ui.sh
```

## Deployment

This service is configured for deployment on [Render](https://render.com).

### Quick Deploy

1. Push to GitHub
2. Connect repository to Render
3. Add environment variables in Render dashboard
4. Deploy!

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed instructions.

## Environment Variables

### Required
- `OPENAI_API_KEY` - OpenAI API key
- `NEON_DATA_API_URL` - Neon database URL
- `NEON_API_KEY` - Neon API key
- `CLOUDINARY_URL` - Cloudinary connection string

### Optional
- `GCP_PROJECT_ID` - For video generation
- `GOOGLE_APPLICATION_CREDENTIALS_BASE64` - Base64 encoded GCP credentials
- `USE_CLOUDINARY` - Enable cloud storage (default: true)

## API Usage Example

```python
import requests

# Upload audio
with open('audio.wav', 'rb') as f:
    response = requests.post(
        'https://your-service.onrender.com/upload',
        files={'audio': f},
        data={'generation_mode': 'both'}
    )
    
session_id = response.json()['session_id']

# Check status
status = requests.get(
    f'https://your-service.onrender.com/status/{session_id}'
)
print(status.json())
```

## Media Storage

Generated media is organized in Cloudinary:
```
pixeltalk/
└── users/
    └── user_xxx/
        ├── images/YYYY/MM/DD/
        └── videos/YYYY/MM/DD/
```

## Documentation

- [Deployment Guide](DEPLOYMENT.md)
- [Cloudinary Integration](CLOUDINARY_INTEGRATION.md)
- [API Documentation](https://your-service.onrender.com/docs)

## License

MIT License - See [LICENSE](LICENSE) file

## Support

For issues or questions, please open an issue on GitHub.

---

Built with ❤️ using FastAPI and AI