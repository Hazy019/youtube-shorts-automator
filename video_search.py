import os
import random
import io
import uuid
import boto3
import requests 
from botocore.config import Config
import googleapiclient.discovery
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from dotenv import load_dotenv

from discord_bot import ping_error

load_dotenv()

BUCKET_NAME = os.getenv("BUCKET_NAME")
ROBLOX_FOLDER_ID = os.getenv("ROBLOX_FOLDER_ID")
PARKOUR_FOLDER_ID = os.getenv("PARKOUR_FOLDER_ID")
SFX_FOLDER_ID = os.getenv("SFX_FOLDER_ID")
BGM_FOLDER_ID = os.getenv("BGM_FOLDER_ID")

SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    creds = None
    if os.path.exists('token_drive.json'):
        creds = Credentials.from_authorized_user_file('token_drive.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if os.getenv("GITHUB_ACTIONS") == "true":
                error_msg = "CRITICAL: Google Tokens expired. Run tools/update_tokens.py locally and update GitHub Secrets!"
                ping_error(error_msg, "Google Auth")
                raise Exception(error_msg)
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_drive.json', 'w') as token:
            token.write(creds.to_json())
    return googleapiclient.discovery.build('drive', 'v3', credentials=creds)

def sync_drive_to_s3(target_folder, num_clips, media_type="video"):
    service = get_drive_service()
    
    # Check if we are grabbing Video or Audio
    if media_type == "video":
        query = f"'{target_folder}' in parents and mimeType='video/mp4'"
        content_type = 'video/mp4'
        s3_prefix = "backgrounds/bg_"
    else:
        query = f"'{target_folder}' in parents and (mimeType='audio/mpeg' or mimeType='audio/wav' or mimeType='audio/mp3')"
        content_type = 'audio/mpeg'
        s3_prefix = "audio/aud_"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get('files', [])

    if not items:
        return []

    random.shuffle(items)
    selected_items = items[:min(num_clips, len(items))]
    
    s3_config = Config(region_name='us-east-1', s3={'addressing_style': 'virtual'})
    s3 = boto3.client('s3', region_name='us-east-1', config=s3_config)
    urls = []
    
    for item in selected_items:
        print(f"Syncing {media_type}: {item['name']} to S3...")
        request = service.files().get_media(fileId=item['id'])
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        s3_key = f"{s3_prefix}{uuid.uuid4().hex}"
        s3.upload_fileobj(fh, BUCKET_NAME, s3_key, ExtraArgs={'ContentType': content_type})
        
        s3_link = s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET_NAME, 'Key': s3_key}, ExpiresIn=3600)
        urls.append(s3_link)
        
    return urls

def get_background_videos(topic, keyword, num_clips=5):
    gaming_keywords = ["blox fruit", "bloxfruits", "roblox", "robux", "kitsune", "buddha", "third sea", "bounty", "fruit", "mechanics"]
    is_roblox_topic = any(word in topic.lower() for word in gaming_keywords)
    
    if is_roblox_topic:
        print("Roblox Fact detected! Targeting ROBLOX Drive Folder...")
        return sync_drive_to_s3(ROBLOX_FOLDER_ID, num_clips, media_type="video")
        
    else:
        if "parkour" in keyword.lower():
            print("AI chose Parkour! Targeting PARKOUR Drive Folder...")
            return sync_drive_to_s3(PARKOUR_FOLDER_ID, num_clips, media_type="video")
        else:
            print(f"Universal Fact detected! Fetching Pexels footage for: {keyword}")
            api_key = os.getenv("PEXELS_API_KEY")
            url = f"https://api.pexels.com/videos/search?query={keyword}&per_page={num_clips}&orientation=portrait"
            
            try:
                response = requests.get(url, headers={"Authorization": api_key}).json()
                urls = []
                if 'videos' in response and len(response['videos']) > 0:
                    for video in response['videos']:
                        urls.append(video['video_files'][0]['link'])
                    return urls
                return []
            except Exception as e:
                print(f"Pexels Error: {e}")
                return []

def get_sfx_urls(num_sfx=5):
    print("Fetching Professional Sound Effects...")
    return sync_drive_to_s3(SFX_FOLDER_ID, num_sfx, media_type="audio")

def get_bgm_url():
    if not BGM_FOLDER_ID:
        print("No BGM_FOLDER_ID found in .env. Skipping background music.")
        return None
    print("Fetching Background Music from Drive...")
    urls = sync_drive_to_s3(BGM_FOLDER_ID, 1, media_type="audio")
    return urls[0] if urls else None