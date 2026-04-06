import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# Map specific channel URLs
URL_LOGS = os.getenv("WEBHOOK_LOGS")
URL_ERRORS = os.getenv("WEBHOOK_ERRORS")
URL_POSTS = os.getenv("WEBHOOK_POSTS")
URL_INSIGHTS = os.getenv("WEBHOOK_INSIGHTS")

# Global variable to store start time
start_time = 0

def ping_render_start(title):
    """Marks the start of the production process and notifies the Logs channel."""
    global start_time
    start_time = time.time()  # Capture the exact start moment
    print(f"Factory started: {title}")
    
    if not URL_LOGS:
        print("Warning: WEBHOOK_LOGS not found.")
        return

    message = f"🏗️ **FACTORY STARTED**\n**Project:** `{title}`\n🟡 *Rendering in progress...*"
    try:
        requests.post(URL_LOGS, json={"content": message})
    except Exception as e:
        print(f"Error sending logs to Discord: {e}")

def ping_creator(youtube_link, tiktok_status, ig_link, title):
    """Notifies the Posts channel about successful production completion."""
    global start_time
    # Calculate how many minutes/seconds have passed
    duration = time.time() - start_time
    minutes = int(duration // 60)
    seconds = int(duration % 60)
    
    print(f"Sending completion for: {title}")
    
    if not URL_POSTS: 
        print("Warning: WEBHOOK_POSTS not found.")
        return
    
    message = (
        f"✅ **PRODUCTION COMPLETE**\n"
        f"**Title:** {title}\n"
        f"📺 **YouTube:** {youtube_link}\n"
        f"🎵 **TikTok:** {tiktok_status}\n"
        f"⏱️ **Render Time:** {minutes}m {seconds}s"
    )
    
    try:
        requests.post(URL_POSTS, json={"content": message})
        print("Production notification sent successfully!")
    except Exception as e:
        print(f"Error sending completion notification: {e}")

def ping_error(error_msg, service_name="API", traceback_str=None):
    """Notifies the Errors channel about issues."""
    if not URL_ERRORS:
        print("Warning: WEBHOOK_ERRORS not found.")
        return
    
    detail_block = f"**Error:** `{error_msg}`"
    if traceback_str:
        detail_block += f"\n**Traceback:**\n```python\n{traceback_str[:1500]}\n```"

    message = (
        f"🚨 **EMERGENCY ALERT**\n"
        f"**Service:** {service_name}\n"
        f"{detail_block}\n"
        f"<@898947674089349180> **Action required!**"
    )
    
    try:
        requests.post(URL_ERRORS, json={"content": message})
        print("Emergency Alert sent to Discord!")
    except Exception as e:
        print(f"Failed to send Discord error: {e}")

def ping_analytics_insight(insight_text):
    """Notifies the Insights channel with AI-generated feedback."""
    if not URL_INSIGHTS:
        print("Warning: WEBHOOK_INSIGHTS not found.")
        return
        
    message = f"🧠 **AI INSIGHT**\n{insight_text}"
    try:
        requests.post(URL_INSIGHTS, json={"content": message})
        print("Analytics Insight sent to Discord!")
    except Exception as e:
        print(f"Failed to send Analytics Insight: {e}")
