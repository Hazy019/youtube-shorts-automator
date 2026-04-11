import os
import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL = os.getenv("SERVE_URL")
FUNCTION_NAME = os.getenv("FUNCTION_NAME") or "remotion-render-4-0-443-mem3008mb-disk2048mb-600sec"
REGION = "us-east-1"

# How many times to retry a full render on AWS Concurrency / Rate Exceeded errors
RENDER_RETRIES = 4
RENDER_RETRY_BASE_WAIT = 60  # seconds — doubles each retry (60, 120, 240, 480)

def _is_retriable_error(error_data) -> bool:
    """
    Returns True for any error class that benefits from a cooldown + retry.
    Covers: AWS concurrency limits, rate exceeded, AND stitcher timeouts.
    """
    err_str = str(error_data).lower()
    return (
        "concurrency limit" in err_str
        or "rate exceeded" in err_str
        or "timed out" in err_str           # stitcher timeout
        or "chunks are missing" in err_str  # stitcher incomplete assembly
    )

def _do_render(client, params):
    """
    Initiate a single render attempt and poll until completion.
    Returns (output_file_url, fatal_error_data) tuple.
    - output_file_url: the S3 URL on success, None on failure.
    - fatal_error_data: the raw errors list if a fatal occurred, else None.
    """
    render = None
    for attempt in range(5):
        try:
            render = client.render_media_on_lambda(render_params=params)
            print(f"Render initiated: {render.render_id}", flush=True)
            break
        except Exception as e:
            print(f"  Lambda invoke failed (Attempt {attempt+1}/5): {e}", flush=True)
            if attempt == 4:
                print("  FATAL: Could not initiate render after 5 attempts.", flush=True)
                return None, "invoke_failed"
            time.sleep(5 * (2 ** attempt))

    # Poll for completion
    while True:
        try:
            status = client.get_render_progress(
                render_id=render.render_id,
                bucket_name=render.bucket_name
            )

            if getattr(status, 'fatalErrorEncountered', False):
                error_data = getattr(status, 'errors', 'Unknown Error')
                safe_error = str(error_data).encode('ascii', 'ignore').decode('ascii')
                print(f"\nAWS LAMBDA FATAL ERROR: {safe_error}", flush=True)
                return None, error_data

            if status.done:
                output = getattr(status, 'outputFile', None)
                if not output:
                    print(f"\nRENDER COMPLETED BUT NO OUTPUT FILE FOUND!", flush=True)
                return output, None

            print(f"Progress: {getattr(status, 'overallProgress', 0) * 100:.1f}%", end="\r", flush=True)

        except Exception as e:
            print(f"\nNetwork error polling render status: {e}. Retrying in 5s...", flush=True)

        time.sleep(5)


def make_cloud_video(voice_url, background_urls, sfx_urls, bgm_url, segments_data, duration_seconds, category="gaming", render_seed=0):
    client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)

    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"Commanding Lambda to render {total_frames} frames with professional effects...", flush=True)

    if total_frames < 150:
        err = "ERROR: Video duration too short. Aborting render."
        print(err, flush=True)
        return None, err

    # ─── CHUNK CALCULATION ────────────────────────────────────────────────────
    # Rule: Never create more than 10 renderer chunks for a 600s stitcher Lambda.
    # Fewer chunks = fewer cold-starts = stitcher finishes in 30-90s not 600s.
    # At 600 frames/chunk: a 90s video (2700 frames) = 5 chunks.
    # Each chunk renders ~20s of video in ~40-80s wall time. Well within 600s.
    # ─────────────────────────────────────────────────────────────────────────
    frames_per_lambda = max(600, math.ceil(total_frames / 10))
    chunk_count = math.ceil(total_frames / frames_per_lambda)
    print(f"Render plan: {total_frames} frames → {chunk_count} chunks @ {frames_per_lambda} fps/chunk", flush=True)

    bgm_volume = 0.18 if category == "gaming" else 0.12

    params = RenderMediaParams(
        serve_url=SERVE_URL,
        composition="MyComp",
        force_duration_in_frames=total_frames,
        frames_per_lambda=frames_per_lambda,  # dynamic — never causes stitcher timeout
        concurrency_per_lambda=2,             # MUST match available vCPUs (2 for 3008MB)
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

    print(f"Requesting AWS Lambda Render (ID tracking enabled)...", flush=True)

    for render_attempt in range(RENDER_RETRIES + 1):
        if render_attempt > 0:
            wait = RENDER_RETRY_BASE_WAIT * (2 ** (render_attempt - 1))
            print(f"\n[Render Retry {render_attempt}/{RENDER_RETRIES}] Waiting {wait}s for AWS concurrency to cool down...", flush=True)
            time.sleep(wait)

        output_url, error_data = _do_render(client, params)

        if output_url:
            print(f"\nSUCCESS! Render complete.", flush=True)
            return output_url, None

        # If it was a retriable error and we have retries left, loop again
        if error_data and _is_retriable_error(error_data) and render_attempt < RENDER_RETRIES:
            print(f"  Retriable error detected — will retry after cooldown.", flush=True)
            continue

        # Any other fatal error (or exhausted retries), give up
        err = f"Render failed: {error_data}"
        print(f"\n{err}. Check AWS CloudWatch logs.", flush=True)
        return None, err

