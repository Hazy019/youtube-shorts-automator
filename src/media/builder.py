import os
import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL = os.getenv("SERVE_URL")
FUNCTION_NAME = os.getenv("FUNCTION_NAME") or "remotion-render-4-0-443-mem3008mb-disk2048mb-600sec"
REGION = "us-east-1"

RENDER_RETRIES = 3
RENDER_RETRY_BASE_WAIT = 60

def _is_concurrency_error(error_data) -> bool:
    """
    Returns True for AWS concurrency / rate errors that benefit from a
    cooldown + retry (waiting for Lambda capacity to free up).
    NOTE: Stitcher timeouts are intentionally excluded — retrying with the
    same chunk config will ALWAYS time out again and wastes 50+ minutes.
    """
    err_str = str(error_data).lower()
    return (
        "concurrency limit" in err_str
        or "rate exceeded" in err_str
    )

def _is_stitcher_timeout(error_data) -> bool:
    """
    Returns True when the Lambda stitcher function itself timed out
    (600-second hard limit) or produced incomplete chunks.
    These are FATAL — a retry with the same params will always re-timeout.
    """
    err_str = str(error_data).lower()
    return (
        "timed out" in err_str
        or "chunks are missing" in err_str
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

    consecutive_errors = 0
    MAX_CONSECUTIVE_ERRORS = 10
    while True:
        try:
            status = client.get_render_progress(
                render_id=render.render_id,
                bucket_name=render.bucket_name
            )
            consecutive_errors = 0

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
            consecutive_errors += 1
            print(f"\nNetwork error polling render status ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}. Retrying in 5s...", flush=True)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print("  FATAL: Too many consecutive poll errors. Aborting.", flush=True)
                return None, f"Poll failed after {MAX_CONSECUTIVE_ERRORS} consecutive errors: {e}"

        time.sleep(5)


def make_cloud_video(voice_url, background_urls, sfx_urls, bgm_url, segments_data, duration_seconds, category="gaming", render_seed=0):
    client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)

    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"Commanding Lambda to render {total_frames} frames with professional effects...", flush=True)

    if total_frames < 150:
        err = "ERROR: Video duration too short. Aborting render."
        print(err, flush=True)
        return None, err

    frames_per_lambda = 300
    chunk_count = math.ceil(total_frames / frames_per_lambda)
    print(f"Render plan: {total_frames} frames → {chunk_count} chunks @ {frames_per_lambda} frames/chunk", flush=True)

    bgm_volume = 0.18 if category == "gaming" else 0.12

    try:
        params = RenderMediaParams(
            serve_url=SERVE_URL,
            composition="MyComp",
            force_duration_in_frames=total_frames,
            frames_per_lambda=frames_per_lambda,
            concurrency_per_lambda=1,
            timeout_in_milliseconds=600000,
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
    except TypeError:
        print("  Warning: SDK does not support frames_per_lambda — using defaults.", flush=True)
        params = RenderMediaParams(
            serve_url=SERVE_URL,
            composition="MyComp",
            force_duration_in_frames=total_frames,
            timeout_in_milliseconds=600000,
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

        if error_data and _is_stitcher_timeout(error_data):
            err = (
                f"Render failed (stitcher timeout — Lambda 600s limit exceeded). "
                f"The video may be too long or chunk config needs adjustment. "
                f"NOT retrying. Check AWS CloudWatch logs."
            )
            print(f"\n{err}", flush=True)
            return None, err

        if error_data and _is_concurrency_error(error_data) and render_attempt < RENDER_RETRIES:
            print(f"  AWS concurrency error — will retry after cooldown.", flush=True)
            continue
        err = f"Render failed: {error_data}"
        print(f"\n{err}. Check AWS CloudWatch logs.", flush=True)
        return None, err

