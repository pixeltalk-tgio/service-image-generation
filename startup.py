"""
Startup configuration for production deployment
Handles environment setup and credential management
"""

import os
import base64
import json
import sys
from pathlib import Path

def setup_google_credentials():
    """
    Set up Google Cloud credentials from base64 encoded environment variable.
    Used in production environments where we can't store the JSON file directly.
    """
    # Check if credentials are provided as base64
    credentials_base64 = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_BASE64')
    
    if credentials_base64:
        try:
            # Decode the base64 credentials
            credentials_json = base64.b64decode(credentials_base64).decode('utf-8')
            
            # Parse to validate JSON
            credentials_dict = json.loads(credentials_json)
            
            # Write to a temporary file
            credentials_path = Path('/tmp/gcp_credentials.json')
            with open(credentials_path, 'w') as f:
                json.dump(credentials_dict, f)
            
            # Set the environment variable to point to the file
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(credentials_path)
            
            print("✅ Google Cloud credentials configured from environment")
            return True
            
        except Exception as e:
            print(f"⚠️ Failed to set up Google Cloud credentials: {e}")
            print("   Video generation may not work without GCP credentials")
            return False
    
    # Check if credentials file already exists
    elif os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        if os.path.exists(os.getenv('GOOGLE_APPLICATION_CREDENTIALS')):
            print("✅ Google Cloud credentials file found")
            return True
        else:
            print("⚠️ GOOGLE_APPLICATION_CREDENTIALS points to non-existent file")
            return False
    
    # Try local gcp.json file (development)
    elif os.path.exists('gcp.json'):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'gcp.json'
        print("✅ Using local gcp.json file")
        return True
    
    else:
        print("⚠️ No Google Cloud credentials found")
        print("   Video generation will be disabled")
        return False

def validate_environment():
    """
    Validate that all required environment variables are set.
    """
    required_vars = {
        'OPENAI_API_KEY': 'OpenAI API key for transcription and generation',
        'NEON_DATA_API_URL': 'Neon database API URL',
        'NEON_API_KEY': 'Neon database API key',
        'CLOUDINARY_URL': 'Cloudinary URL for media storage'
    }
    
    optional_vars = {
        'GCP_PROJECT_ID': 'Google Cloud project ID for video generation',
        'USE_CLOUDINARY': 'Enable Cloudinary uploads (true/false)',
        'PORT': 'Server port (default: 8000)'
    }
    
    missing_required = []
    missing_optional = []
    
    print("=" * 50)
    print("Environment Configuration Check")
    print("=" * 50)
    
    # Check required variables
    for var, description in required_vars.items():
        if os.getenv(var):
            print(f"✅ {var}: Set")
        else:
            print(f"❌ {var}: Missing - {description}")
            missing_required.append(var)
    
    # Check optional variables
    for var, description in optional_vars.items():
        if os.getenv(var):
            print(f"✅ {var}: Set")
        else:
            print(f"ℹ️ {var}: Not set - {description}")
            missing_optional.append(var)
    
    print("=" * 50)
    
    if missing_required:
        print(f"❌ Missing required environment variables: {', '.join(missing_required)}")
        print("   Please set these in your .env file or Render dashboard")
        return False
    
    if missing_optional:
        print(f"ℹ️ Optional variables not set: {', '.join(missing_optional)}")
    
    print("✅ All required environment variables are configured")
    return True

def create_directories():
    """
    Create necessary directories for the application.
    """
    directories = [
        'logs',
        'generated_images',
        'generated_videos'
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
    
    print("✅ Application directories created")

def initialize_production():
    """
    Initialize the application for production deployment.
    """
    print("\n🚀 Initializing PixelTalk Service...")
    
    # Create necessary directories
    create_directories()
    
    # Set up Google Cloud credentials
    gcp_status = setup_google_credentials()
    
    # Validate environment
    env_valid = validate_environment()
    
    if not env_valid:
        print("\n❌ Environment validation failed. Please check your configuration.")
        sys.exit(1)
    
    # Set production flags
    os.environ['ENVIRONMENT'] = os.getenv('ENVIRONMENT', 'production')
    
    print("\n✅ PixelTalk Service initialized successfully!")
    print(f"   Environment: {os.getenv('ENVIRONMENT')}")
    print(f"   Port: {os.getenv('PORT', 8000)}")
    print(f"   Cloudinary: {'Enabled' if os.getenv('USE_CLOUDINARY', 'false').lower() == 'true' else 'Disabled'}")
    print(f"   Video Generation: {'Available' if gcp_status else 'Disabled'}")
    print("\n" + "=" * 50 + "\n")

# Run initialization when imported
if __name__ == '__main__' or os.getenv('ENVIRONMENT') == 'production':
    initialize_production()