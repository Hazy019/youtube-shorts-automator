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
        
        input("\n--- PRESS ENTER HERE ONCE LOGGED IN SUCCESSFULLY ---")
        
        cookies = await context.cookies()
        

        with open("tiktok_cookies.json", "w") as f:
            json.dump(cookies, f)
            
        print("\nSUCCESS! Saved to tiktok_cookies.json")
        print("\n--- FOR GITHUB ACTIONS ---")
        print("Copy the entire content of tiktok_cookies.json and paste it into a GitHub Secret named: TIKTOK_COOKIES_JSON")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_cookies())
