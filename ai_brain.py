import os
import json
import time
import random
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
# VERIFIED FREE TIER MODEL IDs — DO NOT CHANGE THESE
#
# gemini-2.0-flash      → 1500 RPD, 15 RPM  (PRIMARY)
# gemini-2.0-flash-lite → 1500 RPD, 30 RPM  (FALLBACK only)
#
# DEAD MODELS (404 on v1beta API — NEVER USE):
#   gemini-1.5-flash, gemini-1.5-flash-8b, gemini-2.5-flash,
#   gemini-2.5-flash-lite, any *-preview, any *-latest, any *-001
#
# When gemini-2.0-flash hits 15 RPM limit locally:
#   → WAIT 65 seconds and retry the SAME model.
#   → Do NOT fall back to a different model — fallback models are dead.
# ══════════════════════════════════════════════════════════════════
PRIMARY_MODEL  = "gemini-2.0-flash"
FALLBACK_MODEL = "gemini-2.5-flash"
TERTIARY_MODEL = "gemini-2.0-flash-lite"
MODELS = [PRIMARY_MODEL, FALLBACK_MODEL, TERTIARY_MODEL]

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
    ONE Gemini call returns everything.
    Raises RuntimeError with the real reason on failure.

    QUOTA NOTE: gemini-2.0-flash has 15 RPM. If running TWO videos locally
    back-to-back, the second call may hit the rate limit. This is an RPM
    (per-minute) limit, NOT an RPD (per-day) limit. The fix is to wait 65s
    and retry the SAME model — NOT to fall back to a different model.
    gemini-1.5-flash and gemini-1.5-flash-8b are DEAD on the v1beta API.
    """
    used_topics = fetch_used_topics()
    if local_excludes:
        used_topics.extend(local_excludes)
    used_topics = used_topics[:20]
    feedback = fetch_analytics_feedback()

    if category == "gaming":
        theme = "Fascinating video game lore, hidden easter eggs, speedrunning records, mind-blowing mechanics, and developer secrets across all major titles."
        examples = (
            "- The impossible Super Mario 64 glitch that took speedrunners 20 years to solve...\n"
            "- Why the developers of GTA V hid an alien frozen under the ice...\n"
            "- The terrifying lore reason Minecraft Endermen hate eye contact...\n"
            "- How one player broke Elden Ring's entire economy in a single session...\n"
            "- The hidden developer message encoded inside the original Doom soundtrack..."
        )
        keyword_hint = 'Return ONLY "Parkour". Gaming b-roll always uses parkour footage.'
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
        keyword_hint = (
            "Return a SPECIFIC 2-word Pexels video search keyword matching the topic visually.\n"
            "DECISION GUIDE:\n"
            "  Space / astronomy       → 'Space Nebula' or 'Galaxy Stars'\n"
            "  Ocean / deep sea        → 'Deep Ocean' or 'Ocean Waves'\n"
            "  Brain / psychology      → 'Human Brain' or 'Neural Network'\n"
            "  History / ancient       → 'Ancient Rome' or 'Medieval Castle'\n"
            "  Biology / body / cells  → 'Human Body' or 'Cell Biology'\n"
            "  Physics / tech          → 'Quantum Physics' or 'Circuit Board'\n"
            "  Nature / animals        → 'Wild Nature' or 'Wildlife Animals'\n"
            "  Weather / storms        → 'Lightning Storm' or 'Storm Clouds'\n"
            "  Abstract (no good visual) → 'Parkour'\n"
            "Return ONLY the 2-word keyword."
        )
        sfx_style  = "cinematic, atmospheric — riser and whoosh effects for mystery"
        pace_guide = "Build tension slowly, then drop the fact. Let voiceover breathe."

    forbidden_str = str(used_topics) if used_topics else "[]"

    prompt = (
        f"You are a world-class YouTube Shorts scriptwriter AND professional video editor.\n"
        f"Generate a full production package in ONE response.\n"
        f"Target: INTERNATIONAL / US-FIRST audience. Platform: YouTube Shorts + TikTok.\n\n"
        f"CATEGORY: {category}\n"
        f"THEME: {theme}\n"
        f"EDITING STYLE: {sfx_style}\n"
        f"PACING GUIDE: {pace_guide}\n"
        f"{feedback}\n\n"
        f"RULES:\n"
        f"R1.  NO EMOJIS in JSON.\n"
        f"R2.  topic must be unique, intriguing, end in '...'.\n"
        f"R3.  topic MUST NOT be semantically similar to: {forbidden_str}\n"
        f"R4.  description = 200+ words, US SEO, hook sentence first, 3+ hashtags.\n"
        f"R5.  tags = exactly 15 topic-specific SEO strings.\n"
        f"R6.  text (caption) = 1-3 WORDS MAX. Never a sentence.\n"
        f"R7.  voiceover = full spoken script.\n"
        f"R8.  Caption DIFFERS from voiceover. Caption=punchline. Voiceover=explanation.\n"
        f"R9.  highlight_word = most important word in caption. Renders WHITE.\n"
        f"R10. 5-7 segments. Each = one edit cut.\n"
        f"R11. SEGMENT 0 (Hook): end<=3.0s. text_effect=pop. position=top. 1 punchy sentence.\n"
        f"R12. SEGMENT 1 (Tease): 'stay till the end'. text_effect=typewriter. position=center.\n"
        f"R13. BODY: glitch=shocking, pop=reveals, typewriter=builds. 4-8s each. center/top.\n"
        f"R14. LAST (CTA): pop. position=bottom. LIKE/COMMENT/FOLLOW driver.\n"
        f"R15. Timing: seconds = word_count / 2.5\n"
        f"R16. search_keyword: {keyword_hint}\n\n"
        f"EXAMPLES for {category}:\n{examples}\n\n"
        f"Return ONLY valid JSON:\n"
        + """
{
  "topic": "Unique topic ending in ...",
  "search_keyword": "Deep Ocean",
  "title": "SEO title under 50 chars",
  "description": "200+ word SEO description with 3+ hashtags",
  "tags": ["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8","tag9","tag10","tag11","tag12","tag13","tag14","tag15"],
  "segments": [
    {"start": 0.0, "end": 2.5, "text": "IMPOSSIBLE FACT", "voiceover": "Short hook sentence.", "text_effect": "pop", "position": "top", "highlight_word": "IMPOSSIBLE"},
    {"start": 2.5, "end": 8.0, "text": "STAY WATCHING", "voiceover": "Stay till the end because this will change everything.", "text_effect": "typewriter", "position": "center", "highlight_word": "WATCHING"},
    {"start": 8.0, "end": 18.0, "text": "MIND BLOWN", "voiceover": "Fact explanation here with real detail.", "text_effect": "glitch", "position": "center", "highlight_word": "BLOWN"},
    {"start": 18.0, "end": 30.0, "text": "STILL UNEXPLORED", "voiceover": "Second fact with more detail.", "text_effect": "pop", "position": "top", "highlight_word": "UNEXPLORED"},
    {"start": 30.0, "end": 42.0, "text": "FOLLOW NOW", "voiceover": "SMASH LIKE if this broke your brain. Part 2 drops tomorrow.", "text_effect": "pop", "position": "bottom", "highlight_word": "FOLLOW"}
  ]
}
"""
    )

    time.sleep(3)  # Burst protection — always wait before first call

    last_err = "Unknown — all attempts failed"
    for attempt in range(3):
        model_id = MODELS[attempt]
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
            if "429" in upper or "RESOURCE_EXHAUSTED" in upper or "QUOTA" in upper:
                wait = 70 + (attempt * 30)
                print(f"  Rate limit (RPM). Waiting {wait}s then retrying {model_id}...")
                time.sleep(wait)
            elif "404" in upper or "NOT_FOUND" in upper:
                print(f"  Model {model_id} returned 404 NOT FOUND. Skipping to next fallback...")
                last_err = f"404 NOT FOUND for {model_id}"
                time.sleep(2)
                continue
            elif "API_KEY" in upper or "INVALID" in upper or "PERMISSION" in upper:
                raise RuntimeError(f"Gemini auth error: {last_err}")
            else:
                print(f"  Brain error (attempt {attempt+1}): {last_err}")
                time.sleep(15)

    raise RuntimeError(f"All 3 Gemini attempts failed. Last: {last_err}")