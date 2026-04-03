import os
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["[https://www.googleapis.com/auth/youtube.upload](https://www.googleapis.com/auth/youtube.upload)"]

def get_authenticated_service():
    creds = None
    if os.path.exists('token_youtube.json'):
        creds = Credentials.from_authorized_user_file('token_youtube.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if os.getenv("GITHUB_ACTIONS") == "true":
                raise Exception("CRITICAL: Google Tokens expired. Run tools/update_tokens.py locally and update GitHub Secrets!")
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_youtube.json', 'w') as token:
            token.write(creds.to_json())
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

def upload_video(video_path, title, description):
    print(f"\nPreparing to upload {video_path} to YouTube...")
    
    youtube = get_authenticated_service()
    if not youtube:
        return False

    request_body = {
        "snippet": {
            "title": f"{title} #Shorts",
            "description": f"{description}\n\n#Shorts #gaming #trends #hazychanel",
            "tags": ["shorts", "gaming", "insight", "educational"],
            "categoryId": "20"
        },
        "status": {
            "privacyStatus": "private", 
            "selfDeclaredMadeForKids": False
        }
    }

    mediaFile = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=mediaFile
    )

    try:
        print("Uploading to YouTube... (This might take a minute depending on your internet speed)")
        response = request.execute()
        print(f"SUCCESS! Video uploaded to YouTube!")
        print(f"Video Link: [https://youtu.be/](https://youtu.be/){response['id']}")
        return True
    except googleapiclient.errors.HttpError as e:
        print(f"YouTube Upload Error: {e}")
        return False