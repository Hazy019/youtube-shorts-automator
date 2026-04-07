import os
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ── VERIFIED FREE TIER MODEL IDs ─────────────────────────────────────────────
# gemini-2.5-flash-lite does NOT exist. Only use these two:
PRIMARY_MODEL  = "gemini-2.0-flash"       # 1500 RPD free, 15 RPM
FALLBACK_MODEL = "gemini-2.0-flash-lite"  # 1500 RPD free, 30 RPM
# ─────────────────────────────────────────────────────────────────────────────

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    raise EnvironmentError("GEMINI_API_KEY not found in environment.")
client = genai.Client(api_key=_api_key)

_supabase = None
def _get_supabase():
    global _supabase
    if _supabase is None:
        try:
            from supabase import create_client
            url = os.getenv("SUPABASE_URL")
            key = os.getenv("SUPABASE_KEY")
            if url and key:
                _supabase = create_client(url, key)
        except Exception as e:
            print(f"Supabase init failed (non-fatal): {e}")
    return _supabase


def clean_json_response(text):
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
        return False, f"Missing keys — found {list(data.keys())}"
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        return False, f"Need ≥5 segments, got {len(data.get('segments', []))}"
    seg_keys = ["start", "end", "text", "voiceover", "text_effect", "position", "highlight_word"]
    valid_effects = ("pop", "glitch", "typewriter")
    for i, s in enumerate(data["segments"]):
        if not all(k in s for k in seg_keys):
            return False, f"Segment {i} missing keys: {list(s.keys())}"
        if s.get("text_effect") not in valid_effects:
            s["text_effect"] = "pop"
        if i == 0 and s.get("end", 99) > 3.5:
            s["end"] = 3.5
            if len(data["segments"]) > 1:
                data["segments"][1]["start"] = max(3.5, data["segments"][1].get("start", 3.5))
    return True, None


def fetch_analytics_feedback():
    db = _get_supabase()
    if not db:
        return ""
    try:
        winners = db.table("videos").select("topic, script") \
            .gte("avg_view_pct", 75).order("avg_view_pct", desc=True).limit(3).execute()
        losers = db.table("videos").select("topic, script") \
            .lt("avg_view_pct", 40).order("avg_view_pct", desc=False).limit(3).execute()
        feedback = ""
        if winners.data:
            feedback += f"\nHIGH RETENTION (emulate pacing):\n{winners.data}"
        if losers.data:
            feedback += f"\nLOW RETENTION (avoid patterns):\n{losers.data}"
        return feedback
    except Exception as e:
        print(f"Analytics feedback skipped: {e}")
        return ""


def fetch_used_topics():
    db = _get_supabase()
    if not db:
        return []
    try:
        rows = db.table("videos").select("topic") \
            .order("created_at", desc=True).limit(25).execute()
        return [v["topic"] for v in rows.data if v.get("topic")]
    except Exception as e:
        print(f"Topic fetch skipped: {e}")
        return []


def generate_full_package(category, local_excludes=None):
    """
    ONE Gemini call → topic + keyword + full script + tags + description.
    Raises RuntimeError with real reason on failure so Discord gets useful info.
    """
    used_topics = fetch_used_topics()
    if local_excludes:
        used_topics.extend(local_excludes)
    used_topics = used_topics[:20]
    feedback = fetch_analytics_feedback()

    # ── Category configuration ────────────────────────────────────────────
    if category == "gaming":
        theme = "Fascinating video game lore, hidden easter eggs, speedrunning records, mind-blowing mechanics, and developer secrets across all major titles."
        examples = (
            "- The impossible Super Mario 64 glitch that took speedrunners 20 years to solve...\n"
            "- Why the developers of GTA V hid an alien frozen under the ice...\n"
            "- The terrifying lore reason Minecraft Endermen hate eye contact...\n"
            "- How one player broke Elden Ring's entire economy in a single session...\n"
            "- The hidden developer message encoded inside the original Doom soundtrack..."
        )
        # Gaming always uses Parkour Drive folder (physical action = good visual match)
        keyword_hint = (
            'Return ONLY "Parkour". Gaming b-roll is always parkour footage. Never return anything else.'
        )
        sfx_style  = "energetic, punchy — glitch and pop effects aggressively"
        pace_guide = "Fast cuts. Short punchy sentences. Hook creates instant disbelief."
    else:
        theme = "Mind-blowing science, untold history, psychology tricks, and counterintuitive facts."
        examples = (
            "- The biological mechanism making sleep deprivation feel like being drunk...\n"
            "- Why the Mona Lisa has no eyebrows and what it reveals about the Renaissance...\n"
            "- The counterintuitive psychology behind why lottery winners lose happiness...\n"
            "- How ancient Romans discovered concrete stronger than modern steel...\n"
            "- Why your brain literally cannot tell the difference between physical and emotional pain..."
        )
        # ── B-ROLL KEYWORD STRATEGY FOR GENERAL TOPICS ────────────────────
        # This is what was causing 100% parkour.
        # Rule: Gemini MUST return a specific 2-word Pexels search keyword
        # that visually matches the topic. Parkour is ONLY for abstract/psychology.
        # The keyword maps to real Pexels footage, not the Drive folder.
        keyword_hint = (
            'Return a SPECIFIC 2-word Pexels video search keyword that visually matches the topic.\n'
            'The keyword will be used to search stock footage — it must produce relevant, cinematic results.\n'
            '\n'
            'KEYWORD DECISION GUIDE:\n'
            '  - Space / astronomy / universe topics → "Space Nebula" or "Galaxy Stars" or "Solar System"\n'
            '  - Ocean / deep sea / marine topics → "Deep Ocean" or "Ocean Waves" or "Underwater Life"\n'
            '  - Brain / psychology / mind topics → "Human Brain" or "Neural Network" or "Mind Focus"\n'
            '  - History / ancient civilization → "Ancient Rome" or "Medieval Castle" or "Egyptian Pyramid"\n'
            '  - Biology / human body / cells → "Human Body" or "Cell Biology" or "DNA Strand"\n'
            '  - Physics / engineering / tech → "Quantum Physics" or "Circuit Board" or "Technology Innovation"\n'
            '  - Nature / animals / evolution → "Wild Nature" or "Wildlife Animals" or "Forest Timelapse"\n'
            '  - Weather / atmosphere / climate → "Lightning Storm" or "Storm Clouds" or "Aurora Borealis"\n'
            '  - Mathematics / geometry / patterns → "Sacred Geometry" or "Mathematical Pattern"\n'
            '  - Abstract psychology / behavior (no clear visual) → "Parkour"\n'
            '\n'
            'EXAMPLES by topic:\n'
            '  "Why the brain tricks you during sleep" → "Human Brain"\n'
            '  "How concrete was made in ancient Rome" → "Ancient Rome"\n'
            '  "The physics of black holes" → "Black Hole"\n'
            '  "Why lottery winners lose happiness" → "Parkour"\n'
            '  "The chemistry of love" → "Human Body"\n'
            '\n'
            'Return ONLY the 2-word keyword. No explanation.'
        )
        sfx_style  = "cinematic, atmospheric — riser and whoosh effects for mystery"
        pace_guide = "Build tension slowly, then drop the fact. Let voiceover breathe."

    forbidden_str = str(used_topics) if used_topics else "[]"

    # ── THE MASTER PROMPT ──────────────────────────────────────────────────
    # NOTE: The JSON example uses a plain string (not f-string) to avoid
    # escaping issues with curly braces. No {{ }} needed here.
    prompt = (
        f"You are a world-class YouTube Shorts scriptwriter AND professional video editor.\n"
        f"Generate a full production package in ONE response.\n"
        f"Target: INTERNATIONAL / US-FIRST audience. Platform: YouTube Shorts + TikTok.\n"
        f"\n"
        f"CATEGORY: {category}\n"
        f"THEME: {theme}\n"
        f"EDITING STYLE: {sfx_style}\n"
        f"PACING GUIDE: {pace_guide}\n"
        f"{feedback}\n"
        f"\n"
        f"ABSOLUTE RULES:\n"
        f"R1.  NO EMOJIS anywhere in the JSON.\n"
        f"R2.  topic must be unique, intriguing, end in '...'.\n"
        f"R3.  topic MUST NOT be semantically similar to: {forbidden_str}\n"
        f"R4.  description = 200+ words, US SEO, hook sentence first, 3+ hashtags.\n"
        f"R5.  tags = exactly 15 topic-specific SEO strings.\n"
        f"R6.  text (caption) = 1-3 WORDS MAX. Never a full sentence.\n"
        f"R7.  voiceover = full spoken script. No word limit.\n"
        f"R8.  Caption DIFFERS from voiceover. Caption=punchline. Voiceover=explanation.\n"
        f"R9.  highlight_word = most important/shocking word in caption. Renders WHITE.\n"
        f"R10. 5-7 segments total. Each = one edit cut.\n"
        f"R11. SEGMENT 0 (Hook): end <= 3.0s. text_effect=pop. position=top. 1 punchy sentence max.\n"
        f"R12. SEGMENT 1 (Tease): Must contain 'stay till the end'. text_effect=typewriter. position=center.\n"
        f"R13. BODY SEGMENTS: vary effects. glitch=shocking facts, pop=reveals, typewriter=slow builds.\n"
        f"     Each 4-8 seconds. position=center for facts, top for rhetorical questions.\n"
        f"R14. LAST SEGMENT (CTA): text_effect=pop. position=bottom. Include LIKE/COMMENT/FOLLOW driver.\n"
        f"R15. Timing formula: seconds = word_count / 2.5. Round up.\n"
        f"R16. search_keyword: {keyword_hint}\n"
        f"\n"
        f"TIMING STRUCTURE:\n"
        f"  Segment 0: start=0.0,  end=2.5  (hook, pop, top)\n"
        f"  Segment 1: start=2.5,  end=8.0  (tease, typewriter, center)\n"
        f"  Segment 2: start=8.0,  end=18.0 (fact 1, glitch, center)\n"
        f"  Segment 3: start=18.0, end=28.0 (fact 2, pop, center)\n"
        f"  Segment 4: start=28.0, end=38.0 (biggest reveal, glitch, top)\n"
        f"  Segment 5: start=38.0, end=46.0 (CTA, pop, bottom)\n"
        f"\n"
        f"EXAMPLES for {category}:\n"
        f"{examples}\n"
        f"\n"
        f"Return ONLY valid JSON, no markdown, no preamble:\n"
        + """
{
  "topic": "Unique topic string ending in ...",
  "search_keyword": "Deep Ocean",
  "title": "SEO title under 50 chars",
  "description": "200+ word SEO description with 3+ hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10","tag11","tag12","tag13","tag14","tag15"],
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "IMPOSSIBLE FACT",
      "voiceover": "This fact should change how you see the world forever.",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "IMPOSSIBLE"
    },
    {
      "start": 2.5,
      "end": 8.0,
      "text": "STAY WATCHING",
      "voiceover": "Stay till the end — the last fact will completely change how you see this.",
      "text_effect": "typewriter",
      "position": "center",
      "highlight_word": "WATCHING"
    },
    {
      "start": 8.0,
      "end": 18.0,
      "text": "MIND BLOWN",
      "voiceover": "Scientists discovered that the deepest part of the ocean has more pressure than 50 jumbo jets stacked on your chest.",
      "text_effect": "glitch",
      "position": "center",
      "highlight_word": "BLOWN"
    },
    {
      "start": 18.0,
      "end": 30.0,
      "text": "STILL UNEXPLORED",
      "voiceover": "Over 80 percent of the ocean floor has never been mapped in detail. We know more about the surface of Mars than about Earth's own ocean depths.",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "UNEXPLORED"
    },
    {
      "start": 30.0,
      "end": 42.0,
      "text": "FOLLOW NOW",
      "voiceover": "SMASH LIKE if this broke your brain — Part 2 drops tomorrow and you will not believe what we found down there.",
      "text_effect": "pop",
      "position": "bottom",
      "highlight_word": "FOLLOW"
    }
  ]
}
"""
    )

    time.sleep(3)  # Burst protection

    last_err = "Unknown — all 3 attempts failed"
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

            if not response or not response.text:
                last_err = f"Empty/blocked response from {model_id}"
                print(f"  Retry: {last_err}")
                time.sleep(15)
                continue

            package = json.loads(clean_json_response(response.text))

            ok, reason = validate_full_package(package)
            if not ok:
                last_err = f"Validation failed: {reason}"
                print(f"  Retry: {last_err}")
                time.sleep(10)
                continue

            # Save to Supabase (non-fatal)
            db = _get_supabase()
            if db:
                try:
                    full_script = " ".join(s["voiceover"] for s in package["segments"])
                    db.table("videos").insert({
                        "topic":  package["topic"],
                        "title":  package["title"],
                        "script": full_script,
                    }).execute()
                except Exception as e:
                    print(f"Supabase insert skipped: {e}")

            kw = package.get("search_keyword", "?")
            print(f"  Topic: {package['topic'][:60]}...")
            print(f"  B-roll keyword: {kw}")
            return package

        except json.JSONDecodeError as e:
            last_err = f"JSON parse error: {e}"
            print(f"  Retry: {last_err}")
            time.sleep(10)

        except Exception as e:
            last_err = str(e)
            upper = last_err.upper()
            if "429" in upper or "RESOURCE_EXHAUSTED" in upper:
                wait = 65 + attempt * 30
                print(f"  Rate limit. Waiting {wait}s (same model {model_id})...")
                time.sleep(wait)
            elif "API_KEY" in upper or "INVALID" in upper or "PERMISSION" in upper:
                raise RuntimeError(f"Gemini auth error: {last_err}")
            else:
                print(f"  Brain error (attempt {attempt+1}): {last_err}")
                time.sleep(15)

    raise RuntimeError(f"All 3 Gemini attempts failed. Last: {last_err}")