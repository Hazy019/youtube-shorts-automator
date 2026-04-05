import os
import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL = os.getenv("SERVE_URL")
FUNCTION_NAME = "remotion-render-4-0-443-mem3008mb-disk2048mb-600sec"
REGION = "us-east-1"

def make_cloud_video(voice_url, background_urls, sfx_urls, bgm_url, segments_data, duration_seconds, category="gaming", render_seed=0):
    client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)
    
    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"Commanding Lambda to render {total_frames} frames with professional effects...", flush=True)
    
    if total_frames < 150: 
        print("ERROR: Video duration too short. Aborting render.", flush=True)
        return None
        
    bgm_volume = 0.10 if category == "gaming" else 0.07
    
    params = RenderMediaParams(
        serve_url=SERVE_URL,
        composition="MyComp",
        force_duration_in_frames=total_frames, 
        concurrency=4,
        input_props={
            "audioUrl": voice_url, 
            "videoUrls": background_urls, 
            "sfxUrls": sfx_urls,
            "bgmUrl": bgm_url,
            "bgmVolume": bgm_volume,
            "segments": segments_data,  
            "renderSeed": render_seed,
            "effects": {
                "zoom": True,           
                "transition": "fade",    
                "textStyle": "bold"      
            }
        }
    )
    
    print("Requesting AWS Lambda Render...", flush=True)
    render = client.render_media_on_lambda(render_params=params)
    
    while True:
        status = client.get_render_progress(render_id=render.render_id, bucket_name=render.bucket_name)
        
        if getattr(status, 'fatalErrorEncountered', False):
            error_data = getattr(status, 'errors', 'Unknown Error')

            safe_error = str(error_data).encode('ascii', 'ignore').decode('ascii')
            print(f"\nAWS LAMBDA FATAL ERROR: {safe_error}", flush=True)
            return None
            
        if status.done:
            if not getattr(status, 'outputFile', None):
                print(f"\nRENDER COMPLETED BUT NO OUTPUT FILE FOUND! Status: {status}", flush=True)
            return getattr(status, 'outputFile', None)
            
        print(f"Progress: {getattr(status, 'overallProgress', 0) * 100:.1f}%", end="\r", flush=True)
        time.sleep(5)
