import os
import sys
import time
import requests
import random
import traceback
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client

# Force console output to UTF-8 to prevent Windows CP1252 UnicodeEncodeError crashing the script
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

# --- SECURITY & SANITY CHECKS ------------------------------------------------
ALLOWED_RENDER_DOMAINS = [
    "s3.amazonaws.com",          # generic AWS S3
    "s3.us-east-1.amazonaws.com",
    "s3.us-west-2.amazonaws.com",
    "remotion-render",           # direct lambda testing
]

def validate_render_url(url):
    """Ensure the render download URL is from a trusted domain."""
    if not url:
        return False
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    # Check if any allowed domain is in the netloc
    return any(allowed in domain for allowed in ALLOWED_RENDER_DOMAINS)

def check_environment():
    """Verify critical environment variables are present before starting."""
    required = [
        "GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY", 
        "BUCKET_NAME", "SERVE_URL", "PARKOUR_FOLDER_ID",
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"
    ]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"FATAL: Missing environment variables: {missing}")
        sys.exit(1)
    print("Environment check passed.")

# -----------------------------------------------------------------------------

check_environment()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

from src.ai.brain import generate_full_package
from src.ai.tts import generate_voiceover
from src.media.assets import get_background_videos, get_sfx_urls, get_bgm_url
from src.media.builder import make_cloud_video
from src.api.youtube import upload_video
from src.utils.discord import ping_creator, ping_error, ping_render_start, ping_queue

def produce_video(category, local_excludes=None):
    print(f"\n--- STARTING PRODUCTION FOR CATEGORY: {category.upper()} ---")

    try:
        full_package = generate_full_package(category, local_excludes=local_excludes)
        
        topic = full_package['topic']
        search_keyword = full_package['search_keyword']
        viral_package = full_package

        print(f"Topic acquired: {topic}")
        print(f"B-Roll Keyword: {search_keyword}")

    except Exception as e:
        msg = f"Gemini Error: {str(e)}"
        tb = traceback.format_exc()
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini Factory", traceback_str=tb)
        return None, None, False

    full_audio_script = " ".join([s['voiceover'] for s in viral_package['segments']])

    audio_url, duration, voice_error = generate_voiceover(full_audio_script)
    if not audio_url:
        print("\nFACTORY HALTED: Voiceover generation failed.")
        ping_error(str(voice_error), "ElevenLabs")
        return None, None, False

    video_urls = get_background_videos(
        topic,
        search_keyword,
        backup_keywords=viral_package.get('backup_keywords'),
        num_clips=3   # 3 clips = 3 visual cuts = 70%+ retention
    )
    sfx_urls = get_sfx_urls(num_sfx=max(7, len(viral_package['segments'])))

    bgm_url = get_bgm_url(category=category)

    # Prevent AWS Lambda waste if local Google Drive API times out (WinError 10060)
    if not video_urls or not sfx_urls or not bgm_url:
        err = f"FACTORY HALTED: Local Media Fetch Failed. Missing assets. Videos: {len(video_urls)}, SFX: {len(sfx_urls)}, BGM: {'Yes' if bgm_url else 'No'}."
        print(f"\n{err}")
        ping_error(err, "Local Google API")
        return None, None, False

    render_seed = int(time.time())
    ping_render_start(viral_package['title'])
    final_video_url, render_error = make_cloud_video(
        audio_url,
        video_urls,
        sfx_urls,
        bgm_url,
        viral_package['segments'],
        duration,
        category=category,
        render_seed=render_seed
    )

    if final_video_url:
        print(f"\nSUCCESS! RENDER COMPLETE:\n{final_video_url}")

        if not validate_render_url(final_video_url):
            err = f"SECURITY ALERT: Blocked insecure render download from untrusted domain: {final_video_url}"
            print(f"\n{err}")
            ping_error(err, "Security Manager")
            return None, None, False

        local_filename = f"temp_render_{category}.mp4"
        for attempt in range(3):
            try:
                r = requests.get(final_video_url, stream=True, timeout=60)
                r.raise_for_status()
                with open(local_filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                break
            except Exception as e:
                print(f"Download error: {e}. Retrying {attempt+1}/3...")
                time.sleep(3)
                if attempt == 2:
                    ping_error(f"Render download failed after 3 attempts: {e}", "Downloader")
                    return None, None, False

        print("\n[STEP 1/2] Initiating YouTube Upload...")
        youtube_link = upload_video(
            local_filename,
            viral_package['title'],
            viral_package['description'],
            category,
            tags=viral_package.get('tags')
        )

        tiktok_status = "Skipped"

        if youtube_link:
            try:
                video_id = youtube_link.split("/")[-1]
                for attempt in range(3):
                    try:
                        supabase.table("videos").update({"youtube_id": video_id})\
                            .eq("topic", full_package['topic']).execute()
                        print(f"Supabase updated with youtube_id: {video_id}")
                        break
                    except Exception as e:
                        if attempt == 2: raise e
                        time.sleep(2)
            except Exception as e:
                print(f"Warning: Failed to save youtube_id to Supabase: {e}")

        # [STEP 2/2] TikTok queuing
        tiktok_status = "QUEUED"
        print("\n[STEP 2/2] Adding video to TikTok retry queue...")
        
        try:
            tags = viral_package.get('tags')
            hashtags = " ".join(f"#{t}" for t in tags) if tags else "#shorts #gaming #facts"
            tiktok_description = f"{viral_package['title']}\n\n{viral_package['description'][:1400]}\n\n{hashtags}"[:2200]

            tiktok_payload = {
                "tiktok_status":    "PENDING",
                "s3_video_url":     final_video_url,
                "tiktok_description": tiktok_description
            }

            # Try update first (row should exist from brain.py insert)
            result = supabase.table("videos").update(tiktok_payload).eq("topic", full_package['topic']).execute()

            # If no rows matched, the brain.py insert was skipped — insert the row now
            if not result.data:
                print("  Row not found — inserting new Supabase record.")
                supabase.table("videos").insert({
                    "topic": full_package['topic'],
                    "title": viral_package['title'],
                    **tiktok_payload
                }).execute()

            print("Supabase updated with TikTok metadata.")
        except Exception as e:
            print(f"Warning: Failed to queue for TikTok: {e}")
            tiktok_status = "FAILED"
        
        ping_creator(youtube_link or "Upload Failed", tiktok_status, "N/A", viral_package['title'])

        if os.path.exists(local_filename):
            os.remove(local_filename)
        print(f"Local temp file deleted. {category.upper()} Syndication Cycle Complete!")
        
        title = viral_package['title']
        was_queued = (tiktok_status == "QUEUED")
        return topic, title, was_queued
    else:
        # render_error may be a raw Python list from the Remotion SDK (its 'errors' field).
        # str(list) can produce 10,000+ characters — Discord rejects messages >2000 chars
        # with a silent HTTP 400, which is swallowed by _post()'s exception handler.
        # Always coerce to a capped string before pinging.
        safe_render_err = str(render_error or "Remotion render returned None")[:1200]
        print(f"\nRender failed: {safe_render_err}. Check AWS CloudWatch logs.")
        ping_error(safe_render_err, "AWS Lambda")
        return None, None, False

def start_factory():
    print("HAZY CHANEL AUTOMATION STARTING SINGLE SHIFT...\n" + "="*40)
    
    categories = ["gaming", "general"]
    today_shift = random.choice(categories)
    print(f"Today's Shift: {today_shift.upper()}\n")

    overall_success = True
    try:
        queued_titles = []
        
        print(f"--- SHIFT: {today_shift.upper()} ---")
        produced_topics = []
        try:
            topic1, title1, q1 = produce_video(today_shift, local_excludes=produced_topics)
            if topic1:
                produced_topics.append(topic1)
                if q1: 
                    queued_titles.append(title1)
            else:
                overall_success = False
        except Exception as e:
            print(f"Shift Fatal: {e}")
            ping_error(f"Shift crashed: {e}", "Orchestrator")
            overall_success = False
            
        # Always notify about the queue state — ping_queue queries Supabase for ALL
        # PENDING videos, so even when the render failed and nothing new was queued
        # this run, the user is reminded of any videos still waiting for upload.
        ping_queue(queued_titles)
        
    except Exception as e:
        err_msg = f"Fatal Orchestrator Failure: {str(e)}"
        tb = traceback.format_exc()
        print(f"\nFATAL ERROR: {err_msg}\n{tb}")
        ping_error(err_msg, "Orchestrator", traceback_str=tb)
        overall_success = False

    if not overall_success:
        print("\nFACTORY SHUTDOWN WITH ERRORS. Check logs above.")
        sys.exit(1)
    
    print("\nFACTORY SHUTTING DOWN. ALL TASKS COMPLETE!")

if __name__ == "__main__":
    start_factory()