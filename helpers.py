import re
import os
import mailbox


TEMP_DIR = "./temp"
EXTRACT_DIR = "./temp/extracted"


def get_mbox_files():
    mbox_files = []
    for root, _, files in os.walk(EXTRACT_DIR):
        for file in files:
            if file.endswith('.mbox'):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, EXTRACT_DIR)
                mbox_files.append(rel_path)
    return mbox_files


def get_call_duration(subject, message):
    call_duration = None
    duration_patterns = [
        r'Duration:?\s*(\d+):(\d+)',  # Duration: 5:23
        r'(\d+)m\s*(\d+)s',          # 5m 23s
        r'(\d+):(\d+)',              # 5:23
        r'(\d+)\s*min',              # 5 min
        r'(\d+)\s*sec'               # 30 sec
    ]

    for pattern in duration_patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if match:
            if len(match.groups()) == 2:
                minutes, seconds = match.groups()
                call_duration = f"{minutes}:{seconds.zfill(2)}"
            else:
                call_duration = f"0:{match.group(1).zfill(2)}"
            break


    if not call_duration and message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True)
                if body:
                    body_text = body.decode('utf-8', errors='ignore')
                    for pattern in duration_patterns:
                        match = re.search(pattern, body_text, re.IGNORECASE)
                        if match:
                            if len(match.groups()) == 2:
                                minutes, seconds = match.groups()
                                call_duration = f"{minutes}:{seconds.zfill(2)}"
                            else:
                                call_duration = f"0:{match.group(1).zfill(2)}"
                            break
                    if call_duration:
                        break
    return call_duration


def process_mbox_file(mbox_path):
    audio_recordings = []
    full_mbox_path = os.path.join(EXTRACT_DIR, mbox_path)

    try:
        mbox = mailbox.mbox(full_mbox_path)
        messages = []

        for message in mbox:
            messages.append(message)

        print(f"Found {len(messages)} messages in MBOX file")

        for msg in messages:
            subject = msg.get('Subject', '')
            if 'OUTGOING_CALL' in subject or 'INCOMING_CALL' in subject or 'recording' in subject.lower():
                from_number = msg.get('From', '').strip('+')
                to_number = msg.get('To', '').strip('+')
                date_time = msg.get('Date', '')
                message_id = msg.get('Message-ID', '')
                is_outgoing = 'OUTGOING_CALL' in subject
                call_type = 'OUTGOING' if is_outgoing else 'INCOMING'
                phone_number = to_number if is_outgoing else from_number
                call_duration = get_call_duration(subject, msg)
                
                                

                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == 'application/octet-stream':
                            filename = part.get_filename()
                            if filename and ('recording' in filename.lower() or filename.endswith(('.mp3', '.wav'))):
                                payload = part.get_payload(decode=True)
                                
                                if payload:
                                    audio_filename = f"call_{phone_number}_{date_time}.mp3"
                                    audio_path = os.path.join(EXTRACT_DIR, audio_filename)

                                    try:
                                        with open(audio_path, 'wb') as audio_file:
                                            audio_file.write(payload)

                                        recording_info = {
                                            'message_id': message_id,
                                            'file_name': audio_filename,
                                            'from_number': from_number,
                                            'to_number': to_number,
                                            'call_duration': call_duration,
                                            'call_type': call_type,
                                            'date_time': date_time
                                        }

                                        audio_recordings.append(recording_info)
                                        print(f"Extracted audio recording: {audio_filename}")

                                    except Exception as e:
                                        print(f"Failed to save audio file {audio_filename}: {e}")

    except Exception as e:
        print(f"Failed to parse MBOX file {mbox_path}: {e}")

    return audio_recordings