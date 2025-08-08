from firebase_admin import initialize_app, credentials
from openai import OpenAI
from dotenv import load_dotenv

import os
import logging

# Customize the log format
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(funcName)s - %(message)s"

# Configure logging with the custom format
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
)


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

def initialize_firebase():
    # Use the application default credentials
    cred = credentials.ApplicationDefault()
    initialize_app(cred)
    logging.info("Firebase initialized")

def initialize_openai_client():
    # Initialize OpenAI client
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    if OPENAI_API_KEY:
        client = OpenAI(api_key=OPENAI_API_KEY)
        logging.info("OpenAI client initialized")
    else:
        logging.error("OPENAI_API_KEY not found in environment variables.")
        raise ValueError("OPENAI_API_KEY not found in environment variables.")
    
    return client

# Ensure Firebase is initialized at module load
initialize_firebase()
initialize_openai_client()