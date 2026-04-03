import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# Scopes for both Drive and YouTube
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/youtube.upload'
]

def force_refresh_tokens():
    print("Initiating Google Token Refresh Protocol...")
    
    # Delete old tokens to force a fresh login
    for token_file in ['token_drive.json', 'token_youtube.json']:
        if os.path.exists(token_file):
            os.remove(token_file)
            print(f"Deleted old {token_file}")

    print("\nOpening browser for authentication. Please log in to your Google Account...")
    flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
    creds = flow.run_local_server(port=0)

    # Save the new tokens
    with open('token_drive.json', 'w') as f:
        f.write(creds.to_json())
    with open('token_youtube.json', 'w') as f:
        f.write(creds.to_json())

    print("\nSUCCESS! New tokens generated.")
    print("1. Open token_drive.json and token_youtube.json")
    print("2. Copy their contents")
    print("3. Paste them into your GitHub Secrets (DRIVE_TOKEN_JSON & YOUTUBE_TOKEN_JSON)")

if __name__ == "__main__":
    force_refresh_tokens()