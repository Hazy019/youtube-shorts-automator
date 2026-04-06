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
        print("Waiting for automatic login detection (or press ENTER to force save)...")

        logged_in = False
        for _ in range(120):
            current_url = page.url
            if "/foryou" in current_url or "/@ " in current_url or "dashboard" in current_url:
                print(f"\n[DETECTED] Login successful! (URL: {current_url})")
                logged_in = True
                await asyncio.sleep(2)
                break
            await asyncio.sleep(1)
        
        if not logged_in:
            input("\n--- PRESS ENTER HERE ONCE LOGGED IN SUCCESSFULLY ---")
        
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
        print("\n--- FOR GITHUB ACTIONS ---")
        print("Copy the entire content of tiktok_cookies.json and paste it into a GitHub Secret named: TIKTOK_COOKIES_JSON")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_cookies())
