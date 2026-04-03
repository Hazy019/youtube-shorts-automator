import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL = "https://remotionlambda-useast1-d18tz22nyq.s3.us-east-1.amazonaws.com/sites/hazy-chanel-v1/index.html"
FUNCTION_NAME = "remotion-render-4-0-443-mem3008mb-disk2048mb-600sec"
REGION = "us-east-1"

def make_cloud_video(voice_url, background_urls, caption_text, duration_seconds):
    client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)
    
    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"Commanding Lambda to render {total_frames} frames with professional effects...", flush=True)
    
    if total_frames < 150: 
        print("ERROR: Video duration too short. Aborting render.", flush=True)
        return None
    
    params = RenderMediaParams(
        serve_url=SERVE_URL,
        composition="MyComp",
        force_duration_in_frames=total_frames, 
        concurrency=4,                 
        input_props={
            "audioUrl": voice_url, 
            "videoUrls": background_urls, 
            "text": caption_text,
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
            print(f"\nAWS LAMBDA FATAL ERROR: {error_data}", flush=True)
            return None
            
        if status.done:
            if not getattr(status, 'outputFile', None):
                print(f"\nRENDER COMPLETED BUT NO OUTPUT FILE FOUND! Status: {status}", flush=True)
            return getattr(status, 'outputFile', None)
            
        print(f"Progress: {getattr(status, 'overallProgress', 0) * 100:.1f}%", end="\r", flush=True)
        time.sleep(5)