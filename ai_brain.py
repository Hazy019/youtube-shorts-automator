import os
import json
import time
from google import genai
from google.genai import types
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

PRIMARY_MODEL  = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-2.0-flash-lite"

def clean_json_response(text):
    """Strips markdown fences. MUST run before every json.loads()."""
    text = text.strip()
    for prefix in ("```json", "```"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def validate_full_package(data):
    required = ["topic", "search_keyword", "title", "description", "segments", "tags"]
    if not all(k in data for k in required):
        print(f"Validation: Missing keys — found {list(data.keys())}")
        return False
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        print(f"Validation: Need ≥5 segments, got {len(data.get('segments', []))}")
        return False
    seg_keys = ["start", "end", "text", "voiceover", "text_effect", "position", "highlight_word"]
    valid_effects = ("pop", "glitch", "typewriter")
    for i, s in enumerate(data["segments"]):
        if not all(k in s for k in seg_keys):
            print(f"Validation: Segment {i} missing keys")
            return False
        # Auto-correct invalid text_effect so render never fails
        if s.get("text_effect") not in valid_effects:
            s["text_effect"] = "pop"
        # Enforce hook timing rule
        if i == 0 and s.get("end", 99) > 3.5:
            print(f"Validation: Hook segment ends at {s['end']}s — must end ≤3.5s. Retrying.")
            return False
    return True

def fetch_analytics_feedback():
    try:
        winners = supabase.table("videos").select("topic, script") \
            .gte("avg_view_pct", 75).order("avg_view_pct", desc=True).limit(3).execute()
        losers = supabase.table("videos").select("topic, script") \
            .lt("avg_view_pct", 40).order("avg_view_pct", desc=False).limit(3).execute()
        feedback = ""
        if winners.data:
            feedback += f"\nHIGH RETENTION SCRIPTS — emulate their hook timing and pacing:\n{winners.data}"
        if losers.data:
            feedback += f"\nLOW RETENTION SCRIPTS — avoid these patterns:\n{losers.data}"
        return feedback
    except Exception as e:
        print(f"Analytics feedback skipped: {e}")
        return ""

def fetch_used_topics(category):
    try:
        rows = supabase.table("videos").select("topic") \
            .order("created_at", desc=True).limit(25).execute()
        return [v["topic"] for v in rows.data]
    except Exception as e:
        print(f"Topic fetch skipped: {e}")
        return []

def generate_full_package(category, local_excludes=None):
    """
    ONE Gemini call → topic + keyword + full script + tags + description.
    2 calls/day max. Free tier = 1500 RPD. Will never hit quota.
    """
    used_topics = fetch_used_topics(category)
    if local_excludes:
        used_topics.extend(local_excludes)
    feedback = fetch_analytics_feedback()

    used_topics = fetch_used_topics(category)
    if local_excludes:
        used_topics.extend(local_excludes)
    feedback = fetch_analytics_feedback()

    if category == "gaming":
        theme = "Fascinating video game lore, hidden easter eggs, speedrunning records, mind-blowing mechanics, and developer secrets across all major titles."
        examples = """
        - The impossible Super Mario 64 glitch that took speedrunners 20 years to solve...
        - Why the developers of GTA V hid an alien frozen under the ice...
        - The terrifying lore reason behind why Minecraft's Endermen hate eye contact...
        - How one player broke Elden Ring's entire in-game economy in a single session...
        - The hidden developer message encoded inside the original Doom soundtrack...
        - The exact reason why the Minecraft world border exists at exactly 30 million blocks...
        """
        keyword_hint = 'Return ONLY "Parkour" for ALL gaming topics. Never return anything else.'
        sfx_style   = "energetic, punchy — use glitch and pop effects aggressively"
        pace_guide  = "Fast cuts. Short, punchy sentences. Hook must create disbelief."
    else:
        theme = "Mind-blowing science, untold history, psychology tricks, and counterintuitive facts that make you say 'wait, what?'"
        examples = """
        - The physics reason why you physically cannot fall straight down in a vacuum...
        - The biological mechanism that makes sleep deprivation feel exactly like being drunk...
        - Why the Mona Lisa has no eyebrows and what that reveals about the Renaissance...
        - The counterintuitive psychology behind why winning the lottery destroys happiness...
        - How ancient Romans accidentally discovered the formula for concrete stronger than modern steel...
        """
        keyword_hint = 'Return "Parkour" for biology/history/psychology. For space/nature return a 2-word Pexels query.'
        sfx_style   = "cinematic, atmospheric — use riser and whoosh effects for mystery"
        pace_guide  = "Build tension slowly, then drop the fact. Let the voiceover breathe."

    # THE MASTER PROMPT FOR GEMINI
    prompt = f"""
You are simultaneously a world-class YouTube Shorts scriptwriter AND a professional video editor.
Your job is to generate a full production package — the script AND the edit timing in one pass.
Target audience: INTERNATIONAL / US-FIRST. Platform: YouTube Shorts + TikTok.

CATEGORY: {category}
THEME: {theme}
EDITING STYLE: {sfx_style}
PACING GUIDE: {pace_guide}
{feedback}

══════════════════════════════════════════════════════════════
ABSOLUTE RULES — violating ANY of these = invalid response:
══════════════════════════════════════════════════════════════

[CONTENT RULES]
R1.  NO EMOJIS anywhere in the JSON output.
R2.  'topic' must be unique, intriguing, end in '...'.
R3.  'topic' MUST NOT be semantically similar to this forbidden list: {used_topics}
     Example: if 'sleep deprivation' is forbidden, you CANNOT generate 'why we feel tired'.
R4.  'description' = 200+ words, US-market SEO, hook sentence first, 3+ hashtags.
R5.  'tags' = exactly 15 topic-specific US-market SEO strings (no generic words like "shorts").

[SCRIPTING RULES]
R6.  'text' (on-screen caption) = 1–3 WORDS MAXIMUM. NEVER a full sentence.
R7.  'voiceover' = the full spoken script for that segment. No word limit.
R8.  Caption and voiceover MUST CONVEY DIFFERENT THINGS.
     Caption = the PUNCHLINE or LABEL. Voiceover = the EXPLANATION.
     WRONG: text="THE SUN IS HOT", voiceover="The sun is very hot."
     RIGHT: text="5,500°C", voiceover="The surface of the sun is hotter than any human-made material."
R9.  'highlight_word' = single most shocking or important word in the caption. Renders WHITE.

[EDITING RULES — think like a professional editor]
R10. Total 5–7 segments. Each segment = one cut in the edit.
R11. SEGMENT 0 (The Hook): end ≤ 3.0s. Must create instant disbelief or a question.
     text_effect MUST be "pop". position MUST be "top".
     Voiceover: max 1 short, punchy sentence. No full explanation yet.
R12. SEGMENT 1 (The Tease): immediately follows the hook.
     Voiceover MUST contain a retention tease: "stay till the end — what I found will change everything."
     text_effect: "typewriter". position: "center".
R13. SEGMENTS 2 to N-2 (The Body): deliver the actual facts.
     Vary text_effect: use "glitch" for shocking facts, "pop" for reveals, "typewriter" for slow builds.
     Position: "center" for facts, "top" for rhetorical questions.
     Each body segment should be 4–8 seconds long for proper pacing.
R14. LAST SEGMENT (The CTA): curiosity-gap call-to-action + engagement driver.
     text_effect: "pop". position: "bottom".
     Voiceover: "SMASH LIKE if you didn't know this — Part 2 drops tomorrow."
     or: "COMMENT what shocked you most. Follow so you don't miss Part 2."
R15. Timing must be realistic for speech. A 40-word voiceover needs ~10 seconds.
     Use this formula: seconds = word_count / 2.5 (average 150wpm). Round up.
R16. 'position' values: "top" = hook questions, "center" = main facts, "bottom" = CTAs only.
R17. 'search_keyword': {keyword_hint}

══════════════════════════════════════════════════════════════
TIMING EXAMPLE (study this structure):
══════════════════════════════════════════════════════════════
Segment 0 (Hook):    start=0.0,  end=2.5  → 3-5 word hook, "pop", "top"
Segment 1 (Tease):   start=2.5,  end=8.0  → retention tease, "typewriter", "center"
Segment 2 (Body 1):  start=8.0,  end=16.0 → first fact, "glitch" or "pop", "center"
Segment 3 (Body 2):  start=16.0, end=24.0 → second fact, "pop", "center"
Segment 4 (Body 3):  start=24.0, end=34.0 → biggest reveal, "glitch", "top"
Segment 5 (CTA):     start=34.0, end=42.0 → engagement CTA, "pop", "bottom"

Good examples for {category}:
{examples}

══════════════════════════════════════════════════════════════
OUTPUT — return ONLY this JSON, no markdown, no preamble:
══════════════════════════════════════════════════════════════
{{
  "topic": "Unique topic string ending in ...",
  "search_keyword": "Parkour",
  "title": "SEO title under 50 chars",
  "description": "200+ word SEO description with 3+ hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10","tag11","tag12","tag13","tag14","tag15"],
  "segments": [
    {{
      "start": 0.0,
      "end": 2.5,
      "text": "IMPOSSIBLE GLITCH",
      "voiceover": "This glitch should not exist inside any modern video game.",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "IMPOSSIBLE"
    }},
    {{
      "start": 2.5,
      "end": 8.0,
      "text": "STAY WATCHING",
      "voiceover": "Stay till the end because what the developers hid will completely change how you play this game.",
      "text_effect": "typewriter",
      "position": "center",
      "highlight_word": "WATCHING"
    }},
    {{
      "start": 8.0,
      "end": 18.0,
      "text": "20 YEARS",
      "voiceover": "For exactly twenty years, speedrunners knew this glitch existed, but nobody could reproduce it consistently because it required a specific sequence of button presses timed to the exact frame.",
      "text_effect": "glitch",
      "position": "center",
      "highlight_word": "YEARS"
    }},
    {{
      "start": 18.0,
      "end": 38.0,
      "text": "ONE FRAME",
      "voiceover": "The window to execute it is literally one frame — that's 1 divided by 30 seconds. At 30 frames per second, you have 33 milliseconds. The average human blink takes 200 milliseconds. It is physically impossible to do this by eye. It requires a custom bot programmed to hit the input at the exact millisecond.",
      "text_effect": "glitch",
      "position": "top",
      "highlight_word": "FRAME"
    }},
    {{
      "start": 38.0,
      "end": 46.0,
      "text": "FOLLOW NOW",
      "voiceover": "SMASH LIKE if this broke your brain — Part 2 is dropping tomorrow and you will not believe what else they found.",
      "text_effect": "pop",
      "position": "bottom",
      "highlight_word": "FOLLOW"
    }}
  ]
}}
"""

    time.sleep(3)  # Burst protection

    for attempt in range(3):
        model_id = PRIMARY_MODEL if attempt < 2 else FALLBACK_MODEL
        try:
            print(f"Brain (attempt {attempt+1}/3): {model_id}")
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.8,
                    response_mime_type="application/json"
                )
            )
            package = json.loads(clean_json_response(response.text))

            if not validate_full_package(package):
                print("Validation failed — retrying...")
                time.sleep(10)
                continue

            # Save to Supabase (youtube_id added later by orchestrator)
            full_script = " ".join(s["voiceover"] for s in package["segments"])
            try:
                supabase.table("videos").insert({
                    "topic":  package["topic"],
                    "title":  package["title"],
                    "script": full_script,
                }).execute()
            except Exception as e:
                print(f"Supabase insert skipped: {e}")

            return package

        except Exception as e:
            err = str(e).upper()
            if "429" in err or "RESOURCE_EXHAUSTED" in err:
                wait = 65 + attempt * 30
                print(f"Rate limit. Waiting {wait}s (same model)...")
                time.sleep(wait)
            else:
                print(f"Brain error (attempt {attempt+1}): {e}")
                time.sleep(15)

    print("All attempts failed.")
    return None