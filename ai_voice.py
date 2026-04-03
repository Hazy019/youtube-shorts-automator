import os
import time
import random
import requests
import boto3
import asyncio
import edge_tts
from mutagen.mp3 import MP3
from dotenv import load_dotenv

from discord_bot import ping_error 

load_dotenv()

BUCKET_NAME = "remotionlambda-useast1-d18tz22nyq" 

async def _generate_edge_tts_async(text, output_file):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+10%")
    await communicate.save(output_file)

def check_elevenlabs_quota(api_key):
    try:
        url = "[https://api.elevenlabs.io/v1/user/subscription](https://api.elevenlabs.io/v1/user/subscription)"
        headers = {"xi-api-key": api_key}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            count = data.get("character_count", 0)
            limit = data.get("character_limit", 1)
            if limit > 0:
                return count / limit
    except Exception as e:
        print(f"Failed to check quota silently: {e}")
    return 0.0

def generate_voiceover(script_text):
    print("Preparing AI voiceover engine...")
    api_key = os.getenv("ELEVENLABS_API_KEY")
    local_file = "temp_voice.mp3"
    
    use_fallback = False
    fallback_reason = ""
    
    usage_ratio = check_elevenlabs_quota(api_key)
    if usage_ratio >= 0.90:
        use_fallback = True
        fallback_reason = f"ElevenLabs quota is at {usage_ratio*100:.1f}%. Saving remaining characters."
    else:
        print("Generating premium ElevenLabs voice...")
        voice_ids = ["IKne3meq5aSn9XLyUdCD", "Xb7hH8MSUJpSbSDYk0k2", "pNInz6obpgDQGcFmaJgB"]
        selected_voice = random.choice(voice_ids)
        url = f"[https://api.elevenlabs.io/v1/text-to-speech/](https://api.elevenlabs.io/v1/text-to-speech/){selected_voice}"
        
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}
        data = {
            "text": script_text,
            "model_id": "eleven_turbo_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        
        response = requests.post(url, json=data, headers=headers)
        
        if response.status_code == 200:
            with open(local_file, 'wb') as f:
                f.write(response.content)
        else:
            use_fallback = True
            fallback_reason = f"ElevenLabs API failed (Error {response.status_code})."

    if use_fallback:
        print(f"WARNING: {fallback_reason}")
        print("Switching to FREE Microsoft Edge Neural TTS Fallback...")
        ping_error(fallback_reason, "ElevenLabs Fallback System")
        
        try:
            asyncio.run(_generate_edge_tts_async(script_text, local_file))
            print("Fallback voiceover generated successfully!")
        except Exception as e:
            return None, 0, f"CRITICAL: Both ElevenLabs and Edge TTS failed! {e}"

    try:
        audio_info = MP3(local_file)
        duration_seconds = audio_info.info.length
        print(f"Voiceover length: {duration_seconds:.2f} seconds")
    except Exception as e:
        print(f"Audio Duration Check failed: {e}")
        return None, 0, "Duration check failed."
    
    print("Syncing audio to secure AWS S3...")
    s3 = boto3.client('s3', region_name='us-east-1')
    s3_key = f"voiceovers/voice_{int(time.time())}.mp3"
    
    s3.upload_file(local_file, BUCKET_NAME, s3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
    
    audio_url = s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': BUCKET_NAME, 'Key': s3_key},
        ExpiresIn=3600
    )
    
    return audio_url, duration_seconds, None