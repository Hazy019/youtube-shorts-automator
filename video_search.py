import os
import random
import io
import uuid
import boto3
import requests
from botocore.config import Config
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from supabase import create_client, Client
from dotenv import load_dotenv

from discord_bot import ping_error

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

BUCKET_NAME        = os.getenv("BUCKET_NAME")
GAMING_BGM_FOLDER  = os.getenv("GAMING_BGM_FOLDER_ID")
GENERAL_BGM_FOLDER = os.getenv("GENERAL_BGM_FOLDER_ID")
SFX_FOLDER         = os.getenv("SFX_FOLDER_ID")

SCOPES = ["https://www.googleapis.com/auth/drive"]


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

    results = service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])
    if not items:
        return []

    try:
        used = supabase.table("used_clips").select("file_id").execute()
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

        try:
            supabase.table("used_clips").insert(
                {"file_id": item["id"], "file_name": item["name"], "media_type": media_type}
            ).execute()
        except Exception:
            pass

        req = service.files().get_media(fileId=item["id"])
        fh = io.BytesIO()
        dl = MediaIoBaseDownload(fh, req)
        done = False
        while not done:
            _, done = dl.next_chunk()

        fh.seek(0)
        key = f"{s3_prefix}{uuid.uuid4().hex}"
        s3.upload_fileobj(fh, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": key}, ExpiresIn=3600
        )
        urls.append(url)

    return urls


def _fetch_pexels_random(keyword, num_clips):
    """
    Fetch Pexels videos with page randomization so results aren't identical every run.
    Selects the best portrait-orientation file for each result.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    # Randomize page (pages 1-4)
    page = random.randint(1, 4)
    fetch_count = max(num_clips * 3, 9)
    url = (
        f"https://api.pexels.com/videos/search"
        f"?query={keyword}&per_page={fetch_count}&page={page}&orientation=portrait"
    )

    try:
        resp = requests.get(url, headers={"Authorization": api_key}, timeout=15).json()
        videos = resp.get("videos", [])
        if not videos:
            url_p1 = url.replace(f"page={page}", "page=1")
            resp = requests.get(url_p1, headers={"Authorization": api_key}, timeout=15).json()
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
                chosen = next(
                    (f for f in portrait if f.get("height", 9999) <= 1920),
                    portrait[0]
                )
            else:
                chosen = files[0]
            urls.append(chosen["link"])

        return urls

    except Exception as e:
        print(f"Pexels error: {e}")
        return []


def get_background_videos(topic, keyword, num_clips=3):
    num_clips = min(num_clips, 3)

    gaming_kw = [
        "blox fruit", "bloxfruits", "roblox", "kitsune", "buddha",
        "third sea", "bounty", "fruit", "mechanics", "dough", "awakened",
        "mario", "minecraft", "gta", "elden ring", "doom", "zelda",
        "fortnite", "pokemon", "sonic", "gaming", "speedrun", "glitch",
    ]
    is_gaming_topic = any(w in topic.lower() for w in gaming_kw)

    if is_gaming_topic:
        print("Gaming topic → PARKOUR Drive Folder")
        return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")

    if "parkour" in keyword.lower():
        print("Keyword=Parkour → PARKOUR Drive Folder")
        return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")

    # Pexels with random page
    print(f"Fetching Pexels footage for '{keyword}' (randomized page)...")
    urls = _fetch_pexels_random(keyword, num_clips)
    if len(urls) >= 2:
        return urls

    print(f"Pexels returned only {len(urls)} clips. Falling back to Parkour Drive.")
    return sync_drive_to_s3(os.getenv("PARKOUR_FOLDER_ID"), num_clips, "video")


def get_sfx_urls(num_sfx=7):
    """Fetch SFX — request more than needed so Composition can match by filename."""
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