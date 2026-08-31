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
import subprocess
from pydub import AudioSegment
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
GENERAL_BGM_FOLDER = os.getenv("GENERAL_BGM_FOLDER_ID")
SFX_FOLDER         = os.getenv("SFX_FOLDER_ID")
HISTORY_BROLL_FOLDER_ID = os.getenv("HISTORY_BROLL_FOLDER_ID")
SCIENCE_BROLL_FOLDER_ID = os.getenv("SCIENCE_BROLL_FOLDER_ID")

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
# ── FFmpeg Trimming Utility ──────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────

def trim_video_ffmpeg(input_path, output_path, duration):
    """
    Highly efficient trimming using system FFmpeg.
    - input_path: path to raw downloaded video
    - output_path: path for trimmed video
    - duration: target length in seconds
    """
    target = float(duration) + 2.0  # 2.0s safety buffer
    print(f"    FFmpeg: Trimming video to {target:.1f}s...")
    
    try:
        # We try stream copy (-c copy) first for instant processing.
        # If it fails (some codecs don't like partial copies), we fall back to fast encoding.
        cmd = [
            "ffmpeg", "-y", "-ss", "00:00:00", "-to", str(target),
            "-i", input_path, "-c", "copy", "-avoid_negative_ts", "1", output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("    FFmpeg: Stream copy failed, falling back to fast encoding...")
            cmd = [
                "ffmpeg", "-y", "-ss", "00:00:00", "-to", str(target),
                "-i", input_path, "-c:v", "libx264", "-preset", "ultrafast", 
                "-crf", "22", "-c:a", "aac", output_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            
        print(f"    FFmpeg: Trim complete. Output: {output_path}")
        return True
    except Exception as e:
        print(f"    FFmpeg Error: {e}")
        return False



def get_drive_service():
    creds = None
    if os.path.exists("token_drive.json"):
        if os.path.getsize("token_drive.json") < 5:
            print("  Warning: token_drive.json is empty or invalid. Ignoring.")
        else:
            try:
                creds = Credentials.from_authorized_user_file("token_drive.json")
            except Exception as e:
                print(f"  Warning: Failed to parse token_drive.json: {e}")
    
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


def sync_drive_to_s3(folder_id, num_clips, media_type="video", max_duration=None):
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

    # If it's a BGM or long audio, we trim it to a reasonable length (e.g., 5 mins max)
    # to prevent Lambda memory issues and download timeouts.
    def _trim_audio_if_needed(fh, name):
        try:
            fh.seek(0)
            audio = AudioSegment.from_file(fh)
            # If longer than 5 minutes, trim it. 
            # Most shorts are < 2 mins, so 5 mins (300,000ms) is plenty of buffer.
            if len(audio) > 300000:
                print(f"    Trimming long audio {name} ({len(audio)/1000:.1f}s) to 300s...")
                trimmed = audio[:300000]
                out = io.BytesIO()
                trimmed.export(out, format="mp3")
                out.seek(0)
                return out
        except Exception as e:
            print(f"    Audio trim warning: {e}")
        fh.seek(0)
        return fh

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
        if media_type == "audio":
            fh = _trim_audio_if_needed(fh, item["name"])
        
        # ── FFmpeg Video Trimming ──────────────────────────────────────────────
        final_fh = fh
        temp_raw = f"temp_raw_{uuid.uuid4().hex}.mp4"
        temp_trimmed = f"temp_trimmed_{uuid.uuid4().hex}.mp4"
        
        if media_type == "video" and max_duration:
            try:
                # Save stream to local temp file for FFmpeg to process
                with open(temp_raw, "wb") as f:
                    f.write(fh.read())
                
                if trim_video_ffmpeg(temp_raw, temp_trimmed, max_duration):
                    final_fh = open(temp_trimmed, "rb")
                    print(f"    S3 Upload: Sending trimmed version ({os.path.getsize(temp_trimmed)/1024/1024:.1f}MB)")
                else:
                    fh.seek(0)
                    final_fh = fh
            except Exception as e:
                print(f"    Trimming failed, uploading raw: {e}")
                fh.seek(0)
                final_fh = fh

        print(f"    Uploading to S3 cloud storage...")
        key = f"{s3_prefix}{uuid.uuid4().hex}"
        
        for attempt in range(3):
            try:
                final_fh.seek(0)
                s3.upload_fileobj(final_fh, BUCKET_NAME, key, ExtraArgs={"ContentType": content_type})
                break
            except Exception as e:
                print(f"    S3 Upload error ({attempt+1}/3): {e}")
                if attempt == 2: raise e
                time.sleep(2 ** attempt)
        
        # Cleanup
        if final_fh != fh:
            final_fh.close()
        for f in [temp_raw, temp_trimmed]:
            if os.path.exists(f): os.remove(f)

        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET_NAME, "Key": key}, ExpiresIn=172800
        )
        urls.append(url)

    return urls


def _fetch_pexels(keyword, num_clips, page=None, max_duration=None):
    """
    Fetch Pexels videos for a keyword and mirror them to S3.

    Raw Pexels/Vimeo CDN links are throttled for non-browser (Puppeteer) requests
    inside Lambda — a single 1080p clip can take 200-500 s to stream-download,
    which blows the 600 s stitcher budget before a single frame is rendered.

    Fix: download each clip here (on the GitHub Actions runner, which has fast
    outbound bandwidth) and upload to S3. Lambda then fetches the pre-signed S3
    URL at ~1 Gbps (same AWS network) — near-instant regardless of clip size.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    if page is None:
        page = random.randint(1, 5)

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
                    print(f"  Notice: All {len(videos)} Pexels clips for '{keyword}' were used previously. Triggering backup keyword fallback.")
                    return []
                videos = fresh_videos
            except Exception as e:
                print(f"  Pexels dedup warning: {e}")

        random.shuffle(videos)

        # ── S3 client (reuse same config as sync_drive_to_s3) ──────────────────
        s3 = boto3.client(
            "s3",
            region_name="us-east-1",
            config=Config(region_name="us-east-1", s3={"addressing_style": "virtual"}),
        )

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

            # Pick best portrait file capped at 1080p to avoid Lambda OOM on 4K
            files = video.get("video_files", [])
            portrait = [f for f in files if f.get("height", 0) > f.get("width", 0)]
            if portrait:
                portrait.sort(key=lambda f: f.get("height", 0), reverse=True)
                chosen = next(
                    (f for f in portrait if f.get("height", 9999) <= 1080),
                    portrait[0]
                )
            else:
                chosen = files[0] if files else None

            if not chosen:
                continue

            cdn_url = chosen["link"]
            video_id = video.get("id", uuid.uuid4().hex)
            print(f"  Pexels → S3: [{keyword}] video {video_id} ({chosen.get('height', '?')}p)")

            # Download from Pexels CDN (fast on GitHub runner) → stream to S3
            temp_raw = f"temp_raw_{uuid.uuid4().hex}.mp4"
            temp_trimmed = f"temp_trimmed_{uuid.uuid4().hex}.mp4"
            
            try:
                print(f"    Downloading raw b-roll from Pexels...")
                for dl_attempt in range(3):
                    try:
                        with requests.get(cdn_url, stream=True, timeout=120) as r:
                            r.raise_for_status()
                            with open(temp_raw, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                        break
                    except Exception as e:
                        print(f"    Download error ({dl_attempt+1}/3): {e}")
                        if dl_attempt == 2: raise e
                        time.sleep(2 ** dl_attempt)
                
                # Trim if duration provided
                upload_path = temp_raw
                if max_duration:
                    if trim_video_ffmpeg(temp_raw, temp_trimmed, max_duration):
                        upload_path = temp_trimmed
                
                key = f"backgrounds/pexels_{video_id}_{uuid.uuid4().hex[:8]}.mp4"
                print(f"    Uploading to S3 ({os.path.getsize(upload_path)/1024/1024:.1f}MB)...")
                
                for attempt in range(3):
                    try:
                        with open(upload_path, "rb") as f:
                            s3.upload_fileobj(
                                f,
                                BUCKET_NAME,
                                key,
                                ExtraArgs={"ContentType": "video/mp4"},
                            )
                        break
                    except Exception as e:
                        print(f"    S3 Upload error ({attempt+1}/3): {e}")
                        if attempt == 2: raise e
                        time.sleep(2 ** attempt)

                presigned = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": BUCKET_NAME, "Key": key},
                    ExpiresIn=172800,  # 48h — safe window for TikTok manual uploads
                )
                urls.append(presigned)
                print(f"    ✓ Uploaded to S3 → Lambda will fetch at wire speed.")
            except Exception as e:
                print(f"  Pexels S3 upload failed for video {video_id}: {e} — skipping clip.")
            finally:
                for f in [temp_raw, temp_trimmed]:
                    if os.path.exists(f): os.remove(f)

        return urls

    except Exception as e:
        print(f"Pexels error for '{keyword}': {e}")
        return []


def _fetch_pixabay(keyword, num_clips, max_duration=None):
    """
    Fetch Pixabay videos for a keyword and mirror them to S3.
    Pixabay is a fallback for Pexels.
    """
    api_key = os.getenv("PIXABAY_API_KEY")
    if not api_key:
        return []

    # Pixabay vertical orientation uses orientation=vertical
    base_url = (
        f"https://pixabay.com/api/videos/"
        f"?key={api_key}&q={keyword}&video_type=film&orientation=vertical"
    )

    try:
        resp = requests.get(base_url, timeout=15).json()
        videos = resp.get("hits", [])

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
                    fresh_videos = videos
                videos = fresh_videos
            except Exception as e:
                print(f"  Pixabay dedup warning: {e}")

        random.shuffle(videos)

        s3 = boto3.client(
            "s3",
            region_name="us-east-1",
            config=Config(region_name="us-east-1", s3={"addressing_style": "virtual"}),
        )

        urls = []
        for video in videos[:num_clips]:
            if db:
                try:
                    db.table("used_clips").insert({
                        "file_id": str(video.get("id")),
                        "file_name": f"pixabay_{video.get('id')}",
                        "media_type": "pixabay_video"
                    }).execute()
                except Exception:
                    pass

            # Pixabay provides multiple sizes in 'videos' dict
            v_data = video.get("videos", {})
            # Prefer large/medium but ≤ 1080p
            chosen_data = v_data.get("large") or v_data.get("medium") or v_data.get("small") or v_data.get("tiny")
            
            if not chosen_data:
                continue

            cdn_url = chosen_data["url"]
            video_id = video.get("id", uuid.uuid4().hex)
            print(f"  Pixabay → S3: [{keyword}] video {video_id}")

            temp_raw = f"temp_raw_{uuid.uuid4().hex}.mp4"
            temp_trimmed = f"temp_trimmed_{uuid.uuid4().hex}.mp4"
            
            try:
                print(f"    Downloading raw b-roll from Pixabay...")
                for dl_attempt in range(3):
                    try:
                        with requests.get(cdn_url, stream=True, timeout=120) as r:
                            r.raise_for_status()
                            with open(temp_raw, "wb") as f:
                                for chunk in r.iter_content(chunk_size=8192):
                                    f.write(chunk)
                        break
                    except Exception as e:
                        print(f"    Download error ({dl_attempt+1}/3): {e}")
                        if dl_attempt == 2: raise e
                        time.sleep(2 ** dl_attempt)
                
                upload_path = temp_raw
                if max_duration:
                    if trim_video_ffmpeg(temp_raw, temp_trimmed, max_duration):
                        upload_path = temp_trimmed
                
                key = f"backgrounds/pixabay_{video_id}_{uuid.uuid4().hex[:8]}.mp4"
                print(f"    Uploading to S3 ({os.path.getsize(upload_path)/1024/1024:.1f}MB)...")
                
                for attempt in range(3):
                    try:
                        with open(upload_path, "rb") as f:
                            s3.upload_fileobj(
                                f,
                                BUCKET_NAME,
                                key,
                                ExtraArgs={"ContentType": "video/mp4"},
                            )
                        break
                    except Exception as e:
                        print(f"    S3 Upload error ({attempt+1}/3): {e}")
                        if attempt == 2: raise e
                        time.sleep(2 ** attempt)

                presigned = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": BUCKET_NAME, "Key": key},
                    ExpiresIn=172800,  # 48h — safe window for TikTok manual uploads
                )
                urls.append(presigned)
                print(f"    ✓ Uploaded to S3.")
            except Exception as e:
                print(f"  Pixabay S3 upload failed for video {video_id}: {e}")
            finally:
                for f in [temp_raw, temp_trimmed]:
                    if os.path.exists(f): os.remove(f)

        return urls

    except Exception as e:
        print(f"Pixabay error for '{keyword}': {e}")
        return []


def get_background_videos(topic, keyword, backup_keywords=None, num_clips=5, max_duration=None, segment_queries=None):
    """
    Route b-roll based on segment visual_queries + topic + Gemini keywords.

    HIERARCHY (Hazy Insight — visual sync):
    1. High-precision Segment Visual Queries (1:1 visual match per sentence)
    2. Primary Pexels keyword (AI-generated, page 1-5)
    3. Pixabay fallback (same keyword, fills remaining clips)
    4. AI Backup Keywords (Pexels first, then Pixabay)
    5. Premium AI Drive Folders (Science/History)
    6. Categorized Fallback Pool
    """
    # Cap at 10 — more clips = faster visual cuts for better retention
    num_clips = min(num_clips, 10)
    topic_lower = topic.lower()
    urls = []

    # PRO MOVE: Individual Clip Trimming Optimization
    # Each background clip only plays for `total_duration / num_clips` (e.g. 42s / 10 = 4.2s).
    # Trimming to this exact duration + 3s safety buffer significantly reduces download sizes,
    # memory usage, and CPU load inside AWS Lambda, preventing Puppeteer hangs.
    if max_duration:
        max_duration = (max_duration / num_clips) + 3.0

    # Route 1: High-precision Segment Visual Queries (Visual Sync)
    if segment_queries and isinstance(segment_queries, list):
        print(f"\n--- VISUAL SYNC: Fetching targeted b-roll for {len(segment_queries)} script segments ---")
        for q in segment_queries:
            if not q or len(urls) >= num_clips:
                break
            print(f"  Segment Query: '{q}'")
            seg_urls = _fetch_pexels(q, 1, max_duration=max_duration)
            if not seg_urls:
                seg_urls = _fetch_pixabay(q, 1, max_duration=max_duration)
            if seg_urls:
                urls.extend(seg_urls)

        if len(urls) >= num_clips:
            print(f"  ✓ Visual Sync Complete: {len(urls)} tailored segment clips acquired.")
            return urls[:num_clips]

    # Route 2: Primary Pexels keyword
    if len(urls) < num_clips:
        needed = num_clips - len(urls)
        more = _fetch_pexels(keyword, needed, max_duration=max_duration)
        urls.extend(more)
        if len(urls) >= num_clips:
            print(f"  Pexels primary hit: {keyword}")
            return urls[:num_clips]

    # Route 2b: Pixabay fallback for primary keyword
    if len(urls) < num_clips:
        needed = num_clips - len(urls)
        print(f"  Pexels thin ({len(urls)}/{num_clips}). Trying Pixabay for: {keyword}")
        pixabay_urls = _fetch_pixabay(keyword, needed, max_duration=max_duration)
        urls.extend(pixabay_urls)
        if len(urls) >= num_clips:
            return urls[:num_clips]

    # Route 3: AI backup keywords
    if backup_keywords:
        for bk in backup_keywords:
            remaining = num_clips - len(urls)
            # Try Pexels first for backup
            more = _fetch_pexels(bk, remaining, max_duration=max_duration)
            urls.extend(more)
            
            # If still need more, try Pixabay for this backup keyword
            if len(urls) < num_clips:
                needed = num_clips - len(urls)
                more_pix = _fetch_pixabay(bk, needed, max_duration=max_duration)
                urls.extend(more_pix)

            if len(urls) >= num_clips:
                print(f"  Pexels/Pixabay backup hit: {bk}")
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
            more = sync_drive_to_s3(SCIENCE_BROLL_FOLDER_ID, needed, "video", max_duration=max_duration)
            urls.extend(more)
            
        history_keywords = [
            "rome","history","ancient","medieval","war","knight","tomb","civilization","viking",
            "samurai","warrior","emperor","kingdom","artifact","museum","archaeology",
            "renaissance","napoleon","world war","dynasty","pharaoh","empire","temple","ruins","monarchy"
        ]
        if any(k in topic_lower for k in history_keywords):
            print(f"  History topic detected. Pulling {needed} clips from AI_History_Broll...")
            more = sync_drive_to_s3(HISTORY_BROLL_FOLDER_ID, needed, "video", max_duration=max_duration)
            urls.extend(more)
            
        else:
            # If it's a general topic, use curated fallback keywords on Pexels first
            fallback_kw = random.choice(FALLBACK_NATURE)
            more = _fetch_pexels(fallback_kw, needed, max_duration=max_duration)
            urls.extend(more)

    if len(urls) >= num_clips:
        return urls[:num_clips]

    # Route 5: Last resort -> Randomize Premium Pexels Collections
    needed = num_clips - len(urls)
    if needed > 0:
        print(f"  Flow exhausted. Using premium Pexels last resort...")
        # Combine fallback pools for maximum premium variety
        premium_fallbacks = FALLBACK_NATURE + FALLBACK_SCIENCE + FALLBACK_HISTORY
        fallback_kw = random.choice(premium_fallbacks)
        print(f"  Selected Pexels Premium ({fallback_kw}) as last resort.")
        more = _fetch_pexels(fallback_kw, needed, max_duration=max_duration)
        urls.extend(more)

    return urls[:num_clips]


def get_sfx_urls(num_sfx=7):
    """Fetch SFX pool — request 7 so Composition can match by filename keyword."""
    print("Fetching SFX pool from Drive...")
    return sync_drive_to_s3(SFX_FOLDER, num_sfx, "audio")


def get_bgm_url(category="general"):
    """
    Route BGM. All categories use the GENERAL_BGM_FOLDER.
    """
    folder = GENERAL_BGM_FOLDER
    if not folder:
        print(f"No BGM folder for '{category}'. Skipping.")
        return None
    print(f"Fetching {category} BGM...")
    urls = sync_drive_to_s3(folder, 1, "audio")
    return urls[0] if urls else None