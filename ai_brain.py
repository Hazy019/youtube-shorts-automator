import os
import random
import json
import time
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

def get_new_topic(category):
    blox_fruit_topics = [
        "3 secret Blox Fruits mechanics the game never actually teaches you...",
        "The exact mathematical probability of rolling a Kitsune fruit...",
        "The hidden lore behind the Third Sea that 99% of players completely missed...",
        "Why the Buddha fruit is statistically the most broken item in Roblox history...",
        "The actual reason why max bounty players use this specific fighting style..."
    ]

    general_topics = [
        "The physics behind why airplanes stay in the air during turbulence...",
        "The biological reason why some people are naturally morning larks...",
        "How the deep sea creatures survive under extreme atmospheric pressure...",
        "The history of how the first computer programming language was created...",
        "Why the human eye can distinguish more shades of green than any other color..."
    ]

    if category == "gaming":
        return random.choice(blox_fruit_topics)
    else:
        return random.choice(general_topics)

def generate_script(topic):
    prompt = f"""
    SYSTEM INSTRUCTION:
    You are a professional, authoritative, and educational YouTube Shorts creator. 
    Your tone is expert, objective, and high-energy. 
    
    STRICT CONTENT GUARDRAILS:
    - NEVER generate content related to politics, religion, or sensitive social issues.
    - ABSOLUTELY NO EMOJIS IN THE TEXT OR JSON.

    USER TOPIC: "{topic}"

    STRUCTURE:
    Create a 30 to 60-second script.
    - segments: An array of 4 to 6 objects.
    - Each object must have: "start", "end", "text" (max 5 words), "voiceover", and "text_effect".
    - TEXT EFFECTS ALLOWED: "pop", "glitch", "typewriter".
    - CRITICAL RULE: The very last segment MUST be a call to action telling the viewer to subscribe.

    Return ONLY a valid JSON object matching this exact format:
    {{
        "title": "Professional title under 50 characters",
        "description": "2-sentence SEO description with 3 hashtags.",
        "segments": [
            {{"start": 0, "end": 5, "text": "HOOK CAPTION HERE", "voiceover": "Spoken hook text goes here.", "text_effect": "pop"}},
            {{"start": 5, "end": 15, "text": "CRAZY TECH FACT", "voiceover": "Spoken explanation goes here.", "text_effect": "glitch"}},
            {{"start": 15, "end": 20, "text": "SUB FOR MORE INSIGHTS", "voiceover": "Subscribe to Hazy Chanel for more daily facts.", "text_effect": "pop"}}
        ]
    }}
    """

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7, 
                    response_mime_type="application/json" 
                )
            )
            
            viral_package = json.loads(response.text.strip())
            
            try:
                full_script_for_db = " ".join([s['voiceover'] for s in viral_package['segments']])
                supabase.table("videos").insert({
                    "topic": topic, 
                    "title": viral_package['title'],
                    "script": full_script_for_db
                }).execute()
            except Exception:
                pass
                
            return viral_package

        except Exception as e:
            print(f"Brain Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                print("Rate limit/Error hit. Waiting 65 seconds...")
                time.sleep(65)
            else:
                return None

def get_search_query(topic):
    prompt = f"""
    Based on this educational topic: '{topic}', you must choose the background footage. 
    Rule 1: If the topic is about psychology, biology, history, output ONLY the exact word 'Parkour'.
    Rule 2: Only if the topic requires visual proof (like space/technology), return a 2-word Pexels search query (e.g., 'Cinematic Space').
    Output NOTHING ELSE but the 1 or 2 word search query. No punctuation.
    """
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text.strip().replace(".", "").replace('"', '')
    except Exception:
        return "Parkour"