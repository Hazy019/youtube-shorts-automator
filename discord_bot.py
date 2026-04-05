import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def ping_creator(youtube_link, tiktok_status, ig_link, title):
    print("Sending notification to Discord...")
    
    if not WEBHOOK_URL:
        print("Warning: No Discord Webhook URL found. Skipping ping.")
        return

    message = (
        f"<@898947674089349180> **THE FACTORY HAS PRODUCED A NEW SHORT!** \n\n"
        f"**Title:** {title}\n"
        f"🔴 **YouTube:** {youtube_link}\n"
        f"🎵 **TikTok:** {tiktok_status}\n"
        f"📸 **Instagram:** {ig_link}"
    )
    data = {"content": message}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Discord Ping sent successfully!")
    except Exception as e:
        print(f"Failed to ping Discord: {e}")

def ping_error(error_msg, service_name="API", traceback_str=None):
    print(f"Sending Emergency Alert to Discord ({service_name})...")
    
    if not WEBHOOK_URL:
        return

    detail_block = f"**Details:** `{error_msg}`\n"
    if traceback_str:
        detail_block += f"**Traceback:**\n```python\n{traceback_str[:1500]}\n```"

    message = (
        f"🚨 **EMERGENCY FACTORY ALERT** 🚨\n\n"
        f"**Service:** {service_name}\n"
        f"{detail_block}\n"
        f"<@898947674089349180> **CRITICAL failure detected!**"
    )
    data = {"content": message}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Emergency Alert sent to Discord!")
    except Exception as e:
        print(f"Failed to send Discord error: {e}")

def ping_analytics_insight(insight_text):
    print("Sending AI Analytics Insight to Discord...")
    
    if not WEBHOOK_URL:
        return

    message = (
        f"🧠 **AI ANALYTICS INSIGHT** 🧠\n\n"
        f"{insight_text}\n\n"
        f"*The Factory is learning and adapting...*"
    )
    data = {"content": message}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Analytics Insight sent to Discord!")
    except Exception as e:
        print(f"Failed to send Analytics Insight: {e}")
