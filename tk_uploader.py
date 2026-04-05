import os
import json
from tiktok_uploader.upload import upload_video
from discord_bot import ping_error

def _json_to_netscape(cookies_json_path: str, netscape_path: str):
    """
    Convert Playwright-format JSON cookies → Netscape HTTP cookies file.
    The tiktok-uploader library only reads Netscape format.
    """
    with open(cookies_json_path, "r", encoding="utf-8") as f:
        cookies = json.load(f)

    lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    for c in cookies:
        domain = c.get("domain", "")

        flag = "TRUE" if domain.startswith(".") else "FALSE"
        path = c.get("path", "/")
        secure = "TRUE" if c.get("secure", False) else "FALSE"

        expires = c.get("expires", 0)
        expires = 0 if expires < 0 else int(expires)
        name = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{expires}\t{name}\t{value}")

    with open(netscape_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def upload_to_tiktok(video_path, title, description, tags=None):
    print(f"\nPreparing to upload {video_path} to TikTok...")


    json_cookies_path = "tiktok_cookies.json"
    netscape_cookies_path = "tiktok_cookies_netscape.txt"


    cookies_json_env = os.getenv("TIKTOK_COOKIES_JSON")
    if cookies_json_env:
        try:
            with open(json_cookies_path, "w", encoding="utf-8") as f:
                f.write(cookies_json_env)
            print("TikTok cookies written from environment secret.")
        except Exception as e:
            print(f"Failed to write TikTok cookies from env: {e}")

    if not os.path.exists(json_cookies_path):
        print("Missing tiktok_cookies.json! Run tools/capture_tiktok_cookies.py locally.")
        return None


    try:
        _json_to_netscape(json_cookies_path, netscape_cookies_path)
        print(f"Converted cookies to Netscape format → {netscape_cookies_path}")
    except Exception as e:
        print(f"Failed to convert TikTok cookies to Netscape format: {e}")
        ping_error(str(e), "TikTok Cookie Conversion")
        return None

    formatted_tags = " ".join([f"#{tag}" for tag in tags]) if tags else "#shorts #gaming #facts"

    full_caption = f"{title}\n\n{description[:1400]}\n\n{formatted_tags}"

    try:
        print("Launching headless browser for TikTok upload...")
        upload_video(
            video_path,
            description=full_caption,
            cookies=netscape_cookies_path,
            headless=True
        )
        print("SUCCESS! Video pushed to TikTok.")
        return "TikTok Upload Complete"
    except Exception as e:
        print(f"TikTok Fatal Error: {e}")
        ping_error(str(e), "TikTok Syndication")
        return None
    finally:

        if os.path.exists(netscape_cookies_path):
            os.remove(netscape_cookies_path)

        if os.getenv("GITHUB_ACTIONS") == "true" and os.path.exists(json_cookies_path):
            os.remove(json_cookies_path)
