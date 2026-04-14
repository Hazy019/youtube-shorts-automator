import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import requests
import traceback
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# We can safely import Tk_uploader here
from src.api.tiktok import upload_to_tiktok, _cleanup
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

def download_video(url: str, output_path: str) -> bool:
    print(f"Downloading from S3: {url[:60]}...")
    try:
        r = requests.get(url, stream=True, timeout=(10, 120))
        r.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"Failed to download video: {e}")
        return False

def drain_tiktok_queue():
    print("="*40)
    print("TIKTOK SUPABASE RETRY QUEUE MANAGER")
    print("="*40)
    
    db = _get_supabase()
    if not db:
        print("FATAL: Could not connect to Supabase.")
        return

    # Fetch queued items
    try:
        resp = db.table("videos").select("Topic:topic, id, s3_video_url, tiktok_description")\
                .eq("tiktok_status", "PENDING").execute()
    except Exception as e:
        err_str = str(e)
        if "42703" in err_str or "s3_video_url" in err_str:
            print("\n[ERROR] Supabase Schema Mismatch!")
            print("Your 'videos' table is missing the 's3_video_url' column.")
            print("Please run the SQL command provided in the implementation plan to update your database.")
        else:
            print(f"Supabase query failed: {e}")
        return
        
    queue = resp.data
    if not queue:
        print("Queue is empty! No pending TikTok uploads found.")
        return
        
    print(f"Found {len(queue)} pending TikTok uploads in the queue.\n")

    # Step 1: Batch Download
    videos_to_upload = []
    video_map = {} # path -> {id, topic}
    
    temp_dir = ".temp"
    os.makedirs(temp_dir, exist_ok=True)

    for item in queue:
        video_id = item.get("id")
        topic = item.get("Topic")
        s3_url = item.get("s3_video_url")
        desc = item.get("tiktok_description")
        
        if not s3_url or not desc:
            continue
            
        local_filename = os.path.abspath(os.path.join(temp_dir, f"queue_render_{video_id}.mp4"))
        
        if download_video(s3_url, local_filename):
            videos_to_upload.append({
                "path": local_filename,
                "description": desc
            })
            video_map[local_filename] = {"id": video_id, "topic": topic}

    if not videos_to_upload:
        print("No videos successfully downloaded. Aborting.")
        return

    print(f"\nDownloaded {len(videos_to_upload)} videos. Starting batch upload...")

    # Step 2: Batch Upload
    try:
        from tiktok_uploader.upload import upload_videos
        from src.api.tiktok import _prepare_cookies, _validate_netscape
        
        cookies_path = _prepare_cookies()
        if not cookies_path or not _validate_netscape(cookies_path):
            print("FATAL: Invalid or missing TikTok Cookies.")
            return

        thread_result = None
        thread_err = None
        
        def _run_upload():
            nonlocal thread_result, thread_err
            try:
                # Returns a list of FAILED videos
                thread_result = upload_videos(
                    videos_to_upload,
                    cookies=cookies_path,
                    headless=False, # User is local, needs to solve captchas
                )
            except Exception as e:
                thread_err = e
        
        print(f"Launching BATCH browser session (keep window open for all posts)...")
        import threading
        t = threading.Thread(target=_run_upload)
        t.start()
        t.join()
        
        if thread_err:
            raise thread_err
            
        failed_videos = thread_result or []
        failed_paths = {v.get("path") for v in failed_videos if v.get("path")}

        # Step 3: Process Results
        total_uploaded = 0
        for video in videos_to_upload:
            path = video["path"]
            info = video_map.get(path)
            if not info: continue
            
            if path in failed_paths:
                print(f"FAILED: {info['topic']} (Retaining in PENDING for manual retry)")
            else:
                print(f"SUCCESS: {info['topic']}")
                db.table("videos").update({"tiktok_status": "SUCCESS"}).eq("id", info["id"]).execute()
                total_uploaded += 1
                ping_tiktok_success(info["topic"])

        if total_uploaded > 0:
            ping_queue_completed(total_uploaded)

    except Exception as e:
        err_msg = f"Bulk upload flow crashed: {e}"
        print(err_msg)
        traceback.print_exc()
        ping_error(err_msg, "TikTok Bulk Poster")
    
    finally:
        # Cleanup
        for video in videos_to_upload:
            p = video["path"]
            if os.path.exists(p):
                try: os.remove(p)
                except: pass
                
    _cleanup()
    print("\nQueue Manager finished processing.")
    if total_uploaded > 0:
        ping_queue_completed(total_uploaded)

if __name__ == "__main__":
    drain_tiktok_queue()
