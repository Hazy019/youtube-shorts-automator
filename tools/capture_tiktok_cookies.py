import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import json
import asyncio
from playwright.async_api import async_playwright

async def capture_cookies():
    print("\n--- TIKTOK COOKIE CAPTURER ---")
    print("1. A browser will open for TikTok login.")
    print("2. Log in manually (QR Code is easiest).")
    print("3. Once logged in and redirected to home, press ENTER in this terminal.")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        await page.goto("https://www.tiktok.com/login")
        
        print("\nACTION: Please log in to TikTok in the browser window.")
        print("Waiting for session to establish (Automatic detection enabled)...")

        logged_in = False
        for i in range(180):
            cookies = await context.cookies()
            cookie_names = [c.get("name", "").lower() for c in cookies]
            
            if "sessionid" in cookie_names:
                print(f"\n[DETECTED] Session ID acquired! (Attempt {i+1})")
                logged_in = True
                await asyncio.sleep(3) # Let other cookies settle
                break
            
            if i % 10 == 0 and i > 0:
                print(f"  ...still waiting for sessionid (Attempt {i})")
                
            await asyncio.sleep(1)
        
        if not logged_in:
            print("\n[TIMEOUT] Could not detect sessionid automatically.")
            input("--- Please log in MANUALLY, then press ENTER here to save ---")
        
        cookies = await context.cookies()
        
        cookie_names = [c.get("name", "").lower() for c in cookies]
        critical = ["sessionid", "sid_tt", "tt_csrf_token"]
        missing = [c for c in critical if c not in cookie_names]

        if missing:
            print(f"\n[WARNING] Missing critical cookies: {', '.join(missing)}")
            print("The upload might fail. TRy logging out and back in, then capture again.")
        else:
            print("\n[SUCCESS] All critical authentication cookies captured.")

        with open("tiktok_cookies.json", "w") as f:
            json.dump(cookies, f)
            
        print("\nSUCCESS! Saved to tiktok_cookies.json")
        print("Note: bulk_tiktok_poster.py will automatically convert this to tiktok_cookies.txt for uploading.")
        print("\n--- FOR GITHUB ACTIONS ---")
        print("Copy the entire content of tiktok_cookies.json and paste it into a GitHub Secret named: TIKTOK_COOKIES_JSON")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_cookies())
