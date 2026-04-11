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

from src.utils.discord import ping_error

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
HISTORY_BROLL_FOLDER_ID = os.getenv("HISTORY_BROLL_FOLDER_ID")
SCIENCE_BROLL_FOLDER_ID = os.getenv("SCIENCE_BROLL_FOLDER_ID")
PARKOUR_FOLDER_ID = os.getenv("PARKOUR_FOLDER_ID")

SCOPES = ["https://www.googleapis.com/auth/drive"]

# ── CATEGORIZED FALLBACK POOLS ──────────────────────────────────────────────
# We pick a pool based on the original keyword's intent to keep variety relevant.
FALLBACK_NATURE = [
    "Aerial Nature", "Forest Sunlight", "Mountain Landscape", "Time Lapse Nature",
    "Storm Clouds", "River Water", "Island Beach", "Autumn Forest"
]
FALLBACK_SCIENCE = [
    "Space Nebula", "Galaxy Stars", "Deep Ocean", "Human Brain", "Neural Network",
    "Lightning Storm", "Cell Biology", "Quantum Physics", "Circuit Board"
]
FALLBACK_HISTORY = [
    "Ancient Rome", "Medieval Castle", "Architecture Buildings", "Historical Manuscript",
    "Old Library", "Vintage Map", "Dusty Antiques"
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
            results = service.files().list(q=query, fields="files(id, name, size)").execute()
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
        size_mb = round(int(item.get("size", 0)) / (1024 * 1024), 1)
        print(f"  Syncing {media_type}: {safe} ({size_mb}MB)")

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
                    status, done = dl.next_chunk()
                    if status:
                        print(f"    Download Progress: {int(status.progress() * 100)}%", end="\r", flush=True)
                print(f"    Download Progress: 100% (Complete)          ")
                break
            except Exception as e:
                print(f"\nDrive API download error (attempt {attempt+1}): {e}")
                if attempt == 3:
                    raise e
                time.sleep(2 ** attempt)

        fh.seek(0)
        print(f"    Uploading to S3 cloud storage...")
        key = f"{s3_prefix}{uuid.uuid4().hex}"
        s3.upload_fileobj(fh, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": key}, ExpiresIn=7200
        )
        urls.append(url)

    return urls


def _fetch_pexels(keyword, num_clips, page=None):
    """
    Fetch Pexels videos for a keyword.
    Randomizes page (1-5) for variety. Returns portrait-optimized URLs.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    if page is None:
        page = random.randint(1, 5)  # extra page for more variety

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

        # Deduplication using Supabase
        db = _get_supabase()
        if db:
            try:
                used = db.table("used_clips").select("file_id").execute()
                used_ids = {str(c["file_id"]) for c in used.data}
                fresh_videos = [v for v in videos if str(v.get("id")) not in used_ids]
                
                if not fresh_videos:
                    print(f"  All {len(videos)} Pexels videos on this page were used. Proceeding with variety.")
                    fresh_videos = videos
                videos = fresh_videos
            except Exception as e:
                print(f"  Pexels dedup warning: {e}")

        random.shuffle(videos)
        urls = []
        for video in videos[:num_clips]:
            # Log usage
            if db:
                try:
                    db.table("used_clips").insert({
                        "file_id": str(video.get("id")), 
                        "file_name": f"pexels_{video.get('id')}", 
                        "media_type": "pexels_video"
                    }).execute()
                except Exception:
                    pass

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


def get_background_videos(topic, keyword, backup_keywords=None, num_clips=3):
    """
    Route b-roll based on topic + Gemini keywords.
    
    HIERARCHY:
    1. Gaming Topic -> Parkour Drive
    2. Primary Keyword (random page 1-4)
    3. AI Backup Keywords (if primary thin)
    4. Premium AI Drive Folders (Science/History)
    5. Categorized Fallback Pool (if still thin)
    6. Randomized Last Resort (Parkour/Pexels)
    """
    num_clips = min(num_clips, 3)
    topic_lower = topic.lower()

    # Route 1: Gaming → Parkour Drive
    gaming_keywords = ["game", "gaming", "minecraft", "roblox", "gta", "elden", "doom", "speedrun", "speedrunning"]
    if any(k in topic_lower for k in gaming_keywords):
        print(f"  Gaming topic detected. Using Parkour Drive.")
        return sync_drive_to_s3(PARKOUR_FOLDER_ID, num_clips, "video")

    # Route 2: Primary Pexels keyword
    urls = _fetch_pexels(keyword, num_clips)
    if len(urls) >= num_clips:
        print(f"  Pexels primary hit: {keyword}")
        return urls

    # Route 3: AI backup keywords
    if backup_keywords:
        for bk in backup_keywords:
            more = _fetch_pexels(bk, num_clips - len(urls))
            urls.extend(more)
            if len(urls) >= num_clips:
                print(f"  Pexels backup hit: {bk}")
                return urls[:num_clips]

    # Route 4: Premium AI Drive Folders
    # If Pexels didn't find enough clips, pull from our hyper-realistic AI Drive folders
    needed = num_clips - len(urls)
    if needed > 0:
        science_keywords = [
            "space","star","galaxy","planet","nebula","brain","science","physics","quantum",
            "technology","future","cyber","neural","biology","evolution","genetics","astronomy",
            "supernova","black hole","microscope","telescope","chemistry","atom","molecule","laboratory"
        ]
        if any(k in topic_lower for k in science_keywords):
            print(f"  Science topic detected. Pulling {needed} clips from AI_Science_Broll...")
            more = sync_drive_to_s3(SCIENCE_BROLL_FOLDER_ID, needed, "video")
            urls.extend(more)
            
        history_keywords = [
            "rome","history","ancient","medieval","war","knight","tomb","civilization","viking",
            "samurai","warrior","emperor","kingdom","artifact","museum","archaeology",
            "renaissance","napoleon","world war","dynasty","pharaoh","empire","temple","ruins","monarchy"
        ]
        if any(k in topic_lower for k in history_keywords):
            print(f"  History topic detected. Pulling {needed} clips from AI_History_Broll...")
            more = sync_drive_to_s3(HISTORY_BROLL_FOLDER_ID, needed, "video")
            urls.extend(more)
            
        else:
            # If it's a general topic, use curated fallback keywords on Pexels first
            fallback_kw = random.choice(FALLBACK_NATURE)
            more = _fetch_pexels(fallback_kw, needed)
            urls.extend(more)

    if len(urls) >= num_clips:
        return urls[:num_clips]

    # Route 5: Last resort → Randomize Parkour & Pexels
    needed = num_clips - len(urls)
    if needed > 0:
        print(f"  Flow exhausted. Using randomized last resort...")
        # Focus on Parkour only as a 50/50 fallback if not gaming
        if random.random() < 0.5:
             print("  Selected Parkour Drive as last resort.")
             more = sync_drive_to_s3(PARKOUR_FOLDER_ID, needed, "video")
        else:
             fallback_kw = random.choice(FALLBACK_NATURE)
             print(f"  Selected Pexels Nature ({fallback_kw}) as last resort.")
             more = _fetch_pexels(fallback_kw, needed)
        urls.extend(more)

    return urls[:num_clips]


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