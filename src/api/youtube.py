import os
import time
import random
import datetime
import googleapiclient.discovery
import googleapiclient.errors
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from src.utils.discord import ping_error

# Target publish slots in UTC (7:00 AM EDT = 11:00 UTC, 7:00 PM EDT = 23:00 UTC)
_PUBLISH_SLOTS_UTC = [11, 23]
_MIN_PROCESSING_BUFFER_SECONDS = 2700  # Minimum 45 minutes buffer before public release

def get_publish_at():
    """
    Returns the next optimal scheduled publish slot as an ISO 8601 UTC string.
    High-traffic slots: 11:00 UTC (7:00 AM EDT) and 23:00 UTC (7:00 PM EDT).
    
    Guarantees a minimum processing buffer of 45 minutes so YouTube has sufficient
    lead time to transcode 1080p, process subtitles, verify content, and index the
    Short into recommendation clusters before going Public.
    """
    now = datetime.datetime.utcnow()
    today = now.date()
    tomorrow = today + datetime.timedelta(days=1)

    candidate_slots = []
    for d in [today, tomorrow]:
        for hour in _PUBLISH_SLOTS_UTC:
            candidate_slots.append(datetime.datetime(d.year, d.month, d.day, hour, 0, 0))

    # Find first slot that is at least MIN_PROCESSING_BUFFER into the future
    for slot in candidate_slots:
        diff = (slot - now).total_seconds()
        if diff >= _MIN_PROCESSING_BUFFER_SECONDS:
            return slot.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Fallback to tomorrow's earliest slot if loop somehow completes
    fallback = datetime.datetime(tomorrow.year, tomorrow.month, tomorrow.day, _PUBLISH_SLOTS_UTC[0], 0, 0)
    return fallback.strftime("%Y-%m-%dT%H:%M:%S.000Z")


# Rotated engagement CTAs — keyed by category to feel contextually human
_ENGAGEMENT_COMMENTS = {
    "us-centric": [
        "Did you know this about the US? Drop a comment 👇",
        "Which fact surprised you the most? 👇",
        "Follow for more US facts nobody talks about!",
        "Share this with someone who needs to see it 👇",
        "What’s the wildest US fact YOU know? Comment below!",
    ],
    "general": [
        "What did you NOT know before this? Drop it below 👇",
        "Follow if this changed how you see the world 👇",
        "Which part shocked you the most? Comment below!",
        "Share this with someone whose mind needs to be blown 🤯",
        "Drop a 🤯 if this blew your mind.",
    ],
}


def _get_engagement_comment(category):
    pool = _ENGAGEMENT_COMMENTS.get(category, _ENGAGEMENT_COMMENTS["general"])
    return random.choice(pool)

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

def get_authenticated_service(token_name='token_youtube.json'):
    creds = None
    if os.path.exists(token_name):
        # Check if file is empty to prevent JSONDecodeError (happens if GitHub Secret is missing)
        if os.path.getsize(token_name) < 5:
            print(f"  Warning: {token_name} is empty or invalid. Ignoring.")
        else:
            try:
                creds = Credentials.from_authorized_user_file(token_name)
            except Exception as e:
                print(f"  Warning: Failed to parse {token_name}: {e}")
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print(f"  Token for {token_name} expired. Attempting refresh...")
                creds.refresh(Request())
                print(f"  Successfully refreshed token for {token_name}")
            except Exception as e:
                print(f"  FAILED to refresh token for {token_name}: {e}")
                if os.getenv("GITHUB_ACTIONS") == "true":
                    error_msg = f"CRITICAL: YouTube Token {token_name} refresh failed: {e}. Run tools/update_tokens.py locally and update GitHub Secrets!"
                    ping_error(error_msg, "YouTube Auth")
                    raise Exception(error_msg)
        else:
            if not creds:
                print(f"  No credentials found for {token_name}")
            elif not creds.refresh_token:
                print(f"  Credentials for {token_name} have NO REFRESH TOKEN.")
            
            if os.getenv("GITHUB_ACTIONS") == "true":
                error_msg = f"CRITICAL: YouTube Token {token_name} invalid/expired and cannot refresh. Run tools/update_tokens.py locally and update GitHub Secrets!"
                ping_error(error_msg, "YouTube Auth")
                raise Exception(error_msg)
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_name, 'w') as token:
            token.write(creds.to_json())
    return googleapiclient.discovery.build('youtube', 'v3', credentials=creds)

def upload_video(video_path, title, description, category="general", tags=None, token_name='token_youtube.json', publish_at=None):
    print(f"\nPreparing to upload {video_path} to YouTube ({token_name})...")
    if publish_at:
        print(f"  Scheduled publish: {publish_at} (video will be private until then)")
    
    youtube = get_authenticated_service(token_name=token_name)
    if not youtube:
        return False


    if not tags:
        tags = ["shorts", "education", "facts", "science"]

    # Proper YouTube category IDs per content type
    # 24 = Entertainment (US-centric), 27 = Education (general)
    if category == "us-centric":
        category_id = "24"
    else:
        category_id = "27"

    # Only append #Shorts if not already in the title
    clean_title = title if "#Shorts" in title or "#shorts" in title else f"{title} #Shorts"

    # Use Gemini description as-is — it already includes SEO hashtags
    # When publishAt is set, video MUST be private first — YouTube auto-publishes at the slot
    if publish_at:
        status_block = {
            "privacyStatus": "private",
            "publishAt": publish_at,
            "selfDeclaredMadeForKids": False
        }
    else:
        status_block = {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }

    request_body = {
        "snippet": {
            "title": clean_title,
            "description": description,
            "tags": tags,
            "categoryId": category_id
        },
        "status": status_block
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
            
            # Fix 7: Rotate engagement comment by category
            # You CANNOT post comments on a private scheduled video via the API.
            if not publish_at:
                engagement_text = _get_engagement_comment(category)
                post_and_pin_comment(youtube, video_id, engagement_text)
            else:
                print("Skipping comment posting: Video is scheduled (private) and cannot receive comments yet.")
            
            return video_link
        except googleapiclient.errors.HttpError as e:
            err_str = str(e).lower()
            if "quotaexceeded" in err_str:
                msg = f"CRITICAL: YouTube Quota Exceeded for {token_name}. Failing fast."
                print(f"\n{msg}")
                ping_error(msg, "YouTube API")
                return False
                
            print(f"YouTube Upload HTTP Error: {e}")
            if attempt == 3: return False
            time.sleep(2 ** (attempt + 1) * 5)
        except Exception as e:
            # Network drops (socket.timeout, Connection reset, etc)
            print(f"YouTube Upload Network Drop ({attempt+1}/4): {e}")
            if attempt == 3:
                ping_error(f"YouTube upload completely dropped after retries: {e}", "Upload")
                return False
            time.sleep(2 ** attempt * 5)
