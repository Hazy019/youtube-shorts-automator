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

def get_new_topic():
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

    all_topics = blox_fruit_topics + general_topics
    return random.choice(all_topics)

def generate_script(topic):
    print(f"Asking Gemini to architect a viral package for: {topic}...")
    
    prompt = f"""
    SYSTEM INSTRUCTION:
    You are a professional, authoritative, and educational YouTube Shorts creator. 
    Your tone is expert, objective, and high-energy. 
    
    STRICT CONTENT GUARDRAILS:
    - NEVER generate content related to politics, religion, or sensitive social issues.
    - Focus exclusively on science, technology, gaming, and verifiable facts.

    USER TOPIC: "{topic}"

    Return ONLY a valid JSON object:
    {{
        "title": "Professional title under 50 characters",
        "description": "2-sentence SEO description with 3 hashtags.",
        "script": "The spoken voiceover text only. Write it exactly how a fast-paced expert would speak."
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
                supabase.table("videos").insert({
                    "topic": topic, 
                    "title": viral_package['title'],
                    "script": viral_package['script']
                }).execute()
            except Exception:
                pass
                
            return viral_package

        except Exception as e:
            print(f"Brain Error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                print("Rate limit hit. Waiting 65 seconds...")
                time.sleep(65)
            else:
                return None

def get_search_query(topic):
    print("Asking Gemini for professional visual direction...")
    
    prompt = f"""
    Based on this educational topic: '{topic}', act as a professional video editor. 
    1. Choose a high-quality visual keyword (e.g., 'Space', 'Technology', 'Nature').
    2. Add a professional style modifier (e.g., 'Cinematic', 'Minimalist', 'Macro').
    3. If fast-paced background gameplay fits the topic best, output ONLY the word 'Parkour'.
    
    Otherwise, return ONLY the 2-word combination (e.g., 'Cinematic Space').
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', 
            contents=prompt
        )
        return response.text.strip().replace(".", "").replace('"', '')
    except Exception as e:
        print(f"Direction failed: {e}. Using 'Abstract' as fallback.")
        return "Abstract"