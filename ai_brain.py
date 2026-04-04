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

def validate_viral_package(data):
    required_keys = ["title", "description", "segments", "tags"]
    if not all(key in data for key in required_keys):
        return False
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        return False
    segment_keys = ["start", "end", "text", "voiceover", "text_effect", "position", "highlight_word"]
    for s in data["segments"]:
        if not all(key in s for key in segment_keys):
            return False
    return True

def get_new_topic(category):
    print(f"Generating dynamic topic for category: {category}...")
    
    try:
        past_videos = supabase.table("videos").select("topic").order("created_at", desc=True).limit(30).execute()
        used_topics = [v['topic'] for v in past_videos.data]
    except Exception as e:
        print(f"Warning: Could not fetch past topics: {e}")
        used_topics = []

    if category == "gaming":
        theme = "Blox Fruits / Roblox secrets, mechanics, lore, and meta."
        examples = """
        - 3 secret Blox Fruits mechanics the game never actually teaches you...
        - The exact mathematical probability of rolling a Kitsune fruit...
        - The hidden lore behind the Third Sea that 99% of players completely missed...
        - Why the Buddha fruit is statistically the most broken item in Roblox history...
        - The actual reason why max bounty players use this specific fighting style...
        """
    else:
        theme = "Mind-blowing science, history, mystery, and fresh facts."
        examples = """
        - The physics behind why airplanes stay in the air during turbulence...
        - The biological reason why some people are naturally morning larks...
        - How the deep sea creatures survive under extreme atmospheric pressure...
        - The history of how the first computer programming language was created...
        - Why the human eye can distinguish more shades of green than any other color...
        """
    
    prompt = f"""
    Generate ONE unique, high-retention video topic for the category: {category}.
    Theme: {theme}
    
    CRITICAL: The topic MUST sound exactly like these examples in tone and structure:
    {examples}
    
    Rules:
    - Target: Filipino / Southeast Asian audience (but script in English).
    - Style: Hooky, mysterious, or authoritative.
    - Exclude these recently used topics: {used_topics}
    
    Return ONLY the topic string. No punctuation at the end except an ellipsis (...).
    """
    
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text.strip().replace('"', '')
    except Exception as e:
        print(f"Error generating topic: {e}. Falling back to default.")
        return "The secret probability of rolling a Kitsune fruit..." if category == "gaming" else "The physics of airplane turbulence..."

def generate_script(topic):
    prompt = f"""
    You are a world-class YouTube Shorts creator. 
    Your style is fast-paced, high-energy, and uses "Curiosity Gaps" to force follows.
    
    STRICT RULES:
    1. NO EMOJIS anywhere.
    2. Caption 'text' MUST be 1-3 high-impact words MAX. Never a full sentence.
    3. 'voiceover' is the full spoken text.
    4. 5-7 segments total.
    5. Segment 0 (The Hook) MUST end by second 3.0.
    6. Segment 1 MUST contain a mid-video tease (e.g., "stay till the end to see why this changes everything").
    7. The last segment MUST be a curiosity-gap CTA + engagement driver (LIKE/COMMENT/FOLLOW).
    8. 'position': "top" (hooks/questions), "center" (facts), "bottom" (CTAs).
    9. 'highlight_word': The single most important word in the caption.
    10. 'tags': Exactly 15 topic-specific SEO tags.
    11. 'description': 200+ words SEO-optimized.

    USER TOPIC: "{topic}"

    Return JSON:
    {{
        "title": "Short Title",
        "description": "200-word SEO description",
        "tags": ["tag1", "tag2", "tag3"],
        "segments": [
            {{
                "start": 0, 
                "end": 2.5, 
                "text": "SECRET FOUND", 
                "voiceover": "Did you know that there's a hidden mechanic in Blox Fruits that everyone misses?", 
                "text_effect": "pop",
                "position": "top",
                "highlight_word": "SECRET"
            }}
        ]
    }}
    """
    
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-2.0-flash', 
                contents=prompt, 
                config=types.GenerateContentConfig(temperature=0.8, response_mime_type="application/json")
            )
            viral_package = json.loads(response.text.strip())
            
            if not validate_viral_package(viral_package):
                print(f"Validation failed for attempt {attempt + 1}. Retrying...")
                continue
                
            full_script = " ".join([s['voiceover'] for s in viral_package['segments']])
            supabase.table("videos").insert({"topic": topic, "title": viral_package['title'], "script": full_script}).execute()
            return viral_package
        except Exception as e:
            print(f"Brain Error on attempt {attempt + 1}: {e}")
            time.sleep(75)
            
    return None

def get_search_query(topic):
    prompt = f"Topic: '{topic}'. Return ONLY 'Parkour' for science/history, or a 2-word cinematic query for tech/space."
    try:
        response = client.models.generate_content(model='gemini-2.0-flash', contents=prompt)
        return response.text.strip().replace(".", "").replace('"', '')
    except Exception:
        return "Parkour"