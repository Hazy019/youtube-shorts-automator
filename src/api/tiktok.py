import os
import json
import time
from src.utils.discord import ping_error

NETSCAPE_PATH = "tiktok_cookies.txt"
JSON_PATH = "tiktok_cookies.json"
_temp_files = []

# Project root is always two levels above this file (src/api/tiktok.py → root)
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _json_to_netscape(json_path: str, netscape_path: str) -> bool:
    """Convert Playwright-format JSON cookies → Netscape HTTP format."""
    if not os.path.exists(json_path):
        print(f"Warning: Cookie file {json_path} does not exist.")
        return False

    if os.path.getsize(json_path) == 0:
        print(f"Warning: Cookie file {json_path} is empty.")
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {json_path} is not a valid JSON file.")
        return False

    lines = ["# Netscape HTTP Cookie File", "# https://curl.se/docs/http-cookies.html", ""]
    for c in cookies:
        domain  = c.get("domain", "")
        flag    = "TRUE" if domain.startswith(".") else "FALSE"
        path    = c.get("path", "/")
        secure  = "TRUE" if c.get("secure", False) else "FALSE"
        expires = c.get("expires", -1)
        # Session cookies have expires=-1; set a 30-day future timestamp instead
        if not expires or expires <= 0:
            expires = int(time.time()) + 30 * 24 * 3600
        name  = c.get("name", "")
        value = c.get("value", "")
        lines.append(f"{domain}\t{flag}\t{path}\t{secure}\t{int(expires)}\t{name}\t{value}")

    with open(netscape_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Converted JSON -> Netscape: {netscape_path}")
    return True


def _netscape_to_json(netscape_path: str, json_path: str = None) -> list:
    """Convert Netscape HTTP format cookies → Playwright JSON cookies list and optionally saves to file."""
    if not os.path.exists(netscape_path) or os.path.getsize(netscape_path) == 0:
        return []

    cookies = []
    with open(netscape_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, flag, path, secure, expires, name, value = parts[:7]
                try:
                    exp_val = float(expires)
                    if exp_val <= 0:
                        exp_val = -1
                except (ValueError, TypeError):
                    exp_val = -1

                cookie_dict = {
                    "name": name,
                    "value": value,
                    "domain": domain,
                    "path": path or "/",
                    "secure": secure.upper() == "TRUE",
                }
                if exp_val > 0:
                    cookie_dict["expires"] = exp_val
                cookies.append(cookie_dict)

    if json_path and cookies:
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(cookies, f, indent=2)
            print(f"Converted Netscape -> JSON: {json_path}")
        except Exception as e:
            print(f"Warning: Failed to write {json_path}: {e}")

    return cookies


def get_playwright_cookies() -> list:
    """Returns a list of cookie dicts formatted for Playwright context.add_cookies()."""
    txt_path = _prepare_cookies()
    if not txt_path or not os.path.exists(txt_path):
        return []

    # Use project-root JSON path (absolute) — not the relative JSON_PATH constant
    json_path = os.path.join(_PROJECT_ROOT, "tiktok_cookies.json")
    if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception:
            pass

    return _netscape_to_json(txt_path, json_path)


def check_cookie_expiry(warn_days: int = 7) -> bool:
    """
    Checks the TikTok cookie file for expiring/expired critical session cookies.
    Returns True if cookies are healthy, False if action is needed.
    Sends a Discord ping if any critical cookie expires within `warn_days` days.
    """
    json_path = os.path.join(_PROJECT_ROOT, "tiktok_cookies.json")
    if not os.path.exists(json_path):
        print("[Cookie Check] No tiktok_cookies.json found.")
        return False

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception as e:
        print(f"[Cookie Check] Failed to read cookies: {e}")
        return False

    now = time.time()
    warn_threshold = now + warn_days * 86400
    critical = {"sessionid", "sid_tt", "passport_auth_status"}
    issues = []

    for c in cookies:
        name = c.get("name", "")
        if name not in critical:
            continue
        expires = c.get("expires", -1)
        if not expires or expires <= 0:
            continue  # session cookie, no expiry
        if expires < now:
            issues.append(f"  ❌ '{name}' EXPIRED on {time.strftime('%Y-%m-%d', time.localtime(expires))}")
        elif expires < warn_threshold:
            days_left = int((expires - now) / 86400)
            issues.append(f"  ⚠️  '{name}' expires in {days_left} day(s) ({time.strftime('%Y-%m-%d', time.localtime(expires))})")

    if issues:
        msg = "TikTok cookie expiry warning:\n" + "\n".join(issues) + "\n\nRe-run tools/capture_tiktok_cookies.py to refresh."
        print(f"[Cookie Check]\n{msg}")
        ping_error(msg, "TikTok Cookie Expiry")
        return False

    print("[Cookie Check] All critical cookies are healthy.")
    return True


def _prepare_cookies() -> str | None:
    """
    Resolves cookie file in priority order:
      1. TIKTOK_COOKIES_TXT env var  (Netscape format directly)
      2. TIKTOK_COOKIES_JSON env var (Playwright JSON → converted)
      3. Project-root tiktok_cookies.txt / tiktok_cookies.json
      4. CWD tiktok_cookies.txt / tiktok_cookies.json
      5. tools/ subfolder (where capture_tiktok_cookies.py may save to)
    Returns path to Netscape file (always in project root), or None if no cookies found.
    Also ensures both .txt and .json formats are synchronized.
    """
    # Always write resolved Netscape file into the project root so paths are stable
    netscape_out = os.path.join(_PROJECT_ROOT, "tiktok_cookies.txt")
    json_out     = os.path.join(_PROJECT_ROOT, "tiktok_cookies.json")

    # 1. Netscape text directly from env secret
    txt_env = os.getenv("TIKTOK_COOKIES_TXT", "").strip()
    if txt_env:
        with open(netscape_out, "w", encoding="utf-8") as f:
            f.write(txt_env)
        print("TikTok cookies written from TIKTOK_COOKIES_TXT secret.")
        _temp_files.append(netscape_out)
        _netscape_to_json(netscape_out, json_out)
        _temp_files.append(json_out)
        return netscape_out

    # 2. JSON from env secret → convert
    json_env = os.getenv("TIKTOK_COOKIES_JSON", "").strip()
    if json_env:
        if not (json_env.startswith("[") or json_env.startswith("{")):
            print("Warning: TIKTOK_COOKIES_JSON env variable does not look like JSON. Skipping.")
        else:
            with open(json_out, "w", encoding="utf-8") as f:
                f.write(json_env)
            print("TikTok JSON cookies written from TIKTOK_COOKIES_JSON secret.")
            _temp_files.append(json_out)
            if _json_to_netscape(json_out, netscape_out):
                _temp_files.append(netscape_out)
                return netscape_out

    # 3 & 4. Search known locations for .txt or .json files
    # Priority: project root > cwd > tools/ subfolder
    search_roots = list(dict.fromkeys([
        _PROJECT_ROOT,
        os.getcwd(),
        os.path.join(_PROJECT_ROOT, "tools"),
    ]))

    for root in search_roots:
        txt_path = os.path.join(root, "tiktok_cookies.txt")
        if os.path.exists(txt_path) and os.path.getsize(txt_path) > 0:
            abs_txt = os.path.abspath(txt_path)
            abs_out = os.path.abspath(netscape_out)
            if abs_txt != abs_out:
                import shutil
                shutil.copy(txt_path, netscape_out)
                print(f"Using local cookies from: {txt_path}")
            else:
                print(f"Using local cookies: {netscape_out}")
            _netscape_to_json(netscape_out, json_out)
            return netscape_out

    for root in search_roots:
        json_path = os.path.join(root, "tiktok_cookies.json")
        if os.path.exists(json_path) and os.path.getsize(json_path) > 0:
            print(f"Found local {json_path}, converting...")
            abs_json = os.path.abspath(json_path)
            abs_out  = os.path.abspath(json_out)
            if abs_json != abs_out:
                import shutil
                shutil.copy(json_path, json_out)
            if _json_to_netscape(json_out, netscape_out):
                return netscape_out

    print(f"DEBUG: No local cookie files found in: {search_roots}")
    return None


def _validate_netscape(path: str) -> bool:
    """Quick sanity check that critical TikTok session cookies exist."""
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    critical = ["sessionid", "sid_tt"]
    missing = [c for c in critical if c not in content]
    if missing:
        print(f"WARNING: TikTok cookies missing critical fields: {missing}")
        print(f"Cookie file content length: {len(content)} bytes")
        if len(content) < 50:
            print(f"Cookie file preview: {content}")
        print("Your TikTok session may be expired. Re-run tools/capture_tiktok_cookies.py locally.")
        return False
    print("TikTok cookies validated successfully.")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# SELF-CONTAINED TIKTOK UPLOADER — Zero library dependencies
#
# WHY WE ABANDONED tiktok-uploader LIBRARY INTERNALS:
#
#  Problem 1 — Chrome 58 UA:
#    config.toml hardcodes user_agent = 'Chrome/58.0.3029.110' (2017).
#    TikTok's bot detection immediately flags this → login redirect.
#
#  Problem 2 — TikTokUploader.page is a lazy property:
#    upload_videos() always calls self.page, which calls get_browser() →
#    sync_playwright().start(). Passing browser_agent= only works on the
#    MODULE-LEVEL upload_videos() function, NOT on the class method.
#    complete_upload_form() calls _go_to_upload() which re-enters this path.
#
#  Problem 3 — asyncio conflict:
#    Supabase/httpx starts a ProactorEventLoop on Windows. sync_playwright()
#    detects any running loop and throws "Please use the Async API instead."
#    asyncio.set_event_loop(new_event_loop()) doesn't help because the library
#    spawns a SECOND sync_playwright() call inside complete_upload_form.
#
#  Solution:
#    Use async_playwright inside asyncio.run() in a worker thread.
#    asyncio.run() creates a BRAND NEW isolated event loop — no conflicts.
#    We own 100% of the browser lifecycle. Zero library code is called.
# ─────────────────────────────────────────────────────────────────────────────

UPLOAD_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
UPLOAD_URL = "https://www.tiktok.com/creator-center/upload?lang=en"


_PROFILE_DIR = os.path.join(_PROJECT_ROOT, ".tiktok_profile")


async def _async_tiktok_upload(video_path: str, caption: str, headless: bool = False) -> str:
    """
    Fully self-contained async Playwright TikTok uploader.
    
    Session Architecture:
      1. Primary: Uses hardware-bound persistent browser profile (.tiktok_profile/)
         which preserves cookies, localStorage, IndexedDB, and WebMS SDK device tokens.
      2. Fallback: Uses standard context + injected cookies (for CI/GitHub Actions).
    """
    from playwright.async_api import async_playwright
    import asyncio

    has_persistent_profile = os.path.exists(_PROFILE_DIR) and len(os.listdir(_PROFILE_DIR)) > 0
    playwright_cookies = get_playwright_cookies() if not has_persistent_profile else []

    if not has_persistent_profile and not playwright_cookies:
        raise RuntimeError(
            "No TikTok session found! Please run 'tools/setup_tiktok_session.py' to create "
            "a permanent session, or provide 'tiktok_cookies.txt'."
        )

    async with async_playwright() as p:
        browser = None
        context = None

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ]

        if has_persistent_profile:
            print(f"  [Session] Using permanent real Chrome profile: {_PROFILE_DIR}")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=_PROFILE_DIR,
                channel="chrome",  # Uses official installed Google Chrome (chrome.exe)
                headless=headless,
                user_agent=UPLOAD_UA,
                viewport={"width": 1280, "height": 720},
                locale="en-US",
                ignore_default_args=["--enable-automation"],
                args=launch_args,
            )
            pages = context.pages
            page = pages[0] if pages else await context.new_page()
        else:
            print(f"  [Session] Fallback: Using ephemeral context with {len(playwright_cookies)} cookies")
            browser = await p.chromium.launch(
                channel="chrome",  # Uses official installed Google Chrome (chrome.exe)
                headless=headless,
                ignore_default_args=["--enable-automation"],
                args=launch_args,
            )
            context = await browser.new_context(
                user_agent=UPLOAD_UA,
                viewport={"width": 1280, "height": 720},
                locale="en-US",
            )
            await context.add_cookies(playwright_cookies)
            page = await context.new_page()

        # Mask automation fingerprints BEFORE any page load
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
            window.chrome = { runtime: {} };
        """)

        try:
            # ── Step 1: Navigate to upload page ──────────────────────────────
            print("  [Nav] Navigating to TikTok Creator Center upload...")
            await page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(4)

            current_url = page.url
            if "login" in current_url or "explore" in current_url:
                raise RuntimeError(
                    f"TikTok redirected to '{current_url}' — session is not authenticated. "
                    "Please run 'tools/setup_tiktok_session.py' in real Chrome to log in."
                )
            print(f"  [Auth OK] Upload page confirmed: {current_url}")

            # ── Step 2: Dismiss cookie/GDPR banners ──────────────────────────
            try:
                banner = page.locator("tiktok-cookie-banner")
                if await banner.is_visible(timeout=4000):
                    btn = banner.locator("div.button-wrapper button").last
                    await btn.click()
                    print("  [UI] Dismissed cookie banner.")
            except Exception:
                pass

            # ── Step 3: Dismiss 'Not now' split-window popup ─────────────────
            try:
                split = page.locator("//button[./div[text()='Not now']]")
                if await split.is_visible(timeout=4000):
                    await split.click()
                    print("  [UI] Dismissed split-window popup.")
            except Exception:
                pass

            # ── Step 4: Dismiss 'Got it' / promotional modals ────────────────
            for selector in [
                "//button[.//div[text()='Got it']]",
                "//button[.//div[text()='Okay']]",
                "//button[.//div[text()='OK']]",
            ]:
                try:
                    btn = page.locator(selector)
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        print(f"  [UI] Dismissed popup: {selector}")
                        await asyncio.sleep(1)
                except Exception:
                    pass

            # ── Step 5: Upload the video file ────────────────────────────────
            print(f"  [Upload] Setting video file: {video_path}")
            abs_video_path = os.path.abspath(video_path)
            file_input = None

            # Check direct page input, iframe input, or video-accept inputs
            selectors = [
                "input[type='file']",
                "input[accept*='video']",
                "input[accept*='mp4']",
                "div.upload-wrapper input",
            ]

            for s in selectors:
                try:
                    cand = page.locator(s).first
                    if await cand.count() > 0:
                        file_input = cand
                        break
                except Exception:
                    pass

            if not file_input:
                try:
                    frame = page.frame_locator("iframe").first
                    for s in selectors:
                        cand = frame.locator(s).first
                        if await cand.count() > 0:
                            file_input = cand
                            break
                except Exception:
                    pass

            if not file_input:
                # Direct Playwright helper fallback
                try:
                    await page.set_input_files("input[type='file']", abs_video_path, timeout=15000)
                    file_input = True  # handled
                except Exception:
                    raise RuntimeError("Could not find file input on the upload page. Check if logged in.")

            if file_input is not True and file_input is not None:
                await file_input.set_input_files(abs_video_path)

            print("  [Upload] File queued. Waiting for processing...")

            # ── Step 6: Wait for upload processing to complete ───────────────
            upload_done = False
            for _ in range(90):  # up to 3 minutes
                for indicator in [
                    "//div[contains(@class, 'resolution-label-text')]",
                    "//div[contains(@class, 'btn-cancel')]",
                    "//div[contains(@class, 'upload-caption')]",
                ]:
                    try:
                        if await page.locator(indicator).is_visible(timeout=1000):
                            upload_done = True
                            break
                    except Exception:
                        pass
                if upload_done:
                    break
                await asyncio.sleep(2)

            if not upload_done:
                print("  [Upload] Warning: processing indicator not detected. Continuing...")

            # ── Step 7: Fill in the description / caption ────────────────────
            print("  [Caption] Filling description...")
            try:
                desc_box = page.locator("//div[@contenteditable='true']").first
                await desc_box.wait_for(state="visible", timeout=15000)
                await desc_box.click()
                await page.keyboard.press("Control+a")
                await asyncio.sleep(0.3)
                await page.keyboard.press("Delete")
                await asyncio.sleep(0.3)
                # Type in chunks to handle long captions
                chunk_size = 200
                for i in range(0, len(caption), chunk_size):
                    await desc_box.type(caption[i:i + chunk_size], delay=10)
                print(f"  [Caption] Set ({len(caption)} chars).")
            except Exception as e:
                print(f"  [Caption] Warning: could not set description: {e}")

            await asyncio.sleep(2)

            # ── Step 8: Click Post ────────────────────────────────────────────
            print("  [Post] Clicking post button...")
            post_btn = page.locator("//button[@data-e2e='post_video_button']")
            try:
                await post_btn.wait_for(state="visible", timeout=20000)
                # Wait until button is enabled
                for _ in range(30):
                    disabled = await post_btn.get_attribute("data-disabled")
                    if disabled == "false" or disabled is None:
                        break
                    await asyncio.sleep(2)
                await post_btn.scroll_into_view_if_needed()
                await post_btn.click()
            except Exception:
                print("  [Post] Fallback JS click...")
                await page.evaluate("document.querySelector(\"[data-e2e='post_video_button']\").click()")

            # Handle 'Post now' confirmation dialog if it appears
            try:
                post_now = page.locator("//button[.//div[text()='Post now']]")
                if await post_now.is_visible(timeout=5000):
                    await post_now.click()
            except Exception:
                pass

            # ── Step 9: Wait for success confirmation ─────────────────────────
            print("  [Confirm] Waiting for upload confirmation...")
            confirm_sel = (
                "//div[contains(text(), 'Your video has been uploaded') "
                "or contains(text(), 'Video published') "
                "or contains(text(), 'uploaded to TikTok')]"
            )
            try:
                await page.locator(confirm_sel).wait_for(state="attached", timeout=60000)
                print("  ✅ [SUCCESS] TikTok upload confirmed!")
            except Exception:
                print("  [Confirm] Warning: confirmation not detected. Upload may have succeeded anyway.")

            await asyncio.sleep(3)
            return "success"

        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


def _do_tiktok_upload(video_path: str, caption: str, headless: bool = False) -> str:
    """
    Sync entry point — wraps the async uploader in asyncio.run().

    asyncio.run() creates a BRAND NEW event loop in the calling context,
    completely isolated from the main thread's ProactorEventLoop (Supabase/httpx).
    sync_playwright() is NEVER called anywhere in this code path.
    """
    import asyncio
    return asyncio.run(_async_tiktok_upload(video_path, caption, headless=headless))


# Sentinel aliases kept for any external imports (no longer functional)
_build_stealth_page = None
_build_stealth_uploader_page = None


def upload_to_tiktok(video_path, title, description, tags=None):
    print(f"\nPreparing TikTok upload for: {video_path}")

    has_persistent = os.path.exists(_PROFILE_DIR) and len(os.listdir(_PROFILE_DIR)) > 0
    cookies_path = None

    if not has_persistent:
        check_cookie_expiry(warn_days=7)
        cookies_path = _prepare_cookies()
        if not cookies_path:
            msg = ("No TikTok session found. Run 'tools/setup_tiktok_session.py' to create "
                   "a permanent session, or provide 'tiktok_cookies.txt'.")
            print(f"[TikTok SKIP] {msg}")
            ping_error(msg, "TikTok Auth")
            return None

        if not _validate_netscape(cookies_path):
            msg = "TikTok cookies are invalid or expired. Run 'tools/setup_tiktok_session.py' to refresh."
            ping_error(msg, "TikTok Auth")
            _cleanup()
            return None
    else:
        print(f"Using permanent TikTok browser profile: {_PROFILE_DIR}")

    hashtags = " ".join(f"#{t}" for t in tags) if tags else "#shorts #gaming #facts"
    caption = f"{title}\n\n{description[:1400]}\n\n{hashtags}"[:2200]

    try:
        import threading

        is_headless = os.getenv("GITHUB_ACTIONS") == "true"
        thread_result = None
        thread_err = None

        def _run_upload():
            nonlocal thread_result, thread_err
            try:
                thread_result = _do_tiktok_upload(video_path, caption, headless=is_headless)
            except Exception as e:
                thread_err = e

        print(f"Launching async stealth browser (Headless: {is_headless}, UA: Chrome/124)...")
        t = threading.Thread(target=_run_upload)
        t.start()
        t.join()

        if thread_err:
            raise thread_err

        print(f"TikTok upload result: {thread_result}")
        return "TikTok Upload Complete"

    except Exception as e:
        err = str(e)
        print(f"[TikTok ERROR] {err}")
        ping_error(err, "TikTok Upload")
        return None

    finally:
        _cleanup()


def _cleanup():
    """Remove temp cookie files created from env vars."""
    global _temp_files
    for path in _temp_files:
        if os.path.exists(path):
            try:
                os.remove(path)
                print(f"Cleaned up temp session file: {path}")
            except:
                pass
    _temp_files = []