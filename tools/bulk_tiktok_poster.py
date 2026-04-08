import os
import requests
import traceback
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# We can safely import Tk_uploader here
from tk_uploader import upload_to_tiktok, _cleanup
from discord_bot import ping_error

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
        r = requests.get(url, stream=True)
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
        print(f"Supabase query failed (Are the columns added?): {e}")
        return
        
    queue = resp.data
    if not queue:
        print("Queue is empty! No pending TikTok uploads found.")
        return
        
    print(f"Found {len(queue)} pending TikTok uploads in the queue.\n")

    for i, item in enumerate(queue):
        video_id = item.get("id")
        topic = item.get("Topic")
        s3_url = item.get("s3_video_url")
        desc = item.get("tiktok_description")
        
        print(f"--- Processing {i+1}/{len(queue)}: {topic} ---")
        if not s3_url or not desc:
            print("Missing s3_url or description in database. Skipping.")
            continue
            
        local_filename = f"queue_render_{video_id}.mp4"
        
        # 1. Download
        if not download_video(s3_url, local_filename):
            continue
            
        # 2. Upload
        # To avoid duplicating the caption building logic in tk_uploader, 
        # tk_uploader expects title, description, and tags. 
        # But we already baked the entire caption into the database's `tiktok_description`!
        # So we can pass it as the "description" and leave title blank, or vice versa, but tk_uploader
        # modifies it. Let's just pass the pre-baked description as the description, title empty, tags empty,
        # and it will safely format it. But wait, tk_uploader says: f"{title}\n\n{description}\n\n{hashtags}"
        # We can bypass tk_uploader and call upload_video directly here for full control over the caption!
        
        try:
            import threading
            from tiktok_uploader.upload import upload_video
            
            # Use same resolve logic from tk_uploader for cookies
            from tk_uploader import _prepare_cookies, _validate_netscape
            
            cookies_path = _prepare_cookies()
            if not cookies_path or not _validate_netscape(cookies_path):
                print("FATAL: Invalid or missing TikTok Cookies. Stop to fix cookies.")
                break
                
            thread_result = None
            thread_err = None
            
            # Since user runs this manually locally, headless is ALWAYS False so they can solve captchas
            is_headless = False
            
            def _run_upload():
                nonlocal thread_result, thread_err
                try:
                    thread_result = upload_video(
                        local_filename,
                        description=desc,
                        cookies=cookies_path,
                        headless=is_headless,
                    )
                except Exception as e:
                    thread_err = e
            
            print(f"Launching LOCAL browser (captcha manual solving enabled)...")
            t = threading.Thread(target=_run_upload)
            t.start()
            t.join()
            
            if thread_err:
                raise thread_err
                
            result = thread_result
            
            if isinstance(result, list) and len(result) > 0:
                print(f"[RETRY ERROR] {result[0]}")
                print("TikTok blocked the upload again. Retaining in PENDING status.")
            else:
                # 3. Mark Success
                print(f"SUCCESS! Uploaded {topic}")
                db.table("videos").update({"tiktok_status": "SUCCESS"}).eq("id", video_id).execute()
                print("Marked as SUCCESS in Supabase.")
                
        except Exception as e:
            print(f"Upload flow crashed: {e}")
            traceback.print_exc()
            break
            
        finally:
            if os.path.exists(local_filename):
                os.remove(local_filename)
                
    _cleanup()
    print("\nQueue Manager finished processing.")

if __name__ == "__main__":
    drain_tiktok_queue()
