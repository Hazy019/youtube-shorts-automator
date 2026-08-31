import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import requests
import traceback
import boto3
from urllib.parse import urlparse
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Reverting to library-based imports
from src.api.tiktok import upload_to_tiktok, _cleanup, _prepare_cookies, _validate_netscape, _do_tiktok_upload
from src.utils.discord import ping_error, ping_tiktok_success, ping_queue_completed

def _get_supabase() -> Client | None:
    try:
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            return create_client(url, key)
    except Exception as e:
        print(f"Supabase init failed: {e}")
    return None

from src.utils.s3_helper import download_s3_or_http_file, delete_s3_file_by_url

def download_video(url: str, output_path: str) -> bool:
    print(f"Downloading video from: {url[:60]}...")
    return download_s3_or_http_file(url, output_path)

def delete_s3_video(url: str):
    """Delete the video from AWS S3."""
    print(f"  ACTION: Deleting video from S3...")
    if delete_s3_file_by_url(url):
        print("  ✓ S3 Cleanup successful.")
    else:
        print("  ⚠ S3 Cleanup skipped or failed.")

def drain_tiktok_queue():
    print("="*40)
    print("TIKTOK SUPABASE RETRY QUEUE MANAGER (LIBRARY VERSION)")
    print("="*40)
    
    db = _get_supabase()
    if not db:
        print("FATAL: Could not connect to Supabase.")
        return

    # Fetch queued items (Newest first so fresh renders are uploaded immediately)
    try:
        resp = db.table("videos").select("Topic:topic, id, s3_video_url, tiktok_description")\
                .eq("tiktok_status", "PENDING")\
                .order("id", desc=True)\
                .execute()
    except Exception as e:
        print(f"Supabase query failed: {e}")
        return
        
    queue = resp.data
    if not queue:
        print("Queue is empty! No pending TikTok uploads found.")
        return
        
    # PRO MOVE: Limit posts per run to protect account reputation and avoid shadowbans.
    MAX_POSTS_PER_RUN = 3 
    if len(queue) > MAX_POSTS_PER_RUN:
        print(f"Found {len(queue)} pending, but LIMITING to {MAX_POSTS_PER_RUN} for account safety.")
        queue = queue[:MAX_POSTS_PER_RUN]
    else:
        print(f"Found {len(queue)} pending TikTok uploads in the queue.\n")

    total_uploaded = 0

    for i, item in enumerate(queue):
        video_id = item.get("id")
        topic = item.get("Topic")
        s3_url = item.get("s3_video_url")
        desc = item.get("tiktok_description")
        
        print(f"\n--- Processing {i+1}/{len(queue)}: {topic} (ID: {video_id}) ---")
        if not s3_url:
            print(f"  [SKIP] No S3 video URL found for this topic. Record may be incomplete.")
            continue
        if not desc:
            print(f"  [SKIP] No TikTok description found for this topic.")
            continue
            
        temp_dir = ".temp"
        os.makedirs(temp_dir, exist_ok=True)
        local_filename = os.path.join(temp_dir, f"queue_render_{video_id}.mp4")
        
        # 1. Download
        print(f"  ACTION: Downloading video from S3...")
        if not download_video(s3_url, local_filename):
            print(f"  [ERROR] Video file does not exist in S3 (lifecycle expired). Marking as EXPIRED_ASSET.")
            try:
                db.table("videos").update({"tiktok_status": "EXPIRED_ASSET"}).eq("id", video_id).execute()
            except Exception as e:
                print(f"  Failed to update status in Supabase: {e}")
            continue
            
        # 2. Upload
        while True:
            try:
                import threading
                from src.api.tiktok import _do_tiktok_upload, _PROFILE_DIR

                has_persistent = os.path.exists(_PROFILE_DIR) and len(os.listdir(_PROFILE_DIR)) > 0
                cookies_path = _prepare_cookies() if not has_persistent else None

                if not has_persistent and (not cookies_path or not _validate_netscape(cookies_path)):
                    print("FATAL: No valid TikTok session found. Run 'tools/setup_tiktok_session.py' or provide cookies.")
                    break

                if has_persistent:
                    print(f"Launching LOCAL browser with permanent profile (.tiktok_profile)...")
                else:
                    print(f"Launching LOCAL stealth browser with backup cookies...")

                thread_result = None
                thread_err = None

                def _run_sync_upload():
                    nonlocal thread_result, thread_err
                    try:
                        # _do_tiktok_upload handles:
                        #   - asyncio.new_event_loop() isolation (no Playwright async crash)
                        #   - Chrome/124 UA (not Chrome/58 from library config.toml)
                        #   - Cookies injected BEFORE navigation
                        #   - complete_upload_form() called directly (bypasses broken TikTokUploader.page property)
                        thread_result = _do_tiktok_upload(local_filename, desc, headless=False)
                    except Exception as e:
                        thread_err = e

                upload_thread = threading.Thread(target=_run_sync_upload)
                upload_thread.start()
                upload_thread.join()

                if thread_err: raise thread_err
                result = thread_result
                
                if isinstance(result, list) and len(result) > 0:
                    print(f"[RETRY ERROR] {result[0]}")
                    raise Exception(f"Upload returned error: {result[0]}")
                else:
                    # 3. Mark Success
                    print(f"SUCCESS! Uploaded {topic}")
                    db.table("videos").update({"tiktok_status": "SUCCESS"}).eq("id", video_id).execute()
                    total_uploaded += 1
                    ping_tiktok_success(topic)
                    
                    # S3 PURGE: Delete from AWS now that it's on TikTok
                    delete_s3_video(s3_url)
                    break # Exit retry loop on success
                    
            except Exception as e:
                print(f"Upload flow crashed for {topic}: {e}")
                traceback.print_exc()
                
                # INTERACTIVE RECOVERY
                print("\n" + "="*50)
                print("⚠ UPLOAD FAILED OR BLOCKED BY UI ⚠")
                print("Possible reasons: 'react-joyride' popup, captcha, or network issue.")
                print("="*50)
                import time
                ans = input("Do you want to [R]etry, [S]kip this video, or [A]bort queue? (r/s/a): ").strip().lower()
                
                if ans == 'r':
                    print("Retrying upload for the same video...")
                    time.sleep(2)
                    continue
                elif ans == 'a':
                    print("Aborting queue processing.")
                    if os.path.exists(local_filename):
                        try: os.remove(local_filename)
                        except: pass
                    return # Exit the whole function
                else:
                    print("Skipping this video.")
                    break # Exit retry loop, move to next video in queue
            
        if os.path.exists(local_filename):
            try: os.remove(local_filename)
            except: pass
                
    if total_uploaded > 0:
        ping_queue_completed(total_uploaded)
                
    _cleanup()
    print("\nQueue Manager finished processing.")

if __name__ == "__main__":
    drain_tiktok_queue()
