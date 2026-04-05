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

def clean_json_response(text):
    """Mandatory: Strips markdown fences from Gemini JSON output."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def validate_full_package(data):
    """Ensures all required v4 keys are present in the merged response."""
    required_keys = ["topic", "search_keyword", "title", "description", "segments", "tags"]
    if not all(key in data for key in required_keys):
        print(f"Validation Error: Missing keys. Found: {list(data.keys())}")
        return False
        
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        print(f"Validation Error: Invalid segments. Count: {len(data['segments']) if isinstance(data['segments'], list) else 'Not a list'}")
        return False
        
    segment_keys = ["start", "end", "text", "voiceover", "text_effect", "position", "highlight_word"]
    for s in data["segments"]:
        if not all(key in s for key in segment_keys):
            print(f"Validation Error: Segment missing keys: {list(s.keys())}")
            return False
    return True

def fetch_analytics_feedback():
    """V4: Fetches high/low performing video scripts to guide Gemini."""
    try:
        winners = supabase.table("videos").select("topic, script").gte("avg_view_pct", 75).order("avg_view_pct", desc=True).limit(3).execute()
        losers = supabase.table("videos").select("topic, script").lt("avg_view_pct", 40).order("avg_view_pct", desc=False).limit(3).execute()
        
        feedback = f"\n\nHIGH RETENTION EXAMPLES (Emulate this pacing):\n{winners.data}" if winners.data else ""
        feedback += f"\n\nLOW RETENTION EXAMPLES (Avoid these structures):\n{losers.data}" if losers.data else ""
        return feedback
    except Exception as e:
        print(f"Warning: Analytics feedback loop bypassed: {e}")
        return ""

def fetch_used_topics_from_supabase(category):
    """V4: Fetches last 30 topics for exclusion."""

    used_topics = []
    try:
        past_videos = supabase.table("videos").select("topic").eq("category", category).limit(20).execute()
        used_topics = [v['topic'] for v in past_videos.data]
    except Exception as e:
        print(f"Supabase Note: Skipping topic filter (Table/Column missing: {e})")
    return used_topics

def generate_full_package(category):
    """Merged V4 logic: One Gemini call generates EVERYTHING."""
    used_topics = fetch_used_topics_from_supabase(category)
    feedback = fetch_analytics_feedback()

    if category == "gaming":
        theme = "Blox Fruits / Roblox secrets, mechanics, lore, and meta."
        examples = """
        - 3 secret Blox Fruits mechanics the game never actually teaches you...
        - The exact mathematical probability of rolling a Kitsune fruit in Blox Fruits...
        - The hidden lore behind the Third Sea that 99% of players missed...
        - Why Awakened Dough is secretly the best fruit for PvP in 2025...
        - The actual reason why max bounty players use this specific fighting style...
        """
        keyword_hint = "Return 'Parkour' for all gaming assets. NEVER return Minecraft."
    else:
        theme = "Mind-blowing science, history, mystery, and fresh facts."
        examples = """
        - The physics behind why airplanes stay in the air during turbulence...
        - The biological reason why some people are naturally morning larks...
        - Why the human eye can distinguish more shades of green than any other color...
        """
        keyword_hint = "Return 'Parkour' or 'Space' or a 2-word Pexels query."

    prompt = f"""
    You are a world-class YouTube Shorts creator for an INTERNATIONAL / US-FIRST audience.
    Generate a full production package for the category: {category}.
    Theme: {theme}
    
    {feedback}

    STRICT RULES:
    1. NO EMOJIS anywhere in the JSON.
    2. 'text' (caption) = 1-3 WORDS MAX. Never a full sentence.
    3. 'voiceover' is the full spoken text. No word count limit — use timing to control pacing.
    4. 5-7 segments total. Segment 0 ends by 3.0s.
    5. 'topic' must be unique, high-retention, and end in '...'.
    6. Exclude these used topics: {used_topics}
    
    You MUST return a SINGLE JSON Object with exactly this structure:
    {{
      "topic": "String ending in ...",
      "search_keyword": "String for b-roll",
      "title": "String",
      "description": "String",
      "tags": ["tag1", "tag2", "tag3"],
      "segments": [
        {{
          "start": 0.0,
          "end": 3.0,
          "text": "Caption text",
          "voiceover": "Full spoken script...",
          "text_effect": "glow",
          "position": "center",
          "highlight_word": "word"
        }}
      ]
    }}
    """


    working_model = "gemini-3.1-flash-lite-preview"
    fallback_model = "gemini-3.1-flash-lite-preview"
    
    time.sleep(3)
    
    for attempt in range(3):
        try:
            active_model = working_model if attempt < 2 else fallback_model
            print(f"Full Package Gen (Attempt {attempt+1}): Using ({active_model})...")
            
            response = client.models.generate_content(
                model=active_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    response_mime_type="application/json"
                )
            )
            
            clean = clean_json_response(response.text)
            package = json.loads(clean)

            if not validate_full_package(package):
                print("JSON Validation failed. Retrying...")
                continue


            full_audio = " ".join([s['voiceover'] for s in package['segments']])
            try:
                supabase.table("videos").insert({
                    "topic": package['topic'], 
                    "title": package['title'], 
                    "script": full_audio,
                    "category": category
                }).execute()
            except Exception as e:
                print(f"Supabase History Insert skipped: {e}")

                try:
                    supabase.table("videos").insert({
                        "topic": package['topic'], 
                        "title": package['title'], 
                        "script": full_audio
                    }).execute()
                except Exception as inner_e:
                    pass

            return package


        except Exception as e:
            err = str(e).upper()
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 65 + (attempt * 30)
                print(f"Rate limit hit. Waiting {wait}s (attempt {attempt+1}/3)...")
                time.sleep(wait)
            else:
                print(f"Brain Error: {e}")
                time.sleep(15)

    return None
