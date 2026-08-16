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
    Targets API keys, session IDs, tokens, and known secret environments.
    """
    if not text:
        return text
    
    patterns = [
        r"sk-[a-zA-Z0-9_\-]{20,}",                            # OpenAI / general sk-
        r"AIza[a-zA-Z0-9_\-]{30,}",                           # Google AI / Gemini
        r"AKIA[a-zA-Z0-9]{16,}",                              # AWS Key ID
        r"SG\.[a-zA-Z0-9_\-]{20,}",                           # SendGrid / similar
        r"EAA[a-zA-Z0-9]{50,}",                               # Meta / Facebook Graph Access Tokens
        r"eyJ[a-zA-Z0-9_\-]+\.eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+", # JWT / Supabase service_role keys
        r"sb_secret_[a-zA-Z0-9_\-]+",                         # Supabase secret tokens
        r"sb_publishable_[a-zA-Z0-9_\-]+",                    # Supabase publishable tokens
        r"https://discord\.com/api/webhooks/[0-9]+/[a-zA-Z0-9_\-]+", # Webhook URLs
    ]
    
    for p in patterns:
        text = re.sub(p, "[REDACTED_SECRET]", text)
        
    return text

start_time = 0


def _post(url, content=None, embed=None):
    """Helper — silently skips if URL is not set."""
    if not url:
        return
    
    payload = {}
    if content:
        payload["content"] = content
    if embed:
        payload["embeds"] = [embed]
        
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"  Discord post failed: {e}")


def ping_render_start(title, category="general"):
    global start_time
    start_time = time.time()
    print(f"Factory started: {title} [{category}]")
    
    embed = {
        "title": "🏗️ Factory Started",
        "description": f"**Project:** `{title}`\n**Category:** `{category.upper()}`\n\n🟡 *Rendering in progress...*",
        "color": 0xF1C40F  # Yellow/Gold
    }
    _post(URL_LOGS, embed=embed)


def ping_creator(youtube_link, tiktok_status, fb_status, ig_status, title):
    global start_time
    duration = time.time() - start_time
    minutes  = int(duration // 60)
    seconds  = int(duration % 60)
    
    def get_status_emoji(status):
        if status == "SUCCESS" or status == "UPLOADED": return "✅"
        if status == "FAILED": return "❌"
        if status == "PENDING" or status == "QUEUED": return "📥"
        return "⚪"

    print(f"Sending completion for: {title}")
    
    embed = {
        "title": "✅ Production Complete",
        "description": f"**Title:** `{title}`",
        "color": 0x2ECC71, # Green
        "fields": [
            {"name": "📺 YouTube", "value": f"[Watch Video]({youtube_link})", "inline": True},
            {"name": f"{get_status_emoji(tiktok_status)} TikTok", "value": f"`{tiktok_status}`", "inline": True},
            {"name": f"{get_status_emoji(fb_status)} Facebook", "value": f"`{fb_status}`", "inline": True},
            {"name": f"{get_status_emoji(ig_status)} Instagram", "value": f"`{ig_status}`", "inline": True},
            {"name": "⏱️ Time", "value": f"`{minutes}m {seconds}s`", "inline": True}
        ],
        "footer": {"text": "Video syndication cycle complete!"}
    }
    
    _post(URL_POSTS, content=f"<@{PING_ID}>", embed=embed)


def ping_error(error_msg, service_name="API", traceback_str=None):
    error_msg = redact_secrets(error_msg)
    
    embed = {
        "title": "🚨 Emergency Alert",
        "description": f"**Service:** `{service_name}`\n**Error:** `{error_msg}`",
        "color": 0xE74C3C, # Red
    }
    
    if traceback_str:
        clean_tb = redact_secrets(traceback_str)
        embed["fields"] = [
            {"name": "Traceback", "value": f"```python\n{clean_tb[:1000]}\n```", "inline": False}
        ]
        
    _post(URL_ERRORS, content=f"<@{PING_ID}>", embed=embed)


def ping_analytics_insight(insight_text):
    print("Sending AI Analytics Insight to Discord...")
    _post(URL_INSIGHTS, f" **AI INSIGHT**\n{insight_text}")


def ping_queue(new_titles=None):
    """
    Sends the TikTok queue notification.
    Shows only the next item and total count for a professional look.
    """
    fallback = list(new_titles) if new_titles else []
    all_titles = fallback

    try:
        from supabase import create_client
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
        if url and key:
            db = create_client(url, key)
            result = db.table("videos").select("title").eq("tiktok_status", "PENDING").execute()
            pending_titles = [row["title"] for row in result.data if row.get("title")]
            if pending_titles:
                all_titles = pending_titles
    except Exception as e:
        print(f"  Queue DB fetch warning: {e}")

    if not all_titles:
        print("  Queue is empty, no ping needed.")
        return

    count = len(all_titles)
    next_up = all_titles[0]
    
    print(f"Sending professional queue notification ({count} total)...")
    
    embed = {
        "title": "📥 Retry Queue Updated",
        "description": f"Currently **{count}** video(s) are waiting in the manager.",
        "color": 0x3498DB, # Blue
        "fields": [
            {"name": "🏷️ Next Up", "value": f"`{next_up}`", "inline": False}
        ],
        "footer": {"text": "🎬 Run bulk_tiktok_poster.py to upload!"}
    }
    
    if count > 1:
        embed["fields"].append({
            "name": "📦 Remaining",
            "value": f"**{count - 1}** more videos in queue",
            "inline": True
        })

    _post(URL_QUEUE, content=f"Hey <@{PING_ID}>!", embed=embed)


def ping_tiktok_success(topic):
    """Notify when a single video is successfully posted to TikTok."""
    print(f"Sending TikTok success notification: {topic}")
    
    embed = {
        "title": "🚀 Video Published",
        "description": f"**Topic:** `{topic}`\n\n*Available now on TikTok!*",
        "color": 0x2ECC71 # Green
    }
    _post(URL_QUEUE, embed=embed)

def ping_meta_success(topic, platform="Meta"):
    """Notify when a single video is successfully posted to Facebook/Instagram."""
    print(f"Sending {platform} success notification: {topic}")
    
    icon = "📸" if platform == "Instagram" else "📘"
    
    embed = {
        "title": f"{icon} Reel Published",
        "description": f"**Topic:** `{topic}`\n\n*Available now on {platform}!*",
        "color": 0x3498DB # Blue
    }
    _post(URL_POSTS, embed=embed)


def ping_queue_completed(total_uploaded):
    """Notify when the entire local queue has been processed."""
    print(f"Sending queue completion notification (Total: {total_uploaded})")
    
    embed = {
        "title": "🎊 Queue Fully Processed",
        "description": f"Successfully uploaded **{total_uploaded}** video(s).\n\nThe queue is now clear!",
        "color": 0x9B59B6 # Purple/Celebratory
    }
    _post(URL_QUEUE, embed=embed)

def ping_recovery_completed(healed_count, failed_count):
    """Notify when a meta recovery cycle is complete."""
    print(f"Sending recovery completion notification (Healed: {healed_count}, Failed: {failed_count})")
    
    color = 0x2ECC71 if failed_count == 0 else 0xF1C40F
    if healed_count == 0 and failed_count > 0:
        color = 0xE74C3C
        
    embed = {
        "title": "⚕️ Meta Recovery Cycle Complete",
        "description": f"**Healed:** `{healed_count}` videos\n**Failed:** `{failed_count}` videos",
        "color": color
    }
    _post(URL_POSTS, embed=embed)