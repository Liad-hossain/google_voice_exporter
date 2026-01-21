import os
import json
import shutil
import zipfile
from pathlib import Path
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
    return file


def is_exist_in_sheet(credentials, id):
    sheets_service = build('sheets', 'v4', credentials=credentials)
    sheet = sheets_service.spreadsheets()
    sheet_id = os.environ.get('GOOGLE_SPREADSHEET_ID')
    sheet_tab_name = os.environ.get('GOOGLE_SHEET_TAB_NAME', '')
    if not sheet_id or not sheet_tab_name:
        raise ValueError("GOOGLE_SPREADSHEET_ID or GOOGLE_SHEET_TAB_NAME environment variable not set")

    result = sheet.values().get(
        spreadsheetId=sheet_id,
        range=f'{sheet_tab_name}!A:A'
    ).execute()

    values = result.get('values', [])
    for row in values:
        if row and row[0] == id:
            return True
    return False


def add_row_to_sheet(credentials, sheet_data):
    sheets_service = build('sheets', 'v4', credentials=credentials)
    sheet = sheets_service.spreadsheets()
    sheet_id = os.environ.get('GOOGLE_SPREADSHEET_ID')
    sheet_tab_name = os.environ.get('GOOGLE_SHEET_TAB_NAME', '')
    
    if not sheet_id or not sheet_tab_name:
        raise ValueError("GOOGLE_SPREADSHEET_ID or GOOGLE_SHEET_TAB_NAME environment variable not set")

    body = {
        'values': sheet_data
    }

    result = sheet.values().append(
        spreadsheetId=sheet_id,
        range=f'{sheet_tab_name}!A1',
        valueInputOption='RAW',
        insertDataOption='INSERT_ROWS',
        body=body
    ).execute()

    print(f"Added row to sheet: {sheet_data}")
    return result


def extract_zip_file(zip_path):
    try:
        print(f"Starting ZIP extraction for: {zip_path}")
        temp_extract_dir = Path(EXTRACT_DIR) / "temp_extract"
        temp_extract_dir.mkdir(parents=True, exist_ok=True)
        

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_entries = zip_ref.namelist()
            print(f"ZIP contains {len(zip_entries)} entries:")

            for index, entry in enumerate(zip_entries, 1):
                info = zip_ref.getinfo(entry)
                print(f"  {index}. {entry} ({info.file_size} bytes)")

            zip_ref.extractall(temp_extract_dir)

        print(f"ZIP extracted successfully to temporary directory: {temp_extract_dir}")

        for extracted_file in temp_extract_dir.rglob("*.zip"):
            if extracted_file.name.endswith('.mbox.zip'):
                mbox_zip_path = str(extracted_file)
                print(f"Found .mbox.zip file: {extracted_file.name}")
                with zipfile.ZipFile(mbox_zip_path, 'r') as mbox_zip_ref:
                    mbox_zip_ref.extractall(EXTRACT_DIR)

        shutil.rmtree(temp_extract_dir)
        print(f"Cleaned up temporary directory: {temp_extract_dir}")

    except Exception as extract_error:
        print(f"ZIP extraction failed: {extract_error}")

        if os.path.exists(EXTRACT_DIR):
            try:
                extracted_files = list(Path(EXTRACT_DIR).iterdir())
                file_names = [f.name for f in extracted_files]
                print(f"Files currently in extract directory: {file_names}")
            except Exception as dir_error:
                print(f"Could not read extract directory: {dir_error}")
        else:
            print("Extract directory does not exist")

        print("Downloaded file is not a valid ZIP file!")
