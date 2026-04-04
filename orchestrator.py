import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

from ai_brain import get_new_topic, generate_script, get_search_query
from ai_voice import generate_voiceover
from video_search import get_background_videos, get_sfx_urls, get_bgm_url 
from main import make_cloud_video
from yt_uploader import upload_video
from discord_bot import ping_creator, ping_error 

def produce_video(category):
    print(f"\n--- STARTING PRODUCTION FOR CATEGORY: {category.upper()} ---")
    topic = get_new_topic(category)
    
    viral_package = generate_script(topic)
    if not viral_package:
        msg = f"Gemini Script Generation failed for topic: {topic}"
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini")
        return False
        
    keyword = get_search_query(topic)
    if not keyword:
        msg = f"Gemini Keyword Generation failed for topic: {topic}"
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini")
        return False
    
    full_audio_script = " ".join([s['voiceover'] for s in viral_package['segments']])
    
    audio_url, duration, voice_error = generate_voiceover(full_audio_script)
    if not audio_url:
        print("\nFACTORY HALTED: Voiceover generation failed.")
        ping_error(voice_error, "ElevenLabs") 
        return False
    
    video_urls = get_background_videos(topic, keyword, num_clips=8)
    
    sfx_urls = get_sfx_urls(num_sfx=len(viral_package['segments']))
    bgm_url = get_bgm_url()
    
    render_seed = int(time.time())
    final_video_url = make_cloud_video(
        audio_url, 
        video_urls, 
        sfx_urls, 
        bgm_url, 
        viral_package['segments'], 
        duration,
        render_seed=render_seed
    )
    
    if final_video_url:
        print(f"\nSUCCESS! RENDER COMPLETE:\n{final_video_url}")
        
        print("\nDownloading temporarily...")
        r = requests.get(final_video_url, stream=True)
        local_filename = f"temp_render_{category}.mp4"
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print("\nInitiating YouTube Upload...")
        youtube_link = upload_video(local_filename, viral_package['title'], viral_package['description'], category, tags=viral_package.get('tags'))
        
        if youtube_link:
             ping_creator(youtube_link, viral_package['title'])
        
        os.remove(local_filename)
        print(f"Local temp file deleted. {category.upper()} Video is live!")
        return True
    else:
        print("\nRender failed. Check AWS CloudWatch logs.")
        return False

def start_factory():
    print("HAZY CHANEL AUTOMATION STARTING DOUBLE SHIFT...\n" + "="*40)
    
    produce_video("gaming")
    
    print("\nTaking a 60-second break before rendering the second video...")
    time.sleep(60)
    
    produce_video("general")
    
    print("\nFACTORY SHUTTING DOWN. ALL TASKS COMPLETE!")

if __name__ == "__main__":
    start_factory()