import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shutil
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USER_DATA = r"C:\Users\Acer\AppData\Local\Google\Chrome\User Data"
_PROFILE_15 = os.path.join(_USER_DATA, "Profile 15")
_TARGET_PROFILE = os.path.join(_PROJECT_ROOT, ".tiktok_profile")
_TARGET_DEFAULT = os.path.join(_TARGET_PROFILE, "Default")

def sync_chrome_profile():
    print("\n" + "="*60)
    print("      IMPORT SESSION DIRECTLY FROM YOUR REAL CHROME")
    print("="*60)
    print(f"Source Chrome Profile: {_PROFILE_15} ('Kyrell' - @hazy5936)")
    print(f"Target Automation Profile: {_TARGET_PROFILE}\n")

    os.makedirs(_TARGET_DEFAULT, exist_ok=True)

    # Check if Chrome is currently locking the files
    cookies_file = os.path.join(_PROFILE_15, "Network", "Cookies")
    is_locked = False
    if os.path.exists(cookies_file):
        try:
            with open(cookies_file, "r+b") as f:
                pass
        except PermissionError:
            is_locked = True

    if is_locked:
        print("⚠ NOTE: Google Chrome is currently open on your screen.")
        print("  Windows has locked the cookie database while Chrome is running.\n")
        print(">>> Please CLOSE Google Chrome completely for 5 seconds so we can copy your active login...")
        
        while is_locked:
            time.sleep(2)
            try:
                with open(cookies_file, "r+b") as f:
                    is_locked = False
                    print("✓ Chrome closed! Copying active session now...")
            except (PermissionError, FileNotFoundError):
                print("  ...waiting for Chrome to close...")

    # Copy Local State (encryption keys)
    src_local_state = os.path.join(_USER_DATA, "Local State")
    dst_local_state = os.path.join(_TARGET_PROFILE, "Local State")
    if os.path.exists(src_local_state):
        shutil.copyfile(src_local_state, dst_local_state)
        print("[OK] Copied Local State")

    # Copy all auth folders
    for item in ["Network", "Local Storage", "IndexedDB", "Session Storage"]:
        src_item = os.path.join(_PROFILE_15, item)
        dst_item = os.path.join(_TARGET_DEFAULT, item)
        if os.path.exists(src_item):
            try:
                if os.path.exists(dst_item):
                    shutil.rmtree(dst_item, ignore_errors=True)
                shutil.copytree(src_item, dst_item, dirs_exist_ok=True)
                print(f"[OK] Copied {item}")
            except Exception as e:
                print(f"[WARN] {item}: {e}")

    print("\n" + "="*60)
    print("🎉 SUCCESS! YOUR REAL CHROME SESSION WAS COPIED DIRECTLY!")
    print("="*60)
    print("Your automation profile now has your exact @hazy5936 login session.")
    print("You can re-open your regular Google Chrome now.")
    print("You can now run 'bulk_tiktok_poster.py' without logging in!")

if __name__ == "__main__":
    sync_chrome_profile()
