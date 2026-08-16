import os
import time
import requests
from dotenv import load_dotenv
from src.utils.discord import ping_error

load_dotenv()

# A persistent session with a browser-like User-Agent avoids Meta's
# bot-detection heuristics that silently kill API-sourced containers.
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
})

class MetaAPI:
    def __init__(self):
        # Brutally clean env parsing to prevent malformed URLs
        self.access_token = os.getenv("META_PAGE_ACCESS_TOKEN", "").strip(' \t\n\r"')
        self.page_id = os.getenv("META_PAGE_ID", "").strip(' \t\n\r"')
        self.ig_id = os.getenv("META_INSTAGRAM_ID", "").strip(' \t\n\r"')
        self.base_url = "https://graph.facebook.com/v25.0"

    def upload_facebook_reel(self, video_url, description):
        """
        Uploads a Reel to Facebook Page using the 3-step process.
        """
        print(f"🚀 Starting Facebook Reel upload: {description[:30]}...")
        
        # ---------------------------------------------------------
        # Step 1: Initialize
        # ---------------------------------------------------------
        init_url = f"{self.base_url}/{self.page_id}/video_reels"
        init_payload = {
            "upload_phase": "start",
            "access_token": self.access_token
        }
        init_req = _SESSION.post(init_url, data=init_payload)
        init_res = init_req.json()
        
        if "video_id" not in init_res:
            print(f"[FAIL] FB Init Failed: {init_res}")
            return None
        
        video_id = init_res["video_id"]
        upload_url = init_res.get("upload_url")
        print(f"[OK] FB Init Success. Video ID: {video_id}")

        # ---------------------------------------------------------
        # Step 2: Upload Binary
        # ---------------------------------------------------------
        if not upload_url:
            print("[FAIL] FB Upload URL missing from init response.")
            return None
            
        try:
            # Stream download in chunks — avoids loading 50MB+ into RAM
            print(f"    Downloading video from S3 for Facebook upload...")
            video_data = b""
            for dl_attempt in range(3):
                try:
                    with requests.get(video_url, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        for chunk in r.iter_content(chunk_size=8192):
                            video_data += chunk
                    break
                except Exception as e:
                    print(f"    FB download error (attempt {dl_attempt+1}/3): {e}")
                    if dl_attempt == 2:
                        raise e
                    time.sleep(2 ** dl_attempt)

            headers = {
                "Authorization": f"OAuth {self.access_token}",
                "offset": "0",
                "file_size": str(len(video_data)),
                "Content-Type": "application/octet-stream"
            }
            upload_res = _SESSION.post(upload_url, data=video_data, headers=headers)
            upload_json = upload_res.json()
            
            if not upload_json.get("success"):
                print(f"[FAIL] FB Binary Upload Failed: {upload_json}")
                return None
            print("[OK] FB Binary Upload Success.")
        except Exception as e:
            print(f"[FAIL] FB Upload Exception: {e}")
            return None

        # ---------------------------------------------------------
        # Step 3: Publish (with retry on code 1 = still processing)
        # ---------------------------------------------------------
        # NOTE: Facebook Reels use rupload.facebook.com which does NOT expose
        # a 'ready' transition via GET /{video_id}?fields=status.
        # The correct approach is to attempt upload_phase=finish immediately
        # after binary upload and retry when code=1 (still processing).
        publish_url = f"{self.base_url}/{self.page_id}/video_reels"
        publish_payload = {
            "upload_phase": "finish",
            "video_id": video_id,
            "description": description,
            "video_state": "PUBLISHED",
            "access_token": self.access_token
        }
        
        # Wait an initial 20s for Facebook to begin processing
        print("⏳ Waiting 20s for Facebook to begin processing...")
        time.sleep(20)
        
        max_publish_retries = 8  # 8 * 30s = 4 minutes max
        for attempt in range(max_publish_retries):
            publish_req = _SESSION.post(publish_url, data=publish_payload)
            publish_res = publish_req.json()
            
            if publish_res.get("success"):
                print("🎉 Facebook Reel Published successfully!")
                return video_id
                
            err = publish_res.get("error", {})
            err_code = err.get("code")
            err_msg = err.get("message", "")
            
            # Robust check for video processing state.
            # Meta can return various phrasings:
            # - "Your video is still being processed. Please try again later."
            # - "Your video is still processing."
            # - Error code 1
            is_processing = (
                err_code == 1 or
                err_code == 9007 or
                "processing" in err_msg.lower() or
                "processed" in err_msg.lower() or
                "try again later" in err_msg.lower()
            )
            
            if is_processing:
                print(f"⏳ FB still processing (Code {err_code}: {err_msg}) — backing off 30s... (Attempt {attempt+1}/{max_publish_retries})")
                time.sleep(30)
                continue
                
            print(f"[FAIL] FB Publish Failed (non-retryable): {publish_res}")
            return None
            
        print("[FAIL] FB Publish timed out after all retry attempts.")
        return None

    def upload_instagram_reel(self, video_url, caption):
        """
        Uploads a Reel to Instagram Business Account.
        Requires a public video_url (S3).
        """
        if not self.ig_id:
            print("  ℹ️  Instagram upload skipped: META_INSTAGRAM_ID is not configured.")
            return None

        print(f"🚀 Starting Instagram Reel upload: {caption[:30]}...")
        
        # Step 1: Create Container
        container_url = f"{self.base_url}/{self.ig_id}/media"
        container_payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self.access_token
        }
        container_req = _SESSION.post(container_url, data=container_payload)
        container_res = container_req.json()
        
        if "id" not in container_res:
            print(f"[FAIL] IG Container Creation Failed: {container_res}")
            return None
        
        creation_id = container_res["id"]
        print(f"[OK] IG Container Created: {creation_id}. Waiting for processing...")

        # Step 2: Wait for Instagram to hydrate the container on their servers.
        # Polling too fast after creation is the #1 cause of Ghost Container errors.
        print("⏳ Warming up — waiting 30s for IG to register container...")
        time.sleep(30)

        # Step 3: Poll for status with exponential backoff on Ghost Container errors
        max_retries = 24  # 24 polls with growing waits = up to ~8 minutes max
        status_url = f"{self.base_url}/{creation_id}"
        ghost_count = 0
        for i in range(max_retries):
            status_req = _SESSION.get(status_url, params={"fields": "status_code", "access_token": self.access_token})
            status_res = status_req.json()
            status = status_res.get("status_code")
            
            if status == "FINISHED":
                print("[OK] IG Processing Finished.")
                break
            elif status == "ERROR":
                print(f"[FAIL] IG Processing Error: {status_res}")
                return None
            elif "error" in status_res:
                err = status_res["error"]
                if err.get("code") == 100 and err.get("error_subcode") == 33:
                    ghost_count += 1
                    # Exponential backoff: 15s, 20s, 25s ... capped at 45s
                    backoff = min(15 + ghost_count * 5, 45)
                    print(f"⏳ IG Container not yet visible (Ghost) — backing off {backoff}s... ({i+1}/{max_retries})")
                    if ghost_count > 15:
                        print(f"[FAIL] Container {creation_id} permanently rejected by Meta. Aborting to save tokens.")
                        ping_error(f"IG Ghost Container after {ghost_count} attempts: {creation_id}", "Instagram Upload")
                        return None
                    time.sleep(backoff)
                    continue
                else:
                    print(f"[FAIL] Unexpected IG API Error during polling: {err}")
                    return None
            else:
                print(f"⏳ IG Status: {status}... ({i+1}/{max_retries})")
            
            time.sleep(15)
        else:
            err = f"IG Status polling timed out. Container ID: {creation_id}"
            print(f"[FAIL] {err}")
            ping_error(err, "Instagram Upload")
            return None

        # Step 3: Publish
        publish_url = f"{self.base_url}/{self.ig_id}/media_publish"
        publish_payload = {
            "creation_id": creation_id,
            "access_token": self.access_token
        }
        publish_req = _SESSION.post(publish_url, data=publish_payload)
        publish_res = publish_req.json()
        
        if "id" in publish_res:
            print("🎉 Instagram Reel Published successfully!")
            return publish_res["id"]
        else:
            print(f"[FAIL] IG Publish Failed: {publish_res}")
            return None

if __name__ == "__main__":
    client = MetaAPI()
    print("Meta API Client initialized.")
