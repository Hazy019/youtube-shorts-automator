import os
import requests
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Add root to path so we can import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.api.youtube import upload_video
from src.utils.discord import ping_creator
from src.utils.s3_helper import download_s3_or_http_file

load_dotenv()

def recover_failed_upload():
    print("Starting Manual Recovery Protocol...")
    
    # 1. Connect to Supabase
    supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    
    # 2. Find the latest video where youtube_id is NULL (or 'NULL' string)
    # Based on previous check, it might be the literal string 'NULL' or a null value
    res = supabase.table("videos").select("*").is_("youtube_id", "null").order("created_at", desc=True).limit(1).execute()
    
    if not res.data:
        # Check if it was stored as the string 'NULL'
        res = supabase.table("videos").select("*").eq("youtube_id", "NULL").order("created_at", desc=True).limit(1).execute()

    if not res.data:
        print("No failed uploads found in Supabase (youtube_id is not null).")
        return

    video_data = res.data[0]
    topic = video_data['topic']
    title = video_data['title']
    s3_url = video_data['s3_video_url']
    
    print(f"Recovering: {title}")
    print(f"S3 URL: {s3_url}")

    # 3. Download the video from S3
    local_filename = "recovery_video.mp4"
    print(f"Downloading video from S3...")
    if not download_s3_or_http_file(s3_url, local_filename):
        print("Failed to download video from S3.")
        return
    print("Download complete.")

    # 4. Upload to YouTube
    # We'll use the tiktok_description as a fallback for the YouTube description
    # since the original short description wasn't saved separately.
    description = video_data.get('tiktok_description', f"Amazing facts about {topic}")
    
    try:
        # Determine category (defaulting to gaming if not obvious)
        category = "gaming" if "gaming" in description.lower() or "punch-out" in title.lower() else "general"
        
        youtube_link = upload_video(
            local_filename,
            title,
            description,
            category=category
        )
        
        if youtube_link:
            video_id = youtube_link.split("/")[-1]
            print(f"Successfully uploaded! YouTube ID: {video_id}")
            
            # 5. Update Supabase
            supabase.table("videos").update({"youtube_id": video_id}).eq("id", video_data['id']).execute()
            print("Supabase updated.")
            
            # 6. Ping Discord
            ping_creator(youtube_link, "QUEUED", "N/A", title)
        else:
            print("YouTube upload failed again.")
            
    except Exception as e:
        print(f"Error during recovery: {e}")
    finally:
        if os.path.exists(local_filename):
            os.remove(local_filename)

if __name__ == "__main__":
    recover_failed_upload()
