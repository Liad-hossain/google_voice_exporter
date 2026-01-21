import re
import os
import json
import zipfile
from pathlib import Path
from datetime import datetime
from googleapiclient.http import MediaFileUpload
from googleapiclient.discovery import build
from google.oauth2 import service_account



TEMP_DIR = "./temp"
EXTRACT_DIR = "./temp/extracted"


def get_auth_credentials():
    service_account_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not service_account_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON environment variable not set")

    key = json.loads(service_account_json)

    credentials = service_account.Credentials.from_service_account_info(
        key,
        scopes=[
            "https://www.googleapis.com/auth/ediscovery",
            "https://www.googleapis.com/auth/devstorage.read_only",
            "https://www.googleapis.com/auth/drive.file",
        ]
    )
    return credentials


def get_audio_files():
    audio_files = []
    for root, _, files in os.walk(EXTRACT_DIR):
        for file in files:
            if file.endswith(('.wav', '.mp3')):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, EXTRACT_DIR)
                audio_files.append(rel_path)

    return audio_files


def extract_phone_number(filename):
    """Extract phone number from filename"""
    match = re.search(r'\+\d{6,15}', filename)
    return match.group(0) if match else "unknown"


def get_timestamp():
    """Get current timestamp in ISO format with safe characters"""
    return datetime.now().isoformat().replace(':', '-').replace('.', '-')


def build_filename(original_filename):
    """Build a new filename with phone number and timestamp"""
    phone = extract_phone_number(original_filename)
    timestamp = get_timestamp()
    return f"call_{phone}_{timestamp}.wav"


def upload_to_drive(credentials, file_path, drive_file_name):
    drive_service = build('drive', 'v3', credentials=credentials)

    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    if not drive_folder_id:
        raise ValueError("DRIVE_FOLDER_ID environment variable not set")

    print(f"Starting upload for {drive_file_name}")

    file_metadata = {
        'name': drive_file_name,
        'parents': [drive_folder_id]
    }

    media = MediaFileUpload(file_path, mimetype='audio/wav', resumable=True)

    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True
    ).execute()

    print(f"Uploaded {drive_file_name}")
    print(f"Drive upload response: {file}")
    return file


def extract_zip_files(zip_path):
    try:
        print("Starting ZIP extraction...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_entries = zip_ref.namelist()
            print(f"ZIP contains {len(zip_entries)} entries:")
            
            for index, entry in enumerate(zip_entries, 1):
                info = zip_ref.getinfo(entry)
                print(f"  {index}. {entry} ({info.file_size} bytes)")

            zip_ref.extractall(EXTRACT_DIR)

        print("ZIP extracted successfully")
        extracted_files = list(Path(EXTRACT_DIR).iterdir())
        print("Files in extract dir:", [f.name for f in extracted_files])

        if not extracted_files:
            print("Warning: No files were extracted from the ZIP")

    except Exception as extract_error:
        print(f"ZIP extraction failed: {extract_error}")
        print("Downloaded file is not a valid ZIP file!")
