import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/yt-analytics.readonly'
]

def force_refresh_tokens():
    print("="*40)
    print("GOOGLE TOKEN REFRESH PROTOCOL (V5)")
    print("="*40)
    
    if not os.path.exists('client_secrets.json'):
        print("ERROR: client_secrets.json missing. Download it from Google Cloud Console first!")
        return


    for token_file in ['token_drive.json', 'token_youtube.json']:
        if os.path.exists(token_file):
            try:
                os.remove(token_file)
                print(f"Deleted old {token_file}")
            except:
                pass

    print("\nOpening browser for authentication...")
    print("Select your Google account and verify permissions for Drive + YouTube.")
    
    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
    creds = flow.run_local_server(port=0)


    with open('token_drive.json', 'w') as f:
        f.write(creds.to_json())
    with open('token_youtube.json', 'w') as f:
        f.write(creds.to_json())

    print("\n" + "="*40)
    print("SUCCESS! AUTHENTICATION COMPLETE.")
    print("="*40)
    print("1. token_drive.json and token_youtube.json generated.")
    print("2. Copy their contents to GitHub Secrets (DRIVE_TOKEN_JSON & YOUTUBE_TOKEN_JSON).")
    print("3. Ensure your .env GEMINI_API_KEY is also updated.")
    print("="*40)

if __name__ == "__main__":
    force_refresh_tokens()
