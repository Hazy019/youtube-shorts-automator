import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import asyncio
import time
from playwright.async_api import async_playwright

async def capture_cookies():
    print("\n" + "="*50)
    print("      --- TIKTOK COOKIE CAPTURER v2 ---")
    print("="*50)
    print("1. A browser will open for TikTok login.")
    print("2. Log in manually (QR Code is easiest).")
    print("3. Watch the terminal for [DETECTED] messages.")
    print("4. If logged in but not detected, press ENTER in the terminal.")
    
    async with async_playwright() as p:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(user_agent=user_agent)
        page = await context.new_page()
        
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
            print("  [Stealth] Playwright-stealth applied.")
        except ImportError:
            print("  [Note] playwright-stealth not found, proceeding with standard stealth.")

        print("\nACTION: Navigating to TikTok login...")
        await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=60000)
        
        print("ACTION: Please log in in the browser window.")
        print("Waiting for session... (Polling 180s)")

        logged_in = False
        detected_names = set()
        
        # We use a non-blocking way to check for sessionid
        for i in range(180):
            cookies = await context.cookies()
            cookie_names = {c.get("name", "") for c in cookies}
            
            # Show new cookies detected
            new_cookies = cookie_names - detected_names
            if new_cookies:
                # We only print interesting ones to avoid spam
                interesting = {"sessionid", "sid_tt", "tt_csrf_token", "ttwid", "msToken", "odin_tt"}
                found_interesting = new_cookies.intersection(interesting)
                if found_interesting:
                    print(f"  [FOUND] {', '.join(found_interesting)}")
                detected_names.update(new_cookies)

            if "sessionid" in cookie_names:
                print(f"\n[SUCCESS] Session ID detected! (Attempt {i+1})")
                logged_in = True
                await asyncio.sleep(2) # Let it settle
                break
            
            if i % 10 == 0 and i > 0:
                print(f"  ...still waiting (Attempt {i}/180)")
                
            await asyncio.sleep(1)
        
        if not logged_in:
            print("\n[TIMEOUT] Session ID not detected automatically.")
            print("If you ARE logged in, press ENTER to capture anyway.")
            print("If you are stuck, check the browser for Captchas.")
            # Non-blocking input is hard in pure asyncio without extra libs
            # but since we are at the end, we can just use input()
            input(">>> Press ENTER to capture current cookies and save...")
        
        cookies = await context.cookies()
        
        cookie_names = [c.get("name", "").lower() for c in cookies]
        critical = ["sessionid", "sid_tt"]
        missing = [c for c in critical if c not in cookie_names]

        if missing:
            print(f"\n[WARNING] Missing critical cookies: {', '.join(missing)}")
            print("The upload WILL likely fail. Please ensure you are logged in correctly.")
        else:
            print("\n[SUCCESS] All critical authentication cookies captured.")

        # Save as JSON
        with open("tiktok_cookies.json", "w", encoding="utf-8") as f:
            json.dump(cookies, f, indent=2)
            
        print("\nSUCCESS! Saved to tiktok_cookies.json")
        
        # Also auto-convert to Netscape for tiktok-uploader
        try:
            from src.api.tiktok import _json_to_netscape
            if _json_to_netscape("tiktok_cookies.json", "tiktok_cookies.txt"):
                print("SUCCESS! Also converted and saved to tiktok_cookies.txt")
        except Exception as e:
            print(f"  [Note] Auto-conversion to .txt failed: {e}")
            print("  You may need to run bulk_tiktok_poster.py to trigger conversion.")
        
        print("\n--- DONE ---")
        print("You can now close the browser and run your upload scripts.")
        await browser.close()

if __name__ == "__main__":
    try:
        asyncio.run(capture_cookies())
    except KeyboardInterrupt:
        print("\nStopped by user.")
