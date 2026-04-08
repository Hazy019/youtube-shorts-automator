import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import requests
from dotenv import load_dotenv


load_dotenv()
api_key = os.getenv("ELEVENLABS_API_KEY")

def fetch_my_voices():
    print(" Asking ElevenLabs for your authorized voices...\n")
    
    url = "https://api.elevenlabs.io/v1/voices"
    headers = {"xi-api-key": api_key}
    
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        voices = response.json()["voices"]
        print(" SUCCESS! Here are the Voice IDs you can use:\n")
        print("-" * 40)
        

        for voice in voices:
            if voice['category'] == 'premade':
                print(f" Name: {voice['name']}")
                print(f" ID:   {voice['voice_id']}")
                print("-" * 40)
    else:
        print(f" Error: {response.text}")

if __name__ == "__main__":
    fetch_my_voices()
