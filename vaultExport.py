import os
import datetime
from pathlib import Path
import requests
import shutil
import google.auth.transport.requests as google_requests
from utils import upload_to_drive, extract_zip_file, get_auth_credentials, is_exist_in_sheet, append_rows_to_sheet, get_existing_message_ids, get_last_export_time, update_last_export_time
from helpers import process_mbox_file, get_mbox_files

TEMP_DIR = "./temp"
EXTRACT_DIR = "./temp/extracted"


def download_zip_files(gcs_url, credentials):
    print(f"Downloading: {gcs_url}")
    headers = {"Authorization": f"Bearer {credentials.token}"}

    filename = gcs_url.split('/')[-1]
    zip_path = os.path.join(TEMP_DIR, filename)

    with requests.get(gcs_url, headers=headers, stream=True, timeout=30) as response:
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            shutil.copyfileobj(response.raw, f)

    file_size = os.path.getsize(zip_path)
    print(f"Download completed. File size: {file_size} bytes")
    return zip_path



def download_and_upload(export_data, credentials):
    try:
        files = export_data.get('cloudStorageSink', {}).get('files', [])
        if not files:
            print("No files found in the completed export")
            return

        zip_files_downloaded = []

        for file_info in files:
            gcs_url = f"https://storage.googleapis.com/{file_info['bucketName']}/{file_info['objectName']}"

            if gcs_url.endswith('.zip'):
                zip_path = download_zip_files(gcs_url, credentials)
                zip_files_downloaded.append(zip_path)
            else:
                print(f"Skipping non-ZIP file: {gcs_url}")

        audio_files = []
        for zip_path in zip_files_downloaded:
            extract_zip_file(zip_path)
            mbox_files = get_mbox_files()
            for mbox_file in mbox_files:
                audio_files.extend(process_mbox_file(mbox_file))

        print(f"All files found: {len(audio_files)} recordings")
        
        message_ids = get_existing_message_ids(credentials)
        for recording_info in audio_files:
            file_name = recording_info['file_name']
            full_path = os.path.join(EXTRACT_DIR, file_name)

            if not is_exist_in_sheet(message_ids, recording_info['message_id']):
                upload_to_drive(credentials, full_path, file_name)
                
                sheet_data = [
                    recording_info['message_id'],
                    recording_info['file_name'],
                    recording_info['from_number'],
                    recording_info['to_number'],
                    recording_info['call_duration'] or 'Unknown',
                    recording_info['call_type'],
                    recording_info['date_time']
                ]
                append_rows_to_sheet(credentials, sheet_data)
                
            else:
                print(f"Recording already exists, skipping: {recording_info['message_id']}")

        print("All recordings processed")
    except Exception as e:
        print(f"Error in download_and_upload: {e}")
        raise


def create_export(credentials):
    exports_url = f"https://vault.googleapis.com/v1/matters/{vault_matter_id}/exports"
    headers = {"Authorization": f"Bearer {credentials.token}"}
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    workspace_admin_email = os.environ.get('WORKSPACE_ADMIN_EMAIL')
    vault_matter_id = os.environ.get('VAULT_MATTER_ID')
    if not vault_matter_id:
        raise ValueError("VAULT_MATTER_ID environment variable not set")
    
    body = {
        "name": f"Voice_Recordings_Export_{timestamp}",
        "query": {
            "corpus": "VOICE",
            "dataScope": "ALL_DATA",
            "searchMethod": "ACCOUNT",
            "accountInfo": {
                "emails": [workspace_admin_email]
            },
            "startTime": get_last_export_time()
        },
        "exportOptions": {
            "voiceOptions": {
                "exportFormat": "MBOX"
            }
        }
    }

    response = requests.post(exports_url, headers=headers, json=body)
    response.raise_for_status()
    return response.json()


def get_exports(credentials):
    exports_url = f"https://vault.googleapis.com/v1/matters/{vault_matter_id}/exports"
    headers = {"Authorization": f"Bearer {credentials.token}"}
    vault_matter_id = os.environ.get('VAULT_MATTER_ID')
    if not vault_matter_id:
        raise ValueError("VAULT_MATTER_ID environment variable not set")

    response = requests.get(exports_url, headers=headers)
    response.raise_for_status()
    return response.json().get("exports", [])


def run():
    try:
        Path(EXTRACT_DIR).mkdir(parents=True, exist_ok=True)

        credentials = get_auth_credentials()

        workspace_admin_email = os.environ.get('WORKSPACE_ADMIN_EMAIL')
        if workspace_admin_email:
            credentials = credentials.with_subject(workspace_admin_email)


        request = google_requests.Request()
        credentials.refresh(request)

        # export_data = create_export(credentials)
        # download_and_upload(export_data, credentials)
        
        exports_data = get_exports(credentials)
        for export in exports_data:
            download_and_upload(export, credentials)

        update_last_export_time((datetime.datetime.now() - datetime.timedelta(minutes=30)).isoformat() + "Z")


    except Exception as e:
        print(f"Error in run: {e}")
        raise
        

if __name__ == "__main__":
    try:
        run()
    except Exception as err:
        print(f"Error: {err}")
        exit(1)