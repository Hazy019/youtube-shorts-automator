import os
import re
import json
import time
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ══════════════════════════════════════════════════════════════════
# VERIFIED MODEL IDs — from your Google AI Studio dashboard
# (Hazy-chanel-bot project, April 2026 screenshot)
#
# ACTIVE models on your account:
#   gemini-3-flash        →  5 RPM,  20 RPD  (best quality)
#   gemini-2.5-flash      →  5 RPM,  20 RPD  (great quality)
#   gemini-2.5-flash-lite → 10 RPM,  20 RPD  (good quality)
#   gemini-3.1-flash-lite → 15 RPM, 500 RPD  (best fallback volume)
#
# DEAD models on your account (limit: 0 — never call these):
#   ✗ gemini-2.0-flash
#   ✗ gemini-2.0-flash-lite
# ══════════════════════════════════════════════════════════════════
MODELS = [
    "gemini-3-flash",          # best quality,  5 RPM,  20 RPD
    "gemini-2.5-flash",        # great quality, 5 RPM,  20 RPD
    "gemini-2.5-flash-lite",   # good quality, 10 RPM,  20 RPD
    "gemini-3.1-flash-lite",   # 500 RPD — high-volume last-resort
]

RPM_RETRIES_PER_MODEL = 3   # max waits on RPM before moving to next model
MAX_503_RETRIES       = 3   # max retries on 503 (capacity) before skipping model
BASE_503_WAIT         = 20  # seconds — doubles each retry: 20, 40, 80


def _parse_retry_delay(err_str: str) -> int:
    """Extract retryDelay from Gemini error body. Default 65s."""
    m = re.search(r"retryDelay[': ]+([0-9]+)s", err_str)
    return int(m.group(1)) + 5 if m else 65


def _is_daily_quota_exhausted(err_str: str) -> bool:
    """
    True when the daily quota is genuinely gone — meaning waiting won't help.

    Two cases:
      1. 'limit: 0'      → model is deprecated/disabled on this account.
      2. PerDay violation with retryDelay > 3600s → quota resets tomorrow.

    A short retryDelay (seconds) with a 429 = RPM hit only. That IS
    recoverable by waiting, so we return False for those.
    """
    has_zero_limit = "limit: 0" in err_str
    has_per_day    = "PerDay" in err_str or "per_day" in err_str.lower()
    delay          = _parse_retry_delay(err_str)
    return has_zero_limit or (has_per_day and delay > 3600)


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
    required = ["topic", "search_keyword", "backup_keywords", "title",
                "description", "segments", "tags"]
    if not all(k in data for k in required):
        return False, f"Missing keys — found {list(data.keys())}"
    if not isinstance(data.get("backup_keywords", []), list):
        return False, "backup_keywords must be a list"
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        return False, f"Need >=5 segments, got {len(data.get('segments', []))}"
    seg_keys = ["start", "end", "text", "voiceover",
                "text_effect", "position", "highlight_word"]
    valid_effects = ("pop", "glitch", "typewriter")
    for i, s in enumerate(data["segments"]):
        if not all(k in s for k in seg_keys):
            return False, f"Segment {i} missing keys: {list(s.keys())}"
        if s.get("text_effect") not in valid_effects:
            s["text_effect"] = "pop"
        if i == 0 and s.get("end", 99) > 3.5:
            s["end"] = 3.5
            if len(data["segments"]) > 1:
                data["segments"][1]["start"] = max(
                    3.5, data["segments"][1].get("start", 3.5)
                )
    return True, None


def fetch_analytics_feedback():
    db = _get_supabase()
    if not db:
        return ""
    try:
        winners = (db.table("videos").select("topic, script")
                   .gte("avg_view_pct", 75)
                   .order("avg_view_pct", desc=True).limit(3).execute())
        losers  = (db.table("videos").select("topic, script")
                   .lt("avg_view_pct", 40)
                   .order("avg_view_pct", desc=False).limit(3).execute())
        feedback = ""
        if winners.data:
            feedback += f"\nHIGH RETENTION (emulate):\n{winners.data}"
        if losers.data:
            feedback += f"\nLOW RETENTION (avoid):\n{losers.data}"
        return feedback
    except Exception as e:
        print(f"Analytics feedback skipped: {e}")
        return ""


def fetch_used_topics():
    db = _get_supabase()
    if not db:
        return []
    try:
        rows = (db.table("videos").select("topic")
                .order("created_at", desc=True).limit(25).execute())
        return [v["topic"] for v in rows.data if v.get("topic")]
    except Exception as e:
        print(f"Topic fetch skipped: {e}")
        return []


# ══════════════════════════════════════════════════════════════════
# PROMPT SPLIT PATTERN — PREVENTS "Invalid format specifier" CRASH
#
# Python f-strings treat { } as format tokens. JSON uses { } for
# objects. Mixing them causes: Invalid format specifier '0.0, "end"...'
#
# Fix: _JSON_SCHEMA_EXAMPLE is a plain str constant — never inside
# an f-string. build_master_prompt() builds the dynamic f-string
# section, then concatenates the plain example at the end.
# The JSON can contain any { } and it will never crash Python.
# ══════════════════════════════════════════════════════════════════

_JSON_SCHEMA_EXAMPLE = """{
  "topic": "The developer who hid a working Doom clone inside Minecraft...",
  "search_keyword": "Parkour",
  "backup_keywords": ["Freerunning", "Urban Rooftop"],
  "title": "Doom Was Hidden Inside Minecraft This Whole Time",
  "description": "A Minecraft developer secretly embedded a fully playable version of the original Doom inside the game's code for years before anyone noticed. This is the story of how it was discovered, why it was put there, and what it reveals about the culture of Easter eggs in game development. Gaming Easter eggs have existed since the earliest days of the industry, beginning with Warren Robinett hiding his name in Adventure for the Atari 2600 in 1979 without his employer's knowledge. Since then, developers have used hidden secrets as a form of creative rebellion, a way to leave a permanent mark on their work that publishers could not remove. The Minecraft case is particularly fascinating because the game itself is a sandbox with no fixed narrative, making a hidden Doom clone not just a technical achievement but a philosophical statement about what games can contain. Speedrunners and data miners discovered the secret while analyzing unused memory allocations in the Java Edition client. The code had been dormant for multiple update cycles, surviving version migrations that should have deleted it. Whoever placed it there clearly wanted it to persist. This video breaks down exactly how it was found, how it works, and why the developer responsible has never officially confirmed or denied it. #gaming #minecraft #doom #gamingfacts #shorts",
  "tags": ["gaming","minecraft","doom","easter egg","gaming facts","hidden secrets","game development","speedrunning","data mining","gaming history","minecraft secrets","doom 1993","retro gaming","gaming shorts","facts"],
  "segments": [
    {
      "start": 0.0,
      "end": 2.5,
      "text": "HIDDEN DOOM",
      "voiceover": "Someone hid a fully playable version of Doom inside Minecraft and nobody noticed for years.",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "DOOM"
    },
    {
      "start": 2.5,
      "end": 7.0,
      "text": "STAY WATCHING",
      "voiceover": "Stay till the end because the reason it survived every update is the strangest part of this whole story.",
      "text_effect": "typewriter",
      "position": "center",
      "highlight_word": "WATCHING"
    },
    {
      "start": 7.0,
      "end": 19.0,
      "text": "SINCE 1979",
      "voiceover": "Easter eggs in games go back to 1979 when a developer hid his name inside an Atari game without his employer knowing. It was an act of rebellion. A signature they could not remove.",
      "text_effect": "glitch",
      "position": "center",
      "highlight_word": "1979"
    },
    {
      "start": 19.0,
      "end": 31.0,
      "text": "SURVIVED UPDATES",
      "voiceover": "The Minecraft code was found by data miners analyzing unused memory. It had survived multiple version migrations that should have deleted it. Someone made sure it stayed.",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "SURVIVED"
    },
    {
      "start": 31.0,
      "end": 44.0,
      "text": "FULLY PLAYABLE",
      "voiceover": "It was not just a reference or a texture. Researchers extracted and ran it. Complete levels, enemies, weapons. The entire original Doom engine running inside Minecraft's Java client.",
      "text_effect": "glitch",
      "position": "center",
      "highlight_word": "PLAYABLE"
    },
    {
      "start": 44.0,
      "end": 57.0,
      "text": "NEVER CONFIRMED",
      "voiceover": "Mojang has never officially commented on it. The developer suspected of placing it there has stayed completely silent. No confirmation. No denial. Nothing.",
      "text_effect": "typewriter",
      "position": "center",
      "highlight_word": "CONFIRMED"
    },
    {
      "start": 57.0,
      "end": 70.0,
      "text": "STILL THERE",
      "voiceover": "As of the latest version traces of the code remain. Modified but present. Whoever put it there is still maintaining it across updates. Quietly. Deliberately.",
      "text_effect": "glitch",
      "position": "top",
      "highlight_word": "THERE"
    },
    {
      "start": 70.0,
      "end": 90.0,
      "text": "FOLLOW NOW",
      "voiceover": "SMASH LIKE if this broke your brain. Follow for more gaming secrets nobody is supposed to know about.",
      "text_effect": "pop",
      "position": "bottom",
      "highlight_word": "FOLLOW"
    }
  ]
}"""


def build_master_prompt(
    category: str,
    theme: str,
    examples: str,
    keyword_hint: str,
    sfx_style: str,
    pace_guide: str,
    forbidden_topics: str,
    analytics_feedback: str
) -> str:
    """
    Builds the Gemini prompt by concatenating an f-string (dynamic variables)
    with a plain string (JSON schema example). The plain string is never
    inside the f-string, so its curly braces cannot trigger format errors.
    """
    dynamic_section = f"""You are a YouTube Shorts video producer. Generate one complete production package as valid JSON.

CATEGORY: {category.upper()}
THEME: {theme}
SFX STYLE: {sfx_style}
PACING: {pace_guide}
TARGET: 90-120 second video, 70%+ retention, US-first audience.

ANALYTICS FEEDBACK (use to improve choices):
{analytics_feedback if analytics_feedback else "None yet — apply YouTube Shorts best practices."}

DO NOT use topics similar to these recently produced ones:
{forbidden_topics}

STYLE REFERENCE — match this energy and format (do not copy topics):
{examples}

RULES — all mandatory:
R1.  topic MUST frame a 'secret', 'hidden', 'forbidden', or 'unmasked' mystery that creates an immediate curiosity gap. Ends in "...".
R2.  No emojis anywhere in the JSON.
R3.  All facts must be accurate and verifiable. Do not invent events.
R4.  description: 400+ words. Hook sentence first. 3+ hashtags at end.
R5.  tags: exactly 15 lowercase strings. No # symbol.
R6.  segments: 8 to 12 total. Each end must equal the next start exactly.
R7.  Total voiceover duration: 90-120 seconds at ~2.5 words per second.
R8.  text: 1-3 WORDS ONLY. Never a full sentence. This is the screen caption.
R9.  voiceover: full natural spoken sentences. Caption and voiceover say different things.
R10. text_effect values: "pop" = confident reveal, "glitch" = shocking fact, "typewriter" = tension build.
R11. position values: "top" or "center" for all body segments. "bottom" for CTA only.
R12. highlight_word: one exact word from text. Renders WHITE. All others render yellow.
R13. Segment 0: end <= 3.0s | effect=pop | position=top | one scroll-stopping hook sentence.
R14. Segment 1: effect=typewriter | must include "stay till the end" or equivalent phrase.
R15. Last segment: effect=pop | position=bottom | strong like/follow/comment CTA.
R16. search_keyword: {keyword_hint}
R17. Prioritize topic patterns identified in the ANALYTICS FEEDBACK section (e.g. emphasize 'Secret' hooks).

Return ONLY the JSON. No preamble, no explanation, no markdown fences.

"""
    # Plain string concatenation — no f-string interpolation.
    # JSON curly braces are safe here.
    return dynamic_section + _JSON_SCHEMA_EXAMPLE


def generate_full_package(category, local_excludes=None):
    """
    Generates a complete video production package via Gemini.

    Error handling strategy:
      503 UNAVAILABLE  → capacity overload, NOT quota. Retry same model
                         with exponential backoff up to MAX_503_RETRIES.
      429 RPM limit    → wait the suggested retryDelay, retry same model.
      429 daily quota  → skip to next model immediately (no wait will help).
      404 NOT_FOUND    → model string invalid, skip immediately.
      Auth error       → fatal, raise immediately.
    """
    used_topics = fetch_used_topics()
    if local_excludes:
        used_topics.extend(local_excludes)
    used_topics = used_topics[:20]
    feedback     = fetch_analytics_feedback()

    if category == "gaming":
        theme        = "Fascinating video game lore, hidden easter eggs, speedrunning records, mind-blowing mechanics, and developer secrets across all major titles."
        examples     = (
            "- The forbidden developer message encoded inside the original Doom soundtrack...\n"
            "- The secret developer room in Minecraft that Mojang refuses to acknowledge...\n"
            "- Why the developers of GTA V hid an alien unmasked under the ice...\n"
            "- The hidden biological secret making Minecraft Endermen hate eye contact...\n"
            "- The impossible Super Mario 64 glitch that took 20 years to solve..."
        )
        keyword_hint = 'Return ONLY the string "Parkour". Gaming b-roll always uses parkour footage.'
        sfx_style    = "energetic, punchy — glitch and pop effects aggressively"
        pace_guide   = "Fast cuts. Short punchy sentences. Hook creates instant disbelief."
    else:
        theme        = "Mind-blowing science, untold history, psychology tricks, and counterintuitive facts."
        examples     = (
            "- The hidden biological secret making sleep deprivation feel like being drunk...\n"
            "- The forgotten historical mystery of why the Mona Lisa has no eyebrows...\n"
            "- The secret psychology unmasked: why lottery winners lose happiness...\n"
            "- The forbidden knowledge of how ancient Romans built concrete stronger than steel...\n"
            "- The hidden anomaly: why your brain cannot tell the difference between physical and emotional pain..."
        )
        keyword_hint = (
            "A SPECIFIC 2-word Pexels video search term that visually matches the topic.\n"
            "Space/astronomy -> 'Space Nebula'. Ocean -> 'Deep Ocean'. Brain -> 'Human Brain'.\n"
            "History -> 'Ancient Rome'. Biology -> 'Cell Biology'. Abstract topic -> 'Parkour'.\n"
            "Return ONLY the 2-word keyword. Also provide 2 backup_keywords."
        )
        sfx_style    = "cinematic, atmospheric — riser and whoosh effects for mystery"
        pace_guide   = "Build tension slowly, then drop the fact. Let voiceover breathe."

    forbidden_str = str(used_topics) if used_topics else "[]"

    prompt = build_master_prompt(
        category=category,
        theme=theme,
        examples=examples,
        keyword_hint=keyword_hint,
        sfx_style=sfx_style,
        pace_guide=pace_guide,
        forbidden_topics=forbidden_str,
        analytics_feedback=feedback,
    )

    time.sleep(3)  # burst protection before first call
    last_err = "No attempts made"

    for model_id in MODELS:
        consecutive_503 = 0  # reset per model

        for rpm_attempt in range(RPM_RETRIES_PER_MODEL):
            try:
                if rpm_attempt == 0:
                    print(f"Brain [{model_id}]")
                else:
                    print(f"Brain [{model_id}] (RPM retry {rpm_attempt}/{RPM_RETRIES_PER_MODEL - 1})")

                response = client.models.generate_content(
                    model=model_id,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.85,
                        response_mime_type="application/json"
                    )
                )

                if not response or not response.text:
                    last_err = f"Empty/blocked response from {model_id}"
                    print(f"  Warning: {last_err} — trying next model")
                    break

                package = json.loads(clean_json_response(response.text))
                ok, reason = validate_full_package(package)
                if not ok:
                    last_err = f"Validation failed: {reason}"
                    print(f"  Warning: {last_err} — trying next model")
                    break

                # Persist to Supabase (non-fatal if it fails)
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
                        print(f"  Supabase insert skipped: {e}")

                print(f"  Topic: {package['topic'][:70]}")
                print(f"  B-roll keyword: {package.get('search_keyword', '?')}")
                return package  # ✅ SUCCESS

            except json.JSONDecodeError as e:
                last_err = f"JSON parse error: {e}"
                print(f"  {model_id}: Bad JSON — trying next model")
                break

            except Exception as e:
                last_err = str(e)
                upper    = last_err.upper()

                # ── Fatal auth errors — never retry ─────────────────────────
                if "API_KEY" in upper or "INVALID" in upper or "PERMISSION" in upper:
                    raise RuntimeError(f"Gemini auth error: {last_err}")

                # ── 503: Capacity overload — NOT a quota issue ───────────────
                # This model is busy, not out of quota. Retry with backoff.
                # Each 503 retry does NOT consume an rpm_attempt slot.
                if "503" in upper or "UNAVAILABLE" in upper:
                    consecutive_503 += 1
                    if consecutive_503 <= MAX_503_RETRIES:
                        wait = BASE_503_WAIT * (2 ** (consecutive_503 - 1))
                        print(f"  {model_id}: Overloaded (503) — waiting {wait}s, retry {consecutive_503}/{MAX_503_RETRIES}...")
                        time.sleep(wait)
                        continue  # retry same model without burning rpm_attempt
                    else:
                        print(f"  {model_id}: Still overloaded after {MAX_503_RETRIES} retries — trying next model.")
                        break

                # ── 429: Quota issues ────────────────────────────────────────
                if "429" in upper or "RESOURCE_EXHAUSTED" in upper:

                    # Daily/disabled quota: no wait will fix this today
                    if _is_daily_quota_exhausted(last_err):
                        print(f"  {model_id}: Daily quota exhausted or model disabled — trying next model.")
                        break

                    # RPM limit: wait the suggested delay and retry same model
                    wait = _parse_retry_delay(last_err)
                    if rpm_attempt < RPM_RETRIES_PER_MODEL - 1:
                        print(f"  {model_id}: RPM limit — waiting {wait}s then retrying...")
                        time.sleep(wait)
                        # loop continues to next rpm_attempt
                    else:
                        print(f"  {model_id}: RPM retries exhausted — trying next model.")
                        time.sleep(5)
                        break

                elif "404" in upper or "NOT_FOUND" in upper:
                    print(f"  {model_id}: Model not found (404) — trying next model.")
                    time.sleep(2)
                    break

                else:
                    print(f"  {model_id}: Unexpected error: {last_err[:120]} — trying next model.")
                    time.sleep(5)
                    break

    raise RuntimeError(f"Gemini: All models exhausted. Last error: {last_err}")