"""
builder.py — AWS Lambda / Remotion Render Orchestrator v12
-----------------------------------------------------------
CHUNK STRATEGY & LAMBDA LIMITS:
    - Maintain frames_per_lambda = 300 to ensure parallel rendering speed.
    - Single-shot rendering is NOT recommended for videos > 30s.
    - If chunk count gets too high, simplify assets/effects instead of skipping chunking.
    - All videos chunk safely up to 300 frames.

AUDIO VOLUMES (tuned down — previous values were too loud):
    SFX hook:   0.20 → 0.18   (boom at segment 0)
    SFX CTA:    0.20 → 0.18   (riser at last segment)
    SFX mid:    0.15 → 0.13   (all other segments)
    BGM gaming: 0.15
    BGM general: 0.12
    These levels keep voiceover dominant and prevent audio clipping.
"""
import os
import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL     = os.getenv("SERVE_URL", "")
FUNCTION_NAME = os.getenv("FUNCTION_NAME") or "remotion-render-4-0-443-mem3008mb-disk2048mb-900sec"
REGION        = "us-east-1"

RENDER_RETRIES         = 3
RENDER_RETRY_BASE_WAIT = 60
POLL_INTERVAL          = 6
MAX_CONSECUTIVE_ERRORS = 10


def _is_concurrency_error(error_data) -> bool:
    """AWS burst limit / rate limit — retry after cooldown."""
    s = str(error_data).lower()
    return "concurrency limit" in s or "rate exceeded" in s or "throttling" in s


def _is_stitcher_timeout(error_data) -> bool:
    """
    Stitcher timeout — with single-chunk rendering this should NEVER occur.
    If it does, it means something unusual happened (video > 10 min, etc.)
    and retrying with the same config will always fail again.
    """
    s = str(error_data).lower()
    return "timed out" in s or "chunks are missing" in s


def _is_fatal_config_error(error_data) -> bool:
    """Config errors that will never succeed on retry."""
    s = str(error_data).lower()
    return (
        "invalid input" in s
        or "bucket not found" in s
        or "function not found" in s
        or "serve url" in s
        or "access denied" in s
        or "unauthorized" in s
    )


def _do_render(client, params):
    """
    Initiate a single render and poll until done.
    Returns: (output_url, error_data)
    """
    render = None
    for attempt in range(5):
        try:
            render = client.render_media_on_lambda(render_params=params)
            print(f"  Render initiated: {render.render_id}", flush=True)
            break
        except Exception as e:
            print(f"  Lambda invoke failed (attempt {attempt+1}/5): {e}", flush=True)
            if attempt == 4:
                return None, f"invoke_failed_after_5_attempts: {e}"
            time.sleep(5 * (2 ** attempt))

    if render is None:
        return None, "render_object_is_none"

    consecutive_errors = 0
    poll_start = time.time()
    
    while True:
        # Failsafe: Hard timeout of 960 seconds (Lambda 900s limit + buffer)
        if time.time() - poll_start > 960:
            print("\n  AWS LAMBDA FATAL: Polling timeout exceeded. The render function hung.", flush=True)
            return None, "polling_timeout_exceeded_960s"

        try:
            status = client.get_render_progress(
                render_id=render.render_id,
                bucket_name=render.bucket_name,
            )
            consecutive_errors = 0

            if getattr(status, "fatalErrorEncountered", False):
                error_data = getattr(status, "errors", "Unknown Lambda error")
                safe_err   = str(error_data).encode("ascii", "ignore").decode("ascii")
                print(f"\n  AWS LAMBDA FATAL: {safe_err[:400]}", flush=True)
                return None, error_data

            if getattr(status, "done", False):
                output = getattr(status, "outputFile", None)
                if not output:
                    return None, "render_done_but_no_output_file"
                print(f"\n  Render output: {str(output)[:80]}", flush=True)
                return str(output), None

            pct = getattr(status, "overallProgress", 0) * 100
            print(f"  Progress: {pct:.1f}%", end="\r", flush=True)

        except Exception as e:
            consecutive_errors += 1
            print(f"\n  Poll error ({consecutive_errors}/{MAX_CONSECUTIVE_ERRORS}): {e}", flush=True)
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                return None, f"poll_failed_after_{MAX_CONSECUTIVE_ERRORS}_errors: {e}"

        time.sleep(POLL_INTERVAL)


def _do_local_render(input_props, total_frames, output_path="temp_render_local.mp4"):
    """
    Renders video locally using Remotion CLI to save 100% of AWS Lambda GB-Seconds.
    """
    import subprocess
    import json
    import sys

    print("\n  ⚡ [LOCAL RENDER ENGINE] Rendering locally via Remotion CLI (Zero AWS Lambda Cost)...", flush=True)
    temp_props_file = os.path.abspath(f"hazy-remotion-cloud/temp_props_{int(time.time())}.json")
    try:
        with open(temp_props_file, "w", encoding="utf-8") as pf:
            json.dump(input_props, pf)

        out_file = os.path.abspath(output_path)
        cmd = [
            "npx", "remotion", "render",
            "src/index.ts", "MyComp",
            out_file,
            f"--props={temp_props_file}",
            f"--frames=0-{total_frames-1}",
            "--overwrite"
        ]
        res = subprocess.run(
            cmd,
            cwd="hazy-remotion-cloud",
            shell=True if sys.platform == "win32" else False,
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        if res.returncode == 0 and os.path.exists(out_file):
            print(f"  ✓ Local render complete: {out_file}", flush=True)
            return out_file, None
        else:
            err = f"Local render process failed: {res.stderr[:400] if res.stderr else res.stdout[:400]}"
            print(f"  ❌ {err}", flush=True)
            return None, err
    except Exception as e:
        return None, f"Local render exception: {e}"
    finally:
        if os.path.exists(temp_props_file):
            try:
                os.remove(temp_props_file)
            except Exception:
                pass


def make_cloud_video(
    voice_url,
    background_urls,
    sfx_urls,
    bgm_url,
    segments_data,
    duration_seconds,
    category="general",
    render_seed=0,
    word_timestamps=None,
):
    """
    Render a video using AWS Lambda or Local Remotion CLI fallback.
    Returns: (output_url: str | None, error_msg: str | None)
    """
    global SERVE_URL
    render_mode = os.getenv("RENDER_MODE", "cloud").lower()
    use_local   = os.getenv("USE_LOCAL_RENDER", "").lower() in ["true", "1", "yes"]

    if not background_urls:
        return None, "No background video URLs provided"

    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"  Frame count: {total_frames} ({duration_seconds:.1f}s × 30fps + 15)", flush=True)

    if total_frames < 150:
        return None, f"Video too short: {total_frames} frames (min 150)"

    # Lowering this to 300 to prevent AWS Lambda 15-minute timeouts.
    frames_per_lambda = min(total_frames, 300)
    chunk_count = math.ceil(total_frames / frames_per_lambda)
    print(f"  Render plan: {total_frames} frames → {chunk_count} chunk(s) of {frames_per_lambda}f (Safety Chunking v13.5-ENFORCED)", flush=True)

    if chunk_count >= 5:
        print(f"  WARNING: High chunk count ({chunk_count}). Stitcher may time out. Consider increasing Lambda Timeout or simplifying the video.", flush=True)

    bgm_volume = 0.15 if category == "gaming" else 0.12

    input_props = {
        "audioUrl":       voice_url,
        "videoUrls":      background_urls,
        "sfxUrls":        sfx_urls or [],
        "bgmUrl":         bgm_url or "",
        "bgmVolume":      bgm_volume,
        "segments":       segments_data,
        "renderSeed":     render_seed,
        "category":       category,
        "wordTimestamps": word_timestamps or [],
        "effects": {
            "zoom":       True,
            "transition": "fade",
            "textStyle":  "bold",
        },
    }

    # COST-CONTAINMENT SAFEGUARD: Direct local rendering toggle to preserve AWS Free Tier
    if render_mode == "local" or use_local or not SERVE_URL:
        if not SERVE_URL and not (render_mode == "local" or use_local):
            print("  [NOTICE] SERVE_URL not configured. Automatically routing to Local Remotion Render engine...", flush=True)
        local_path, local_err = _do_local_render(input_props, total_frames, f"temp_render_{category}.mp4")
        if local_path:
            return local_path, None
        return None, f"Local render failed: {local_err}"
    # all available CPU threads in the 3GB Lambda. This is ~4x faster per chunk
    # than the old concurrency_per_lambda=1 setting.
    params = RenderMediaParams(
        serve_url=SERVE_URL,
        composition="MyComp",
        force_duration_in_frames=total_frames,
        frames_per_lambda=frames_per_lambda,
        timeout_in_milliseconds=900000,
        input_props=input_props,
    )
    print(f"  RenderMediaParams: {chunk_count} chunk(s) of {frames_per_lambda}f, full CPU concurrency", flush=True)

    client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)
    print("  Requesting AWS Lambda render...", flush=True)

    for attempt in range(RENDER_RETRIES + 1):
        if attempt > 0:
            wait = RENDER_RETRY_BASE_WAIT * (2 ** (attempt - 1))
            print(f"\n  [Retry {attempt}/{RENDER_RETRIES}] Cooling down {wait}s...", flush=True)
            time.sleep(wait)

        output_url, error_data = _do_render(client, params)

        if output_url:
            print(f"  SUCCESS! Render complete.", flush=True)
            return output_url, None

        if error_data:
            if _is_fatal_config_error(error_data):
                if "compositions" in str(error_data).lower() or "serve url" in str(error_data).lower():
                    print("\n  AWS LAMBDA FATAL: Remotion bundle missing or returning 403.", flush=True)
                    print("  AUTO-HEALING: Triggering Remotion site deployment from builder...", flush=True)
                    try:
                        import subprocess
                        import sys
                        import re
                        
                        print("  -> Installing Node dependencies...", flush=True)
                        subprocess.run(
                            ["npm", "install"],
                            cwd="hazy-remotion-cloud",
                            shell=True if sys.platform == "win32" else False,
                            check=True,
                            stdout=subprocess.DEVNULL
                        )
                        print("  -> Deploying site...", flush=True)
                        result = subprocess.run(
                            ["npx", "remotion", "lambda", "sites", "create", "src/index.ts", "--site-name=hazy-factory"],
                            cwd="hazy-remotion-cloud",
                            shell=True if sys.platform == "win32" else False,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            check=True
                        )
                        print("  AUTO-HEALING SUCCESS: Remotion site redeployed.", flush=True)
                        
                        match = re.search(r"Serve URL\s+(https://[^\s\x1b]+)", result.stdout)
                        if match:
                            new_url = match.group(1).replace("/index.html", "")
                            SERVE_URL = new_url
                            os.environ["SERVE_URL"] = new_url
                            params.serve_url = new_url
                            print(f"  Updated SERVE_URL to: {new_url}", flush=True)
                            client = RemotionClient(region=REGION, serve_url=SERVE_URL, function_name=FUNCTION_NAME)
                        
                        print("  Retrying render after healing...", flush=True)
                        continue
                    except Exception as e:
                        err = f"Fatal config error (auto-healing failed): {e}\nOriginal error: {str(error_data)[:200]}"
                        print(f"\n  {err}", flush=True)
                        return None, err
                
                err = f"Fatal config error (no retry useful): {str(error_data)[:200]}"
                print(f"\n  {err}", flush=True)
                return None, err

            if _is_stitcher_timeout(error_data):
                if attempt < RENDER_RETRIES:
                    # Stitcher timeout or Chunk timeout in single/multi-chunk mode.
                    # This means the render is too slow for the 900s Lambda limit.
                    print(f"  Render timeout (Attempt {attempt+1}) — will retry. Likely heavy assets or long duration.", flush=True)
                    continue
                
                err = (
                    f"Lambda Timeout (900s) after all retries. The video is too complex or long for the current {frames_per_lambda}f chunks. "
                    "ACTION: Reduce video length or simplify assets."
                )
                print(f"\n  {err}", flush=True)
                return None, err

            if _is_concurrency_error(error_data) and attempt < RENDER_RETRIES:
                print("  AWS concurrency error — will retry after cooldown.", flush=True)
                continue

        err = str(error_data or "unknown_error")[:300]
        print(f"\n  Render failed: {err}", flush=True)
        return None, err

    return None, "All render attempts exhausted"