import sys
import os

# Force console output to UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.utils.discord import redact_secrets
from run_factory import validate_render_url

def test_redaction():
    print("Testing Secret Redaction...")
    
    # Real-looking fake secrets
    gemini_key = "AIzaSyD-7Xj2_mock_key_1234567890abcdefgh"
    aws_key = "AKIA1234567890ABCDEF"
    openai_key = "sk-antigravity-mock-secret-key-donotleakthisone"
    webhook = "https://discord.com/api/webhooks/123456789/mock-token-abc-123"
    
    raw_traceback = f"""
    Internal Error at line 42:
    API_KEY = '{gemini_key}'
    CLIENT = Client(key='{openai_key}')
    AWS_ID = '{aws_key}'
    CALLBACK = '{webhook}'
    Something went wrong!
    """
    
    redacted = redact_secrets(raw_traceback)
    
    print("\n[Original Traceback (excerpt)]:")
    print(raw_traceback.strip()[:100] + "...")
    
    print("\n[Redacted Traceback]:")
    print(redacted)
    
    # Assertions
    if gemini_key in redacted or aws_key in redacted or openai_key in redacted or webhook in redacted:
        print("\n❌ FAIL: Secrets were NOT fully redacted!")
    else:
        print("\n✅ PASS: All secrets were replaced with [REDACTED_SECRET].")

def test_url_validation():
    print("\nTesting Render URL Validation...")
    
    safe_urls = [
        "https://s3.us-east-1.amazonaws.com/hazy-renders/video.mp4",
        "https://remotion-render.s3.us-east-1.amazonaws.com/final.mp4",
    ]
    
    unsafe_urls = [
        "https://malicious-site.com/exploit.mp4",
        "https://localhost:8080/token",
        "https://evil-bucket.s3.eu-west-1.amazonaws.com/leak", # Wrong region or untrusted
    ]
    
    for url in safe_urls:
        if validate_render_url(url):
            print(f"✅ PASS: Correctly allowed {url}")
        else:
            print(f"❌ FAIL: Blocked legitimate URL {url}")
            
    for url in unsafe_urls:
        if not validate_render_url(url):
            print(f"✅ PASS: Correctly blocked {url}")
        else:
            print(f"❌ FAIL: COMPROMISE! Allowed unsafe URL {url}")

if __name__ == "__main__":
    test_redaction()
    test_url_validation()
