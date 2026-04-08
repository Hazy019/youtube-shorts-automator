import os
import sys

# Force console output to UTF-8 to prevent Windows CP1252 UnicodeEncodeError crashing the script
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import time
import requests
import random
import traceback
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

from src.ai.brain import generate_full_package
from src.ai.tts import generate_voiceover
from src.media.assets import get_background_videos, get_sfx_urls, get_bgm_url
from src.media.builder import make_cloud_video
from src.api.youtube import upload_video
from src.api.tiktok import upload_to_tiktok
from src.utils.discord import ping_creator, ping_error, ping_render_start, ping_queue

def produce_video(category, local_excludes=None):
    print(f"\n--- STARTING PRODUCTION FOR CATEGORY: {category.upper()} ---")

    try:
        full_package = generate_full_package(category, local_excludes=local_excludes)
        
        topic = full_package['topic']
        keyword = full_package['search_keyword']
        viral_package = full_package

        print(f"Topic acquired: {topic}")
        print(f"B-Roll Keyword: {keyword}")

    except Exception as e:
        msg = f"Gemini Error: {str(e)}"
        tb = traceback.format_exc()
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini Factory", traceback_str=tb)
        return False

    full_audio_script = " ".join([s['voiceover'] for s in viral_package['segments']])

    audio_url, duration, voice_error = generate_voiceover(full_audio_script)
    if not audio_url:
        print("\nFACTORY HALTED: Voiceover generation failed.")
        ping_error(str(voice_error), "ElevenLabs")
        return False

    video_urls = get_background_videos(topic, keyword, num_clips=3)
    sfx_urls = get_sfx_urls(num_sfx=len(viral_package['segments']))

    bgm_url = get_bgm_url(category=category)

    # Prevent AWS Lambda waste if local Google Drive API times out (WinError 10060)
    if not video_urls or not sfx_urls or not bgm_url:
        err = f"FACTORY HALTED: Local Media Fetch Failed. Missing assets. Videos: {len(video_urls)}, SFX: {len(sfx_urls)}, BGM: {'Yes' if bgm_url else 'No'}."
        print(f"\n{err}")
        ping_error(err, "Local Google API")
        return False

    render_seed = int(time.time())
    ping_render_start(viral_package['title'])
    final_video_url = make_cloud_video(
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

        local_filename = f"temp_render_{category}.mp4"
        r = requests.get(final_video_url, stream=True)
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)

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
                supabase.table("videos").update({"youtube_id": video_id})\
                    .eq("topic", full_package['topic']).execute()
                print(f"Supabase updated with youtube_id: {video_id}")
            except Exception as e:
                print(f"Warning: Failed to save youtube_id to Supabase: {e}")

            delay_tt = random.randint(45, 90)
            print(f"\n[STEP 2/2] Waiting {delay_tt}s for TikTok syndication (anti-bot stagger)...")
            time.sleep(delay_tt)

            tt_result = upload_to_tiktok(
                local_filename,
                viral_package['title'],
                viral_package['description'],
                tags=viral_package.get('tags')
            )
            
            if tt_result:
                tiktok_status = "SUCCESS"
                print(f"TikTok Upload Status: {tiktok_status}")
            else:
                tiktok_status = "FAILED"
                print(f"TikTok Upload Status: {tiktok_status} (Check logs/Discord for errors)")
                try:
                    tags = viral_package.get('tags')
                    hashtags = " ".join(f"#{t}" for t in tags) if tags else "#shorts #gaming #facts"
                    tiktok_desc = f"{viral_package['title']}\n\n{viral_package['description'][:1400]}\n\n{hashtags}"[:2200]
                    supabase.table("videos").update({
                        "tiktok_status": "PENDING", 
                        "s3_video_url": final_video_url,
                        "tiktok_description": tiktok_desc
                    }).eq("topic", full_package['topic']).execute()
                    print(f"TikTok upload queued in Supabase for retry.")
                except Exception as e:
                    print(f"Warning: Failed to queue TikTok upload in Supabase (Did you add the columns?): {e}")

            ping_creator(youtube_link, tiktok_status, "N/A", viral_package['title'])

        if os.path.exists(local_filename):
            os.remove(local_filename)
        print(f"Local temp file deleted. {category.upper()} Syndication Cycle Complete!")
        
        was_queued = (tiktok_status == "PENDING")
        return topic, was_queued
    else:
        print("\nRender failed. Check AWS CloudWatch logs.")
        ping_error("Remotion render returned None", "AWS Lambda")
        return None, False

def start_factory():
    print("HAZY CHANEL AUTOMATION STARTING RANDOMIZED DOUBLE SHIFT...\n" + "="*40)
    
    categories = ["gaming", "general"]
    today_shift = [random.choice(categories) for _ in range(2)]
    print(f"Today's Shift: {today_shift[0].upper()} then {today_shift[1].upper()}\n")

    overall_success = True
    try:
        shift_history = []
        queued_count = 0
        
        print(f"--- SHIFT 1: {today_shift[0].upper()} ---")
        topic1, q1 = produce_video(today_shift[0])
        if topic1:
            shift_history.append(topic1)
            if q1: queued_count += 1
        else:
            overall_success = False
        
        print(f"\nTaking a 70-second break before the second video ({today_shift[1].upper()}) to clear Gemini RPM limits...")
        time.sleep(70)
        
        print(f"--- SHIFT 2: {today_shift[1].upper()} ---")
        topic2, q2 = produce_video(today_shift[1], local_excludes=shift_history)
        if topic2:
            if q2: queued_count += 1
        else:
            overall_success = False
            
        if queued_count > 0:
            ping_queue(queued_count)
        
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