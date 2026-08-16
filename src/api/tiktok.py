import os
import json
import time
from src.utils.discord import ping_error

NETSCAPE_PATH = "tiktok_cookies.txt"
JSON_PATH = "tiktok_cookies.json"
_temp_files = []


def _json_to_netscape(json_path: str, netscape_path: str) -> bool:
    """Convert Playwright-format JSON cookies → Netscape HTTP format."""
    if not os.path.exists(json_path):
        print(f"Warning: Cookie file {json_path} does not exist.")
        return False

    if os.path.getsize(json_path) == 0:
        print(f"Warning: Cookie file {json_path} is empty.")
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {json_path} is not a valid JSON file.")
        return False

    lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    for c in cookies:
        domain  = c.get("domain", "")
        flag    = "TRUE" if domain.startswith(".") else "FALSE"
        path    = c.get("path", "/")
        secure  = "TRUE" if c.get("secure", False) else "FALSE"
        expires = c.get("expires", -1)
        # Session cookies have expires=-1; set a 30-day future timestamp instead
        if not expires or expires <= 0:
            expires = int(time.time()) + 30 * 24 * 3600
        name  = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expires)}\t{name}\t{value}")

    with open(netscape_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Converted JSON -> Netscape: {netscape_path}")
    return True


def _netscape_to_json(netscape_path: str, json_path: str = None) -> list:
    """Convert Netscape HTTP format cookies → Playwright JSON cookies list and optionally saves to file."""
    if not os.path.exists(netscape_path) or os.path.getsize(netscape_path) == 0:
        return []

    cookies = []
    with open(netscape_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expires, name, value = parts[:7]
                try:
                    exp_val = float(expires)
                    if exp_val <= 0:
                        exp_val = -1
                except (ValueError, TypeError):
                    exp_val = -1

                cookie_dict = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path or "/",
                    "secure": secure.upper() == "TRUE",
                }
                if exp_val > 0:
                    cookie_dict["expires"] = exp_val
                cookies.append(cookie_dict)

    if json_path and cookies:
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"Converted Netscape -> JSON: {json_path}")
        except Exception as e:
            print(f"Warning: Failed to write {json_path}: {e}")

    return cookies


def get_playwright_cookies() -> list:
    """Returns a list of cookie dicts formatted for Playwright context.add_cookies()."""
    txt_path = _prepare_cookies()
    if not txt_path or not os.path.exists(txt_path):
        return []

    # If JSON path exists and is populated, load it; otherwise convert from Netscape
    if os.path.exists(JSON_PATH) and os.path.getsize(JSON_PATH) > 0:
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass

    return _netscape_to_json(txt_path, JSON_PATH)


def _prepare_cookies() -> str | None:
    """
    Resolves cookie file in priority order:
      1. TIKTOK_COOKIES_TXT env var  (Netscape format directly)
      2. TIKTOK_COOKIES_JSON env var (Playwright JSON → converted)
      3. Local tiktok_cookies.txt file
      4. Local tiktok_cookies.json file (converted)
    Returns path to Netscape file, or None if no cookies found.
    Also ensures both .txt and .json formats are synchronized.
    """
    # 0. Resolve potential paths
    possible_roots = list(dict.fromkeys([
        os.getcwd(),                                            # Current working dir
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), # Project root if run from subfolder
    ]))
    
    # 1. Netscape text directly from env secret
    txt_env = os.getenv("TIKTOK_COOKIES_TXT", "").strip()
    if txt_env:
        with open(NETSCAPE_PATH, "w", encoding="utf-8") as f:
            f.write(txt_env)
        print("TikTok cookies written from TIKTOK_COOKIES_TXT secret.")
        _temp_files.append(NETSCAPE_PATH)
        _netscape_to_json(NETSCAPE_PATH, JSON_PATH)
        _temp_files.append(JSON_PATH)
        return NETSCAPE_PATH

    # 2. JSON from env secret → convert
    json_env = os.getenv("TIKTOK_COOKIES_JSON", "").strip()
    if json_env:
        if not (json_env.startswith("[") or json_env.startswith("{")):
            print("Warning: TIKTOK_COOKIES_JSON env variable does not look like JSON. Skipping.")
        else:
            with open(JSON_PATH, "w", encoding="utf-8") as f:
                f.write(json_env)
            print("TikTok JSON cookies written from TIKTOK_COOKIES_JSON secret.")
            _temp_files.append(JSON_PATH)
            if _json_to_netscape(JSON_PATH, NETSCAPE_PATH):
                _temp_files.append(NETSCAPE_PATH)
                return NETSCAPE_PATH

    # 3. Local .txt
    for root in possible_roots:
        txt_path = os.path.join(root, "tiktok_cookies.txt")
        if os.path.exists(txt_path) and os.path.getsize(txt_path) > 0:
            if os.path.abspath(txt_path) != os.path.abspath(NETSCAPE_PATH):
                import shutil
                shutil.copy(txt_path, NETSCAPE_PATH)
                print(f"Using local cookies from: {txt_path}")
            else:
                print(f"Using local cookies: {NETSCAPE_PATH}")
            # Ensure JSON sync
            _netscape_to_json(NETSCAPE_PATH, JSON_PATH)
            return NETSCAPE_PATH

    # 4. Local .json → convert
    for root in possible_roots:
        json_path = os.path.join(root, JSON_PATH)
        if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
            print(f"Found local {json_path}, converting...")
            if _json_to_netscape(json_path, NETSCAPE_PATH):
                return NETSCAPE_PATH

    print(f"DEBUG: No local cookie files found in {possible_roots}")
    return None


def _validate_netscape(path: str) -> bool:
    """Quick sanity check that critical TikTok session cookies exist."""
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    critical = ["sessionid", "sid_tt"]
    missing = [c for c in critical if c not in content]
    if missing:
        print(f"WARNING: TikTok cookies missing critical fields: {missing}")
        print(f"Cookie file content length: {len(content)} bytes")
        if len(content) < 50:
            print(f"Cookie file preview: {content}")
        print("Your TikTok session may be expired. Re-run tools/capture_tiktok_cookies.py locally.")
        return False
    print("TikTok cookies validated successfully.")
    return True


def upload_to_tiktok(video_path, title, description, tags=None):
    print(f"\nPreparing TikTok upload for: {video_path}")

    cookies_path = _prepare_cookies()
    if not cookies_path:
        msg = "No TikTok cookie file found. Ensure 'tiktok_cookies.txt' or 'tiktok_cookies.json' is in the root directory, OR set TIKTOK_COOKIES_TXT/JSON secrets."
        print(f"[TikTok SKIP] {msg}")
        ping_error(msg, "TikTok Auth")
        return None

    if not _validate_netscape(cookies_path):
        msg = "TikTok cookies are invalid or expired. Re-authenticate locally."
        ping_error(msg, "TikTok Auth")
        _cleanup()
        return None

    hashtags = " ".join(f"#{t}" for t in tags) if tags else "#shorts #gaming #facts"
    caption = f"{title}\n\n{description[:1400]}\n\n{hashtags}"[:2200]

    try:
        import threading
        
        is_headless = os.getenv("GITHUB_ACTIONS") == "true"
        thread_result = None
        thread_err = None
        
        def _run_upload():
            nonlocal thread_result, thread_err
            try:
                from tiktok_uploader.upload import upload_video
                thread_result = upload_video(
                    video_path,
                    description=caption,
                    cookies=cookies_path,
                    headless=is_headless,
                )
            except Exception as e:
                thread_err = e
                
        print(f"Launching browser via tiktok-uploader (Headless: {is_headless})...")
        t = threading.Thread(target=_run_upload)
        t.start()
        t.join()
        
        if thread_err:
            raise thread_err
            
        result = thread_result
        
        print(f"TikTok upload raw result: {result}")
        
        # tiktok-uploader returns a list of FAILED uploads. 
        # If the list is empty [], then it succeeded! If it has items, those items failed.
        if isinstance(result, list) and len(result) > 0:
            err = f"TikTok failed to upload! Playwright was blocked by Captcha or Pop-up. Raw error data: {result[0]}"
            print(f"[TikTok ERROR] {err}")
            ping_error(err, "TikTok Upload")
            return None
               
        return "TikTok Upload Complete"

    except ImportError:
        msg = "tiktok-uploader not installed. Add 'tiktok-uploader==0.1.0' to requirements.txt"
        print(f"[TikTok ERROR] {msg}")
        ping_error(msg, "TikTok Import")
        return None

    except Exception as e:
        err = str(e)
        print(f"[TikTok ERROR] {err}")
        ping_error(err, "TikTok Upload")
        return None

    finally:
        _cleanup()


def _cleanup():
    """Remove temp cookie files created from env vars."""
    global _temp_files
    for path in _temp_files:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Cleaned up temp session file: {path}")
            except:
                pass
    _temp_files = []