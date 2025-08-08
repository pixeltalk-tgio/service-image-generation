import requests
import logging
import os

from zoneinfo import ZoneInfo
from datetime import datetime
from firebase_admin import firestore, storage # SETUP FIREBASE
import json

# Customize the log format
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(funcName)s - %(message)s"

# Configure logging with the custom format
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
)


def download_audio_file(url, session_id):
    if os.path.isfile(url):  # If already a local file path, return it directly
        logging.info(f"Audio file already available locally: {url}")
        return url

    # Otherwise, treat as a URL and download
    local_filename = f"/tmp/{session_id}_audio_file.wav"
    try:
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
        logging.info(f"Audio file downloaded to {local_filename}")
        return local_filename
    except Exception as e:
        logging.error(f"Error downloading audio file from {url}: {e}")
        raise

def check_cancellation(session_id):
    # This function should query the database and return True if the processing should be cancelled.
    # Implementation depends on how you're storing the session's state.
    db_ref = firestore.client().collection('sessions').document(session_id)
    doc = db_ref.get()
    if doc.exists:
        return doc.to_dict().get('is_cancelled', False)
    return False

def send_request(method, path, body=None, headers={}):
    try:
        url = f"https://cl.imagineapi.dev{path}"
        response = requests.request(method, url, json=body, headers=headers)
        response.raise_for_status()
        logging.info(f"Request to {url} completed with status code {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"HTTP error while sending request to {url}: {e}")
        raise RuntimeError(f"HTTP error while sending request to {url}: {e}")


def check_image_status(image_id, headers):
    try:
        response_data = send_request('GET', f"/items/images/{image_id}", headers=headers)
        status = response_data['data']['status']
        if status in ['completed', 'failed']:
            if status == 'failed':
                logging.error("Image generation failed.")
                raise RuntimeError("Image generation failed.")
            logging.info("Image generation completed.")
            return response_data['data']
        else:
            logging.info(f"Images are not finished generating. Status: {status}")
            return None
    except Exception as e:
        logging.error(f"Error checking image status for {image_id}: {e}")
        raise


def cleanup_file(file_path):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"File {file_path} has been removed.")
        else:
            logging.warning(f"File {file_path} does not exist.")
    except Exception as e:
        logging.error(f"Error removing file {file_path}: {e}")
        raise


def final_results(session_id, prompt, recording_url, summary, uploaded_image_urls, titles, transcription):
    if check_cancellation(session_id):
        raise Exception("Processing cancelled by user before compiling results.")

    bucket = storage.bucket('pixel-talk-personal')
    est_timezone = ZoneInfo("America/New_York")
    timestamp = datetime.now(est_timezone).strftime("%Y-%m-%d %H:%M:%S %Z")
    final_result = {
                    'sessionId': session_id,
                    'timestamp': timestamp,
                    'transcript': transcription,
                    'prompt': prompt,
                    'recording': recording_url,
                    'summarization': summary,
                    'images': [
                        {
                            'url': uploaded_image_urls[i],
                            f'title_{i + 1}': titles[i][f'title_{i + 1}']
                        } for i in range(len(uploaded_image_urls))
                    ]
                }
    document_path = f'user_data/{session_id}.json'
    # Uploading to Firebase Storage
    blob = bucket.blob(document_path)
    # Serialize data to JSON format
    blob.upload_from_string(json.dumps(final_result), content_type='application/json')
    
    # Final check for cancellation before concluding the process
    if check_cancellation(session_id):
        raise Exception("Processing cancelled by user after compiling results.")

    return final_result