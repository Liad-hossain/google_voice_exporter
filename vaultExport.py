import os
from pathlib import Path
import requests
import shutil
import google.auth.transport.requests as google_requests
from utils import build_filename, upload_to_drive, extract_zip_file, get_auth_credentials, get_audio_files

TEMP_DIR = "./temp"
EXTRACT_DIR = "./temp/extracted"


def download_zip_files(gcs_url, credentials):
    print(f"Downloading: {gcs_url}")
    headers = {"Authorization": f"Bearer {credentials.token}"}

    # Extract filename from URL
    filename = gcs_url.split('/')[-1]
    zip_path = os.path.join(TEMP_DIR, filename)

    with requests.get(gcs_url, headers=headers, stream=True, timeout=30) as response:
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)

    file_size = os.path.getsize(zip_path)
    print(f"Download completed. File size: {file_size} bytes")
    return zip_path



def download_and_upload(completed_export, credentials):

    files = completed_export.get('cloudStorageSink', {}).get('files', [])
    if not files:
        print("No files found in the completed export")
        return

    zip_files_downloaded = []

    for file_info in files:
        gcs_url = f"https://storage.googleapis.com/{file_info['bucketName']}/{file_info['objectName']}"

        # Only download ZIP files, skip metadata XML files
        if gcs_url.endswith('.zip'):
            zip_path = download_zip_files(gcs_url, credentials)
            zip_files_downloaded.append(zip_path)
        else:
            print(f"Skipping non-ZIP file: {gcs_url}")

    # Extract all downloaded ZIP files
    for zip_path in zip_files_downloaded:
        extract_zip_file(zip_path)

    audio_files = get_audio_files()
    print(f"All files found: {audio_files}")
    
    for file_path in audio_files:
        print(f"Uploading file: {file_path}")
        full_path = os.path.join(EXTRACT_DIR, file_path)
        file_name = build_filename(os.path.basename(file_path))

        upload_to_drive(credentials, full_path, file_name)

        print("All recordings uploaded")



def run():
    """Main execution function"""
    # Create directories
    Path(EXTRACT_DIR).mkdir(parents=True, exist_ok=True)

    credentials = get_auth_credentials()

    # Impersonate workspace admin if specified
    workspace_admin_email = os.environ.get('WORKSPACE_ADMIN_EMAIL')
    if workspace_admin_email:
        credentials = credentials.with_subject(workspace_admin_email)

    # --- Get latest completed export ---
    vault_matter_id = os.environ.get('VAULT_MATTER_ID')
    if not vault_matter_id:
        raise ValueError("VAULT_MATTER_ID environment variable not set")

    # Get access token
    request = google_requests.Request()
    credentials.refresh(request)

    exports_url = f"https://vault.googleapis.com/v1/matters/{vault_matter_id}/exports"
    headers = {"Authorization": f"Bearer {credentials.token}"}

    response = requests.get(exports_url, headers=headers)
    response.raise_for_status()
    exports_data = response.json()

    completed_exports = []
    for export in exports_data.get('exports', []):
        if export.get('status') == 'COMPLETED':
            completed_exports.append(export)

    if not completed_exports:
        print("No completed export found")
        return

    for completed_export in completed_exports:
        download_and_upload(completed_export, credentials)

if __name__ == "__main__":
    try:
        run()
    except Exception as err:
        print(f"Error: {err}")
        exit(1)