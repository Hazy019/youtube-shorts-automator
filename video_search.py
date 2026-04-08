import os
import random
import io
import time
import uuid
import boto3
import requests
import socket
from botocore.config import Config
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv

_old_getaddrinfo = socket.getaddrinfo
def _ipv4_getaddrinfo(*args, **kwargs):
    responses = _old_getaddrinfo(*args, **kwargs)
    return [r for r in responses if r[0] == socket.AF_INET]
socket.getaddrinfo = _ipv4_getaddrinfo

from discord_bot import ping_error

load_dotenv()

# Supabase — lazy init to avoid crashing if creds are wrong at import time
_supabase = None
def _get_supabase():
    global _supabase
    if _supabase is None:
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                _supabase = create_client(url, key)
        except Exception as e:
            print(f"Supabase init (video_search) failed: {e}")
    return _supabase

BUCKET_NAME        = os.getenv("BUCKET_NAME")
GAMING_BGM_FOLDER  = os.getenv("GAMING_BGM_FOLDER_ID")
GENERAL_BGM_FOLDER = os.getenv("GENERAL_BGM_FOLDER_ID")
SFX_FOLDER         = os.getenv("SFX_FOLDER_ID")

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ── PEXELS FALLBACK KEYWORD POOLS ────────────────────────────────────────────
# When Pexels returns no results for the AI-generated keyword, randomly pick
# from these topic-appropriate fallback pools instead of ALWAYS using Parkour.
PEXELS_GENERAL_FALLBACK = [
    "Aerial Cityscape", "Time Lapse Nature", "Storm Lightning",
    "Deep Ocean", "Aurora Borealis", "Space Galaxy",
    "Mountain Landscape", "Abstract Science", "Fire Water",
    "Forest Sunlight", "Microscope Biology", "Architecture Buildings",
]

PEXELS_SCIENCE_TERMS = [
    "Space Nebula", "Deep Ocean", "Human Brain", "DNA Strand",
    "Cell Biology", "Lightning Storm", "Aurora Borealis", "Wild Nature",
    "Neural Network", "Solar System", "Quantum Physics", "Chemical Reaction",
]
# ─────────────────────────────────────────────────────────────────────────────


def get_drive_service():
    creds = None
    if os.path.exists("token_drive.json"):
        creds = Credentials.from_authorized_user_file("token_drive.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        elif os.getenv("GITHUB_ACTIONS") == "true":
            ping_error("Drive token expired in CI!", "Google Auth")
            raise Exception("Drive token expired in CI")
        else:
            from google_auth_oauthlib.flow import InstalledAppFlow
            flow = InstalledAppFlow.from_client_secrets_file("client_secrets.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token_drive.json", "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def sync_drive_to_s3(folder_id, num_clips, media_type="video"):
    if not folder_id:
        print(f"No Drive folder ID for {media_type}. Skipping.")
        return []

    service = get_drive_service()

    if media_type == "video":
        query = f"'{folder_id}' in parents and mimeType='video/mp4'"
        content_type = "video/mp4"
        s3_prefix = "backgrounds/bg_"
    else:
        query = (
            f"'{folder_id}' in parents and "
            "(mimeType='audio/mpeg' or mimeType='audio/wav' or mimeType='audio/mp3')"
        )
        content_type = "audio/mpeg"
        s3_prefix = "audio/aud_"

    items = []
    for attempt in range(4):
        try:
            results = service.files().list(q=query, fields="files(id, name)").execute()
            items = results.get("files", [])
            break
        except Exception as e:
            print(f"Drive API list error (attempt {attempt+1}): {e}")
            if attempt == 3:
                return []
            time.sleep(2 ** attempt)
    
    if not items:
        return []

    # Clip deduplication
    db = _get_supabase()
    if db:
        try:
            used = db.table("used_clips").select("file_id").execute()
            used_ids = {c["file_id"] for c in used.data}
            fresh = [i for i in items if i["id"] not in used_ids]
            if not fresh:
                print("All clips used recently. Resetting dedup window.")
                fresh = items
            items = fresh
        except Exception as e:
            print(f"Dedup warning: {e}")

    random.shuffle(items)
    selected = items[: min(num_clips, len(items))]

    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        config=Config(region_name="us-east-1", s3={"addressing_style": "virtual"}),
    )
    urls = []

    for item in selected:
        safe = item["name"].encode("ascii", "ignore").decode("ascii")
        print(f"  Syncing {media_type}: {safe}")

        if db:
            try:
                db.table("used_clips").insert(
                    {"file_id": item["id"], "file_name": item["name"], "media_type": media_type}
                ).execute()
            except Exception:
                pass

        for attempt in range(4):
            try:
                req = service.files().get_media(fileId=item["id"])
                fh = io.BytesIO()
                dl = MediaIoBaseDownload(fh, req)
                done = False
                while not done:
                    _, done = dl.next_chunk()
                break
            except Exception as e:
                print(f"Drive API download error (attempt {attempt+1}): {e}")
                if attempt == 3:
                    raise e
                time.sleep(2 ** attempt)

        fh.seek(0)
        key = f"{s3_prefix}{uuid.uuid4().hex}"
        s3.upload_fileobj(fh, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": key}, ExpiresIn=3600
        )
        urls.append(url)

    return urls


def _fetch_pexels(keyword, num_clips, page=None):
    """
    Fetch Pexels videos for a keyword.
    Randomizes page (1-4) for variety. Returns portrait-optimized URLs.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    if page is None:
        page = random.randint(1, 4)

    fetch_count = max(num_clips * 3, 9)
    base_url = (
        f"https://api.pexels.com/videos/search"
        f"?query={keyword}&per_page={fetch_count}&orientation=portrait"
    )

    try:
        resp = requests.get(
            f"{base_url}&page={page}",
            headers={"Authorization": api_key},
            timeout=15
        ).json()
        videos = resp.get("videos", [])

        # If random page had no results, try page 1
        if not videos and page != 1:
            resp = requests.get(
                f"{base_url}&page=1",
                headers={"Authorization": api_key},
                timeout=15
            ).json()
            videos = resp.get("videos", [])

        if not videos:
            return []

        random.shuffle(videos)
        urls = []
        for video in videos[:num_clips]:
            files = video.get("video_files", [])
            portrait = [f for f in files if f.get("height", 0) > f.get("width", 0)]
            if portrait:
                portrait.sort(key=lambda f: f.get("height", 0), reverse=True)
                # Cap at 1080p to avoid Lambda OOM on 4K files
                chosen = next(
                    (f for f in portrait if f.get("height", 9999) <= 1920),
                    portrait[0]
                )
            else:
                chosen = files[0] if files else None
            if chosen:
                urls.append(chosen["link"])

        return urls

    except Exception as e:
        print(f"Pexels error for '{keyword}': {e}")
        return []


def get_background_videos(topic, keyword, num_clips=3):
    """
    Route b-roll based on topic + Gemini's search_keyword.

    ROUTING LOGIC:
    1. Gaming topic detected → Parkour Drive folder (physical action footage)
    2. keyword == "Parkour" → Parkour Drive folder
    3. Any other keyword → Try Pexels with that keyword
       a. Good results (≥2 clips) → use Pexels
       b. Poor results → try a random fallback keyword from general pool
       c. Still poor → try Parkour Drive as last resort
    """
    num_clips = min(num_clips, 3)

    gaming_kw = [
        "blox fruit", "bloxfruits", "roblox", "kitsune", "buddha",
        "third sea", "bounty", "fruit", "mechanics", "dough", "awakened",
        "mario", "minecraft", "gta", "elden ring", "doom", "zelda",
        "fortnite", "pokemon", "sonic", "gaming", "speedrun", "glitch",
        "video game", "developer", "easter egg", "speedrunner",
    ]
    is_gaming_topic = any(w in topic.lower() for w in gaming_kw)

    # ── Route 1: Gaming → Parkour Drive ──────────────────────────────────
    if is_gaming_topic:
        print(f"Gaming topic → PARKOUR Drive")
        return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")

    # ── Route 2: AI explicitly chose Parkour → Drive ──────────────────────
    if keyword.lower() == "parkour":
        print(f"Keyword=Parkour → PARKOUR Drive")
        return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")

    # ── Route 3: Pexels with AI-generated keyword ─────────────────────────
    print(f"Fetching Pexels: '{keyword}'")
    urls = _fetch_pexels(keyword, num_clips)

    if len(urls) >= 2:
        print(f"  Pexels returned {len(urls)} clips for '{keyword}'")
        return urls

    # ── Route 4: Pexels returned too few → try a random fallback keyword ──
    # This prevents always falling back to Parkour when Pexels has thin results
    fallback_keyword = random.choice(PEXELS_GENERAL_FALLBACK)
    print(f"  Pexels thin ({len(urls)} clips). Trying fallback: '{fallback_keyword}'")
    urls = _fetch_pexels(fallback_keyword, num_clips)

    if len(urls) >= 2:
        print(f"  Fallback Pexels returned {len(urls)} clips")
        return urls

    # ── Route 5: True last resort → Parkour Drive ─────────────────────────
    print(f"  Pexels exhausted. Using Parkour Drive as last resort.")
    return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")


def get_sfx_urls(num_sfx=7):
    """Fetch SFX pool — request 7 so Composition can match by filename keyword."""
    print("Fetching SFX pool from Drive...")
    return sync_drive_to_s3(SFX_FOLDER, num_sfx, "audio")


def get_bgm_url(category="general"):
    folder = GAMING_BGM_FOLDER if category == "gaming" else GENERAL_BGM_FOLDER
    if not folder:
        print(f"No BGM folder for '{category}'. Skipping.")
        return None
    print(f"Fetching {category} BGM...")
    urls = sync_drive_to_s3(folder, 1, "audio")
    return urls[0] if urls else None