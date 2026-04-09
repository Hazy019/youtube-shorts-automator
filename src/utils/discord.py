import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# ── Webhook URLs ──────────────────────────────────────────────────────────────
# factory.yml writes WEBHOOK_LOGS, WEBHOOK_ERRORS, WEBHOOK_POSTS, WEBHOOK_INSIGHTS
# to the .env file. All fall back to DISCORD_WEBHOOK_URL if specific ones not set.
URL_LOGS     = os.getenv("WEBHOOK_LOGS")     or os.getenv("DISCORD_WEBHOOK_URL")
URL_ERRORS   = os.getenv("WEBHOOK_ERRORS")   or os.getenv("DISCORD_WEBHOOK_URL")
URL_POSTS    = os.getenv("WEBHOOK_POSTS")    or os.getenv("DISCORD_WEBHOOK_URL")
URL_INSIGHTS = os.getenv("WEBHOOK_INSIGHTS") or os.getenv("DISCORD_WEBHOOK_URL")
URL_QUEUE    = os.getenv("WEBHOOK_QUEUE")    or os.getenv("DISCORD_WEBHOOK_URL")
# ─────────────────────────────────────────────────────────────────────────────

start_time = 0


def _post(url, content):
    """Helper — silently skips if URL is not set."""
    if not url:
        print(f"  Discord skip: no webhook URL configured.")
        return
    try:
        requests.post(url, json={"content": content}, timeout=10)
    except Exception as e:
        print(f"  Discord post failed: {e}")


def ping_render_start(title):
    global start_time
    start_time = time.time()
    print(f"Factory started: {title}")
    _post(URL_LOGS, f"🏗️ **FACTORY STARTED**\n**Project:** `{title}`\n🟡 *Rendering in progress...*")


def ping_creator(youtube_link, tiktok_status, ig_link, title):
    global start_time
    duration = time.time() - start_time
    minutes  = int(duration // 60)
    seconds  = int(duration % 60)
    
    # Detail check for TikTok status
    if tiktok_status == "QUEUED":
        tiktok_status = "📥 **QUEUED** (Ready for Local Retry Manager)"
    elif tiktok_status == "SUCCESS":
        tiktok_status = "✅ **UPLOADED**"
    elif tiktok_status == "FAILED":
        tiktok_status = "❌ **FAILED**"

    print(f"Sending completion for: {title}")
    _post(URL_POSTS, (
        f"✅ **PRODUCTION COMPLETE**\n"
        f"**Title:** {title}\n"
        f"📺 **YouTube:** {youtube_link}\n"
        f"🎵 **TikTok:** {tiktok_status}\n"
        f"⏱️ **Render Time:** {minutes}m {seconds}s"
    ))


def ping_error(error_msg, service_name="API", traceback_str=None):
    detail = f"**Error:** `{error_msg}`"
    if traceback_str:
        detail += f"\n**Traceback:**\n```python\n{traceback_str[:1500]}\n```"
    _post(URL_ERRORS, (
        f"🚨 **EMERGENCY ALERT**\n"
        f"**Service:** {service_name}\n"
        f"{detail}\n"
        f"<@898947674089349180> **Action required!**"
    ))


def ping_analytics_insight(insight_text):
    print("Sending AI Analytics Insight to Discord...")
    _post(URL_INSIGHTS, f"🧠 **AI INSIGHT**\n{insight_text}")


def ping_queue(titles):
    """Notify when videos are rendered and added to the Supabase retry queue."""
    if not titles:
        return
        
    count = len(titles)
    title_list = "\n".join([f"{i+1}. `{t}`" for i, t in enumerate(titles)])
    
    print(f"Sending queue notification for {count} videos...")
    _post(URL_QUEUE, (
        f"📥 **RETRY QUEUE UPDATED**\n"
        f"Hey! **{count}** new videos are rendered and waiting for you in the local retry manager:\n\n"
        f"{title_list}\n\n"
        f"🚀 *Ready for bulk upload!*"
    ))