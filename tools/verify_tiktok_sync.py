import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force utf-8 encoding for stdout to prevent emoji printing errors on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import time
from dotenv import load_dotenv
from supabase import create_client, Client
from src.api.tiktok import _prepare_cookies, _validate_netscape, _cleanup, get_playwright_cookies

load_dotenv()

def get_db() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    return create_client(url, key)

def scan_and_sync():
    print("="*40)
    print("TIKTOK LIVE PROFILE SCANNER & SYNC")
    print("="*40)
    
    cookies_path = _prepare_cookies()
    
    if not cookies_path or not _validate_netscape(cookies_path):
        print("FATAL: Invalid or missing TikTok cookies.")
        return

    playwright_cookies = get_playwright_cookies()
    if not playwright_cookies:
        print("FATAL: Could not parse session cookies for Playwright.")
        return

    from playwright.sync_api import sync_playwright
    from playwright._impl._errors import TargetClosedError

    try:
        with sync_playwright() as p:
            print("Launching browser...")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
            
            # Inject authenticated session cookies
            context.add_cookies(playwright_cookies)
            print(f"✓ Injected {len(playwright_cookies)} TikTok session cookies into browser context.")
            
            page = context.new_page()
            
            # Determine target URL: Check TIKTOK_USERNAME or default to Home to verify login
            custom_username = os.getenv("TIKTOK_USERNAME", "").strip().lstrip("@")
            if custom_username:
                target_url = f"https://www.tiktok.com/@{custom_username}"
                print(f"Navigating to profile: {target_url}...")
            else:
                target_url = "https://www.tiktok.com/"
                print("Navigating to TikTok (Home/Profile verification)...")
                
            page.goto(target_url, wait_until="domcontentloaded")
            time.sleep(5) # Wait for hydration & dynamic elements
            
            # Check login indicator
            is_logged_in = False
            login_btn = page.query_selector('button:has-text("Log in"), a:has-text("Log in")')
            avatar_btn = page.query_selector('div[data-e2e="profile-icon"], img[class*="avatar"], div[class*="avatar"]')
            
            if avatar_btn and not login_btn:
                print("✓ Authentication SUCCESS: Logged-in session confirmed!")
                is_logged_in = True
            elif not login_btn:
                print("✓ Session Active (No login button displayed).")
                is_logged_in = True
            else:
                print("⚠️  Warning: Login button detected. Session cookies may need refresh or TikTok requested a captcha.")

            # Scrape video titles (captions)
            print("Extracting live video titles...")
            video_elements = page.query_selector_all('div[data-e2e="user-post-item-desc"]')
            live_titles = [el.inner_text().strip() for el in video_elements if el.inner_text()]
            
            print(f"Found {len(live_titles)} video(s) on view.")
            
            if live_titles:
                for idx, t in enumerate(live_titles[:5]):
                    print(f"  [{idx+1}] {t[:60]}...")
            
            # Cross-reference with Supabase if in profile view
            if custom_username and live_titles:
                try:
                    db = get_db()
                    resp = db.table("videos").select("id, title, topic").eq("tiktok_status", "PENDING").execute()
                    pending = resp.data or []
                    
                    matches = 0
                    for item in pending:
                        title = item.get("title", "")
                        if any(title.lower() in live.lower() for live in live_titles):
                            print(f"  ✓ MATCH FOUND: {title} (ID: {item['id']})")
                            db.table("videos").update({"tiktok_status": "SUCCESS"}).eq("id", item['id']).execute()
                            matches += 1
                    
                    if matches > 0:
                        print(f"\nScan complete. Synchronized {matches} items to SUCCESS.")
                except Exception as e:
                    print(f"Supabase sync notice: {e}")

            time.sleep(2)
            browser.close()

    except TargetClosedError:
        print("\nNotice: Browser was closed by user.")
    except Exception as e:
        print(f"\nVerification encountered an issue: {e}")
    finally:
        _cleanup()

if __name__ == "__main__":
    scan_and_sync()
