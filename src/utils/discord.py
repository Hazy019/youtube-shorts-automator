import os
import requests
import time
import re
from dotenv import load_dotenv

load_dotenv()

# ── Webhook URLs ──────────────────────────────────────────────────────────────
# factory.yml writes: WEBHOOK_LOGS, WEBHOOK_ERRORS, WEBHOOK_POSTS, WEBHOOK_INSIGHTS, WEBHOOK_QUEUE
# All fall back to DISCORD_WEBHOOK_URL if specific ones are not set.
URL_LOGS     = os.getenv("WEBHOOK_LOGS")     or os.getenv("DISCORD_WEBHOOK_LOGS") or os.getenv("DISCORD_WEBHOOK_URL")
URL_ERRORS   = os.getenv("WEBHOOK_ERRORS")   or os.getenv("DISCORD_WEBHOOK_URL")
URL_POSTS    = os.getenv("WEBHOOK_POSTS")    or os.getenv("DISCORD_WEBHOOK_URL")
URL_INSIGHTS = os.getenv("WEBHOOK_INSIGHTS") or os.getenv("DISCORD_WEBHOOK_URL")
URL_QUEUE    = os.getenv("WEBHOOK_QUEUE")    or os.getenv("DISCORD_WEBHOOK_URL")
PING_ID      = os.getenv("DISCORD_PING_USER_ID", "898947674089349180")
# ─────────────────────────────────────────────────────────────────────────────

def redact_secrets(text):
    """
    Scrubs sensitive patterns from tracebacks or strings before sending to Discord.
    Targets API keys, session IDs, and known secret environments.
    """
    if not text:
        return text
    
    # Redact common API key patterns (GPT, Gemini, ElevenLabs, etc)
    # sk-..., AIza..., AKIA..., SG....
    patterns = [
        r"sk-[a-zA-Z0-9_\-]{20,}",           # OpenAI / general sk-
        r"AIza[a-zA-Z0-9_\-]{30,}",          # Google AI / Gemini
        r"AKIA[a-zA-Z0-9]{16,}",             # AWS Key ID
        r"SG\.[a-zA-Z0-9_\-]{20,}",          # SendGrid / similar
        r"https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_\-]+", # Webhooks
    ]
    
    for p in patterns:
        text = re.sub(p, "[REDACTED_SECRET]", text)
        
    return text

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
        f"⏱️ **Render Time:** {minutes}m {seconds}s\n"
        f"<@{PING_ID}> **Video is ready!**"
    ))


def ping_error(error_msg, service_name="API", traceback_str=None):
    error_msg = redact_secrets(error_msg)
    detail = f"**Error:** `{error_msg}`"
    if traceback_str:
        clean_tb = redact_secrets(traceback_str)
        detail += f"\n**Traceback:**\n```python\n{clean_tb[:1500]}\n```"
    _post(URL_ERRORS, (
        f"🚨 **EMERGENCY ALERT**\n"
        f"**Service:** {service_name}\n"
        f"{detail}\n"
        f"<@{PING_ID}> **Action required!**"
    ))


def ping_analytics_insight(insight_text):
    print("Sending AI Analytics Insight to Discord...")
    _post(URL_INSIGHTS, f" **AI INSIGHT**\n{insight_text}")


def ping_queue(new_titles=None):
    """
    Sends the TikTok queue notification.
    Primary: queries Supabase for ALL PENDING videos for the full cumulative list.
    Fallback: uses the locally known new_titles if Supabase is unavailable or
              returns 0 results (e.g. if the DB insert was skipped silently),
              ensuring a notification is ALWAYS sent when a video was queued.
    """
    fallback = list(new_titles) if new_titles else []
    all_titles = fallback  # guaranteed baseline — overwritten if DB has data

    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            db = create_client(url, key)
            result = db.table("videos").select("title").eq("tiktok_status", "PENDING").execute()
            pending_titles = [row["title"] for row in result.data if row.get("title")]
            if pending_titles:
                all_titles = pending_titles  # DB is authoritative when it has data
            else:
                print("  Queue: DB returned 0 PENDING rows — using locally known titles as fallback.")
    except Exception as e:
        print(f"  Queue DB fetch warning (using local titles): {e}")

    if not all_titles:
        print("  Queue is empty, no ping needed.")
        return

    count = len(all_titles)
    title_list = "\n".join([f"{i+1}. `{t}`" for i, t in enumerate(all_titles)])

    print(f"Sending queue notification ({count} total pending videos)...")
    _post(URL_QUEUE, (
        f"📥 **RETRY QUEUE UPDATED**\n"
        f"Hey <@{PING_ID}>! You have **{count}** video(s) waiting in the local retry manager:\n\n"
        f"{title_list}\n\n"
        f"🎬 *Run `bulk_tiktok_poster.py` to upload!*"
    ))


def ping_tiktok_success(topic):
    """Notify when a single video is successfully posted to TikTok."""
    print(f"Sending TikTok success notification: {topic}")
    _post(URL_QUEUE, (
        f" **VIDEO POSTED TO TIKTOK**\n"
        f"**Topic:** `{topic}`\n"
        f" *Available now on the platform!*"
    ))


def ping_queue_completed(total_uploaded):
    """Notify when the entire local queue has been processed."""
    print(f"Sending queue completion notification (Total: {total_uploaded})")
    _post(URL_QUEUE, (
        f" **QUEUE FULLY PROCESSED**\n"
        f"Finished uploading **{total_uploaded}** videos. The queue is now clear!\n\n"
        f" *All caught up!*"
    ))