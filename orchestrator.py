import os
import requests
from dotenv import load_dotenv

load_dotenv()

from ai_brain import get_new_topic, generate_script, get_search_query
from ai_voice import generate_voiceover
from video_search import get_background_videos 
from main import make_cloud_video
from yt_uploader import upload_video
from discord_bot import ping_creator, ping_error 

def start_factory():
    print("HAZY CHANEL AUTOMATION STARTING...\n" + "="*40)
    
    topic = get_new_topic()
    
    viral_package = generate_script(topic)
    if not viral_package:
        msg = f"Gemini Script Generation failed for topic: {topic}"
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini")
        return
        
    keyword = get_search_query(topic)
    if not keyword:
        msg = f"Gemini Keyword Generation failed for topic: {topic}"
        print(f"\nABORTING: {msg}")
        ping_error(msg, "Gemini")
        return
    
    audio_url, duration, voice_error = generate_voiceover(viral_package['script'])
    if not audio_url:
        print("\nFACTORY HALTED: Voiceover generation failed.")
        ping_error(voice_error, "ElevenLabs") 
        return
    
    video_urls = get_background_videos(topic, keyword, num_clips=5)
    caption = viral_package['title'].upper()
    
    final_video_url = make_cloud_video(audio_url, video_urls, caption, duration)
    
    if final_video_url:
        print(f"\nSUCCESS! RENDER COMPLETE:\n{final_video_url}")
        
        print("\nDownloading temporarily...")
        r = requests.get(final_video_url, stream=True)
        local_filename = "temp_render.mp4"
        with open(local_filename, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print("\nInitiating YouTube Upload...")
        youtube_link = upload_video(local_filename, viral_package['title'], viral_package['description'])
        
        if youtube_link:
             ping_creator(youtube_link, viral_package['title'])
        
        os.remove(local_filename)
        print("Local temp file deleted. Your hard drive is clean!")
        print("\nAUTOMATION CYCLE COMPLETE! Your new Short is live.")
    else:
        print("\nRender failed. Check AWS CloudWatch logs.")

if __name__ == "__main__":
    start_factory()