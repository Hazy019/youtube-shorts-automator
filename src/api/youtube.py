import os
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from src.utils.discord import ping_error

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]

def post_and_pin_comment(youtube, video_id, text):
    try:
        print(f"Posting engagement comment to video {video_id}...")
        comment_response = youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": text
                        }
                    }
                }
            }
        ).execute()
        

        comment_id = comment_response['snippet']['topLevelComment']['id']
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus='published'
        ).execute()

        print("Engagement comment posted and status set!")
        return True
    except Exception as e:
        print(f"Failed to post/pin comment: {e}")
        return False

def get_authenticated_service():
    creds = None
    if os.path.exists('token_youtube.json'):
        creds = Credentials.from_authorized_user_file('token_youtube.json', SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if os.getenv("GITHUB_ACTIONS") == "true":
                error_msg = "CRITICAL: YouTube Tokens expired. Run tools/update_tokens.py locally and update GitHub Secrets!"
                ping_error(error_msg, "YouTube Auth")
                raise Exception(error_msg)
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token_youtube.json', 'w') as token:
            token.write(creds.to_json())
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

def upload_video(video_path, title, description, category="gaming", tags=None):
    print(f"\nPreparing to upload {video_path} to YouTube...")
    
    youtube = get_authenticated_service()
    if not youtube:
        return False


    if not tags:
        if category == "gaming":
            tags = ["shorts", "gaming", "roblox", "bloxfruits"]
        else:
            tags = ["shorts", "education", "facts", "science"]

    category_id = "20" if category == "gaming" else "27"

    request_body = {
        "snippet": {
            "title": f"{title} #Shorts",
            "description": f"{description}\n\n#Shorts #trends #hazychanel",
            "tags": tags,
            "categoryId": category_id
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    mediaFile = MediaFileUpload(video_path, chunksize=-1, resumable=True)

    request = youtube.videos().insert(
        part="snippet,status",
        body=request_body,
        media_body=mediaFile
    )

    print(f"Uploading to YouTube as Category {category_id}... (This might take a minute)")
    import time
    for attempt in range(4):
        try:
            response = request.execute()
            video_id = response['id']
            print(f"SUCCESS! Video uploaded to YouTube!")
            video_link = f"https://youtu.be/{video_id}"
            print(f"Video Link: {video_link}")
            
            engagement_text = "What did you NOT know before this? Drop it below 👇"
            post_and_pin_comment(youtube, video_id, engagement_text)
            
            return video_link
        except googleapiclient.errors.HttpError as e:
            # Usually strict HTTP auth errors
            print(f"YouTube Upload HTTP Error: {e}")
            if attempt == 3: return False
            time.sleep(2 ** attempt * 5)
        except Exception as e:
            # Network drops (socket.timeout, Connection reset, etc)
            print(f"YouTube Upload Network Drop ({attempt+1}/4): {e}")
            if attempt == 3:
                ping_error(f"YouTube upload completely dropped after retries: {e}", "Upload")
                return False
            time.sleep(2 ** attempt * 5)
