import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import asyncio
import time
import subprocess
from playwright.async_api import async_playwright

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROFILE_DIR = os.path.join(_PROJECT_ROOT, ".tiktok_profile")
_CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
_JSON_OUT = os.path.join(_PROJECT_ROOT, "tiktok_cookies.json")
_TXT_OUT = os.path.join(_PROJECT_ROOT, "tiktok_cookies.txt")

CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

def launch_native_chrome() -> subprocess.Popen:
    """
    Launches genuine Google Chrome as a standalone Windows process with Remote Debugging.
    This completely ELIMINATES the 'Chrome is being controlled by automated test software'
    banner, allowing Google Sign-In and TikTok login to work without security blocks.
    """
    os.makedirs(_PROFILE_DIR, exist_ok=True)
    
    cmd = [
        _CHROME_EXE,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={_PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "https://www.tiktok.com/login",
    ]
    print(f"Launching Real Google Chrome binary: {_CHROME_EXE}")
    return subprocess.Popen(cmd)


async def setup_tiktok_session():
    print("\n" + "="*65)
    print("      REAL GOOGLE CHROME - TIKTOK PERMANENT SESSION SETUP")
    print("="*65)
    print(f"Profile Directory: {_PROFILE_DIR}")
    print("\nNotice:")
    print("1. Standalone Google Chrome is launching WITHOUT automation banners.")
    print("2. Google Sign-In / QR Code will NOT be blocked.")
    print("3. Log in to your TikTok account (@hazy5936).")
    print("4. Your session will be saved permanently on your machine.\n")

    chrome_proc = launch_native_chrome()
    await asyncio.sleep(3)

    try:
        async with async_playwright() as p:
            print("Connecting to your Real Chrome instance...")
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            
            pages = context.pages
            page = pages[0] if pages else await context.new_page()

            print("\n>>> Complete your login in the open Chrome window.")
            print(">>> Monitoring for successful authentication...\n")

            logged_in = False
            for attempt in range(1, 181):
                await asyncio.sleep(2)
                try:
                    current_url = page.url
                    cookies = await context.cookies()
                    cookie_names = {c.get("name", "") for c in cookies}

                    if "sessionid" in cookie_names and "login" not in current_url:
                        print(f"✅ [SUCCESS] Logged in successfully! (URL: {current_url[:45]}...)")
                        logged_in = True
                        break

                    if "sessionid" in cookie_names and attempt > 10:
                        print(f"✅ [SUCCESS] Authentication session token detected.")
                        logged_in = True
                        break

                    if attempt % 15 == 0:
                        print(f"  ...waiting for login ({attempt * 2}s elapsed)")
                except Exception:
                    # Page might be navigating during login
                    pass

            if not logged_in:
                print("\n[NOTE] Automatic detection timed out.")
                input(">>> Once you are logged in, press ENTER in this terminal: ")

            # Verify creator center access
            print("\nNavigating to TikTok Creator Center to verify upload permissions...")
            try:
                await page.goto("https://www.tiktok.com/creator-center/upload?lang=en", wait_until="domcontentloaded", timeout=45000)
                await asyncio.sleep(4)
                if "creator-center/upload" in page.url and "login" not in page.url:
                    print("✅ [VERIFIED] TikTok Creator Center upload page loaded!")
                else:
                    print(f"Current URL: {page.url}")
            except Exception as e:
                print(f"Notice: Verification load check: {e}")

            # Backup export cookies
            try:
                all_cookies = await context.cookies()
                with open(_JSON_OUT, "w", encoding="utf-8") as f:
                    json.dump(all_cookies, f, indent=2)
                print(f"✅ Exported backup cookies to {_JSON_OUT}")

                from src.api.tiktok import _json_to_netscape
                if _json_to_netscape(_JSON_OUT, _TXT_OUT):
                    print(f"✅ Exported backup cookies to {_TXT_OUT}")
            except Exception as e:
                print(f"  (Note: Backup cookie export: {e})")

            print("\n" + "="*65)
            print("🎉 REAL GOOGLE CHROME SESSION SAVED PERMANENTLY!")
            print("="*65)
            print(f"Saved to: {_PROFILE_DIR}")
            print("You can now close the browser and run bulk_tiktok_poster.py.")

    finally:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(setup_tiktok_session())
    except KeyboardInterrupt:
        print("\nSetup cancelled.")
