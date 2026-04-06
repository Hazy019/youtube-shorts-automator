import os
import json
import time
from discord_bot import ping_error

NETSCAPE_PATH = "tiktok_cookies_netscape.txt"
JSON_PATH = "tiktok_cookies.json"


def _json_to_netscape(json_path: str, netscape_path: str):
    """Convert Playwright-format JSON cookies → Netscape HTTP format."""
    with open(json_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)

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
    print(f"Converted JSON → Netscape: {netscape_path}")


def _prepare_cookies() -> str | None:
    """
    Resolves cookie file in priority order:
      1. TIKTOK_COOKIES_TXT env var  (Netscape format directly)
      2. TIKTOK_COOKIES_JSON env var (Playwright JSON → converted)
      3. Local tiktok_cookies.txt file
      4. Local tiktok_cookies.json file (converted)
    Returns path to Netscape file, or None if no cookies found.
    """
    # 1. Netscape text directly from env secret
    txt_env = os.getenv("TIKTOK_COOKIES_TXT", "").strip()
    if txt_env:
        with open(NETSCAPE_PATH, "w", encoding="utf-8") as f:
            f.write(txt_env)
        print("TikTok cookies written from TIKTOK_COOKIES_TXT secret.")
        return NETSCAPE_PATH

    # 2. JSON from env secret → convert
    json_env = os.getenv("TIKTOK_COOKIES_JSON", "").strip()
    if json_env:
        with open(JSON_PATH, "w", encoding="utf-8") as f:
            f.write(json_env)
        print("TikTok JSON cookies written from TIKTOK_COOKIES_JSON secret.")
        _json_to_netscape(JSON_PATH, NETSCAPE_PATH)
        return NETSCAPE_PATH

    # 3. Local .txt
    if os.path.exists("tiktok_cookies.txt"):
        import shutil
        shutil.copy("tiktok_cookies.txt", NETSCAPE_PATH)
        print("Using local tiktok_cookies.txt")
        return NETSCAPE_PATH

    # 4. Local .json → convert
    if os.path.exists(JSON_PATH):
        _json_to_netscape(JSON_PATH, NETSCAPE_PATH)
        return NETSCAPE_PATH

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
        print("Your TikTok session may be expired. Re-run tools/capture_tiktok_cookies.py.")
        return False
    return True


def upload_to_tiktok(video_path, title, description, tags=None):
    print(f"\nPreparing TikTok upload for: {video_path}")

    cookies_path = _prepare_cookies()
    if not cookies_path:
        msg = "No TikTok cookie file found. Set TIKTOK_COOKIES_TXT or TIKTOK_COOKIES_JSON secret."
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
        from tiktok_uploader.upload import upload_video

        print("Launching headless browser via tiktok-uploader...")
        result = upload_video(
            video_path,
            description=caption,
            cookies=cookies_path,
            headless=True,
        )
        print(f"TikTok upload result: {result}")
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
    """Remove temp cookie files — never leave session data on disk in CI."""
    for path in [NETSCAPE_PATH, JSON_PATH]:
        if os.path.exists(path) and os.getenv("GITHUB_ACTIONS") == "true":
            os.remove(path)
            print(f"Cleaned up: {path}")