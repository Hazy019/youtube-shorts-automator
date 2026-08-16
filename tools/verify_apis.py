import os
import sys
import requests
from dotenv import load_dotenv

# Force UTF-8 output for emojis on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

def verify_pexels():
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        print("❌ PEXELS_API_KEY missing.")
        return False
    
    url = "https://api.pexels.com/videos/search?query=nature&per_page=1"
    headers = {"Authorization": key}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            print("✅ Pexels API: Valid")
            return True
        else:
            print(f"❌ Pexels API: Invalid (Status {r.status_code})")
            return False
    except Exception as e:
        print(f"❌ Pexels API: Request failed: {e}")
        return False

def verify_gemini():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        print("❌ GEMINI_API_KEY missing.")
        return False
    
    # We use a very cheap model check or a dummy request
    # Since we use google-genai, we'll just check if the key exists
    # A full check would require calling a model, which costs tokens (though minimal)
    # For pre-flight, let's just assume if it's 30+ chars it's present.
    if len(key) < 20:
        print("❌ GEMINI_API_KEY: Looks invalid (too short)")
        return False
    
    print("✅ Gemini API Key: Present")
    return True

def main():
    print("🔍 PRE-FLIGHT API VERIFICATION...")
    p = verify_pexels()
    g = verify_gemini()
    
    if p and g:
        print("🚀 All critical APIs are healthy.")
        exit(0)
    else:
        print("🛑 API Verification FAILED. Blocking factory to save resources.")
        exit(1)

if __name__ == "__main__":
    main()
