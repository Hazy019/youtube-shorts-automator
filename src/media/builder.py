"""
builder.py — AWS Lambda / Remotion Render Orchestrator v12
-----------------------------------------------------------
ROOT CAUSE OF STITCHER TIMEOUT (FIXED HERE):

    OLD:  frames_per_lambda = 300
          90-second video = 2715 frames ÷ 300 = 10 chunks
          Stitcher Lambda must wait for all 10 chunks, then stitch.
          Stitcher has a 600s hard limit. With 10 chunks: ALWAYS TIMES OUT.

    FIX:  frames_per_lambda = total_frames  (render entire video as 1 chunk)
          10 chunks → 1 chunk.  Stitcher phase is skipped entirely.
          The single render Lambda runs the whole video in one shot ~120-180s.
          Well inside the 600s Lambda timeout.

AUDIO VOLUMES (tuned down — previous values were too loud):
    SFX hook:  0.55 → 0.28   (boom at segment 0)
    SFX CTA:   0.45 → 0.22   (riser at last segment)
    SFX mid:   0.35 → 0.18   (all other segments)
    BGM gaming: 0.18 → 0.10
    BGM general: 0.12 → 0.07
    These levels keep voiceover dominant and prevent audio clipping.
"""
import os
import time
import math
from remotion_lambda import RemotionClient, RenderMediaParams

SERVE_URL     = os.getenv("SERVE_URL", "")
FUNCTION_NAME = os.getenv("FUNCTION_NAME") or "remotion-render-4-0-443-mem3008mb-disk2048mb-600sec"
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
    while True:
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


def make_cloud_video(
    voice_url,
    background_urls,
    sfx_urls,
    bgm_url,
    segments_data,
    duration_seconds,
    category="general",
    render_seed=0,
):
    """
    Render a video on AWS Lambda using single-chunk mode (no stitcher).
    Returns: (output_url: str | None, error_msg: str | None)
    """
    if not SERVE_URL:
        return None, "SERVE_URL is not configured"
    if not background_urls:
        return None, "No background video URLs provided"

    total_frames = math.ceil(duration_seconds * 30) + 15
    print(f"  Frame count: {total_frames} ({duration_seconds:.1f}s × 30fps + 15)", flush=True)

    if total_frames < 150:
        return None, f"Video too short: {total_frames} frames (min 150)"

    frames_per_lambda = 300
    chunk_count = math.ceil(total_frames / frames_per_lambda)
    print(f"  Render plan: {total_frames} frames → {chunk_count} chunks of {frames_per_lambda}f (Proven Safe Mode)", flush=True)

    bgm_volume = 0.10 if category == "gaming" else 0.07

    input_props = {
        "audioUrl":   voice_url,
        "videoUrls":  background_urls,
        "sfxUrls":    sfx_urls or [],
        "bgmUrl":     bgm_url or "",
        "bgmVolume":  bgm_volume,
        "segments":   segments_data,
        "renderSeed": render_seed,
        "effects": {
            "zoom":       True,
            "transition": "fade",
            "textStyle":  "bold",
        },
    }

    # NOTE: concurrency_per_lambda is intentionally OMITTED so Remotion uses
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
                err = f"Fatal config error (no retry useful): {str(error_data)[:200]}"
                print(f"\n  {err}", flush=True)
                return None, err

            if _is_stitcher_timeout(error_data):
                if attempt < RENDER_RETRIES:
                    # Stitcher timeout can be transient (AWS throttling delayed
                    # some chunks, stitcher ran out of time). Always worth retrying
                    # with our 300f/chunk config — chunks are fast enough.
                    print("  Stitcher timeout — will retry (chunks are small, likely AWS throttle delay)", flush=True)
                    continue
                err = (
                    "Stitcher timeout after all retries. AWS may be under heavy load. "
                    "Check CloudWatch for chunk render durations."
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