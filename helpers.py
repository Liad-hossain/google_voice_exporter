import os
from email import policy
import datetime
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

TEMP_DIR = "./temp"
EXTRACT_DIR = "./temp/extracted"

def process_mbox_file(mbox_path):
    audio_recordings = []
    full_mbox_path = os.path.join(EXTRACT_DIR, mbox_path)

    try:
        with open(full_mbox_path, 'rb') as f:
            parser = BytesParser(policy=policy.default)
            messages = []

            content = f.read().decode('utf-8', errors='ignore')
            message_blocks = content.split('\nFrom ')

            for i, block in enumerate(message_blocks):
                if i == 0 and not block.startswith('From '):
                    continue

                if not block.strip():
                    continue

                if i > 0:
                    block = 'From ' + block

                try:
                    msg = parser.parsestr(block, headersonly=False)
                    messages.append(msg)
                except Exception as e:
                    print(f"Failed to parse message {i}: {e}")
                    continue

            print(f"Found {len(messages)} messages in MBOX file")

            for msg in messages:
                # Check if this is a call recording message
                subject = msg.get('Subject', '')
                if 'OUTGOING_CALL' in subject or 'INCOMING_CALL' in subject or 'recording' in subject.lower():
                    # Extract call details
                    from_number = msg.get('From', '').strip('+')
                    to_number = msg.get('To', '').strip('+')
                    date_str = msg.get('Date', '')

                    # Determine if it's outgoing or incoming
                    is_outgoing = 'OUTGOING_CALL' in subject
                    phone_number = to_number if is_outgoing else from_number

                    # Parse date
                    try:
                        # Parse the date string
                        parsed_date = parsedate_to_datetime(date_str)
                        timestamp = parsed_date.strftime('%Y%m%d_%H%M%S')
                    except Exception as e:
                        print(f"Failed to parse date '{date_str}': {e}")
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

                    # Process attachments
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'application/octet-stream':
                                filename = part.get_filename()
                                if filename and ('recording' in filename.lower() or filename.endswith(('.mp3', '.wav'))):
                                    # Get the base64 encoded content
                                    payload = part.get_payload(decode=True)
                                    if payload:
                                        # Create filename
                                        audio_filename = f"call_{phone_number}_{timestamp}.mp3"
                                        audio_path = os.path.join(EXTRACT_DIR, audio_filename)

                                        # Decode and save the audio file
                                        try:
                                            with open(audio_path, 'wb') as audio_file:
                                                audio_file.write(payload)

                                            audio_recordings.append(audio_filename)
                                            print(f"Extracted audio recording: {audio_filename}")

                                        except Exception as e:
                                            print(f"Failed to save audio file {audio_filename}: {e}")

    except Exception as e:
        print(f"Failed to parse MBOX file {mbox_path}: {e}")

    return audio_recordings