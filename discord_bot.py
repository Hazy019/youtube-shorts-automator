import os
import requests
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def ping_creator(youtube_link, title):
    print("Sending notification to Discord...")
    
    if not WEBHOOK_URL:
        print("Warning: No Discord Webhook URL found. Skipping ping.")
        return

    message = f"<@898947674089349180> **THE FACTORY HAS PRODUCED A NEW SHORT!** \n\n**Title:** {title}\n**Link:** {youtube_link}"
    data = {"content": message}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Discord Ping sent successfully!")
    except Exception as e:
        print(f"Failed to ping Discord: {e}")

def ping_error(error_msg, service_name="API"):
    print(f"Sending Emergency Alert to Discord ({service_name})...")
    
    if not WEBHOOK_URL:
        return

    message = (
        f"**EMERGENCY FACTORY ALERT** \n\n"
        f"**Service:** {service_name}\n"
        f"**Details:** `{error_msg}`\n\n"
        f"<@898947674089349180> **CRITICAL: The automation has stalled due to a limit/error!**"
    )
    data = {"content": message}
    
    try:
        requests.post(WEBHOOK_URL, json=data)
        print("Emergency Alert sent to Discord!")
    except Exception as e:
        print(f"Failed to send Discord error: {e}")