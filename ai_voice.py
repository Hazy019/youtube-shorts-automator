import os
import time
import random
import requests
import boto3
import asyncio
import edge_tts
from mutagen.mp3 import MP3
from pydub import AudioSegment, effects
from dotenv import load_dotenv
from discord_bot import ping_error 

load_dotenv()

BUCKET_NAME = os.getenv("BUCKET_NAME")

async def _generate_edge_tts_async(text, output_file):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural", rate="+10%")
    await communicate.save(output_file)

def check_elevenlabs_quota(api_key):
    try:
        url = "https://api.elevenlabs.io/v1/user/subscription"
        headers = {"xi-api-key": api_key}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data.get("character_count", 0) / data.get("character_limit", 1)
    except:
        pass
    return 0.0

def generate_voiceover(script_text):
    api_key = os.getenv("ELEVENLABS_API_KEY")
    local_file = "temp_voice.mp3"
    use_fallback = False
    
    usage_ratio = check_elevenlabs_quota(api_key)
    if usage_ratio >= 0.90:
        use_fallback = True
    else:
        voice_ids = ["IKne3meq5aSn9XLyUdCD", "Xb7hH8MSUJpSbSDYk0k2", "pNInz6obpgDQGcFmaJgB"]
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{random.choice(voice_ids)}"
        headers = {"Accept": "audio/mpeg", "Content-Type": "application/json", "xi-api-key": api_key}
        data = {"text": script_text, "model_id": "eleven_turbo_v2", "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            with open(local_file, 'wb') as f:
                f.write(response.content)
        else:
            use_fallback = True

    if use_fallback:
        print("Switching to Microsoft Edge Neural TTS Fallback...")
        ping_error("Fallback Active", "ElevenLabs")
        try:
            asyncio.run(_generate_edge_tts_async(script_text, local_file))
        except Exception as e:
            return None, 0, f"Both ElevenLabs and Edge TTS failed: {e}"

    raw_audio = AudioSegment.from_file(local_file)
    normalized_audio = effects.normalize(raw_audio)
    normalized_audio.export(local_file, format="mp3")

    audio_info = MP3(local_file)
    duration_seconds = audio_info.info.length
    
    s3 = boto3.client('s3', region_name='us-east-1')
    s3_key = f"voiceovers/voice_{int(time.time())}.mp3"
    s3.upload_file(local_file, BUCKET_NAME, s3_key, ExtraArgs={'ContentType': 'audio/mpeg'})
    
    os.remove(local_file)
    return s3.generate_presigned_url('get_object', Params={'Bucket': BUCKET_NAME, 'Key': s3_key}, ExpiresIn=3600), duration_seconds, None