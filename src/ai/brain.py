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
#   gemini-3-flash-preview        →  5 RPM,  20 RPD  (best quality)
#   gemini-2.5-flash              →  5 RPM,  20 RPD  (great quality)
#   gemini-2.5-flash-lite          → 10 RPM,  20 RPD  (good quality)
#   gemini-3.1-flash-lite-preview → 15 RPM, 500 RPD  (best fallback volume)
#
# DEAD models on your account (limit: 0 — never call these):
#   ✗ gemini-2.0-flash
#   ✗ gemini-2.0-flash-lite
# ══════════════════════════════════════════════════════════════════
MODELS = [
    "gemini-3-flash-preview",          # best quality,  5 RPM,  20 RPD
    "gemini-2.5-flash",                # great quality, 5 RPM,  20 RPD
    "gemini-2.5-flash-lite",           # good quality, 10 RPM,  20 RPD
    "gemini-3.1-flash-lite-preview",   # 500 RPD — high-volume last-resort
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


def with_supabase_retry(operation, max_attempts=3):
    """Wrapper to handle transient network issues with Supabase."""
    for attempt in range(max_attempts):
        try:
            return operation.execute()
        except Exception as e:
            if attempt == max_attempts - 1:
                raise e
            print(f"  Supabase error (attempt {attempt+1}/{max_attempts}): {e}. Retrying...")
            time.sleep(2)



def clean_json_response(text):
    text = text.strip()
    
    # 1. Try regex extraction of markdown code blocks
    # Look for ```json <content> ``` or ``` <content> ```
    match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if not match:
        match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        
    if match:
        cleaned = match.group(1).strip()
        # Double check if this cleaned text is valid-looking JSON
        if cleaned.startswith('{') and cleaned.endswith('}'):
            return cleaned
        if cleaned.startswith('[') and cleaned.endswith(']'):
            return cleaned
            
    # 2. Fallback: Find the outermost curly braces or square brackets
    start_obj = text.find('{')
    end_obj = text.rfind('}')
    
    start_arr = text.find('[')
    end_arr = text.rfind(']')
    
    # Determine whether we have a valid-looking object or array
    has_obj = start_obj != -1 and end_obj != -1 and end_obj > start_obj
    has_arr = start_arr != -1 and end_arr != -1 and end_arr > start_arr
    
    if has_obj and has_arr:
        # If both are present, pick the outer one
        if start_obj < start_arr:
            return text[start_obj:end_obj + 1].strip()
        else:
            return text[start_arr:end_arr + 1].strip()
    elif has_obj:
        return text[start_obj:end_obj + 1].strip()
    elif has_arr:
        return text[start_arr:end_arr + 1].strip()
        
    # If no braces/brackets found, just return original stripped text
    return text



def validate_full_package(data):
    required = ["topic", "search_keyword", "backup_keywords", "title",
                "description", "segments", "tags", "pinned_comment"]
    if not all(k in data for k in required):
        return False, f"Missing keys — found {list(data.keys())}"
    if not isinstance(data.get("backup_keywords", []), list):
        return False, "backup_keywords must be a list"
    if not isinstance(data.get("pinned_comment"), str) or not data["pinned_comment"].strip():
        return False, "pinned_comment must be a non-empty string"
    if not isinstance(data["segments"], list) or len(data["segments"]) < 5:
        return False, f"Need >=5 segments, got {len(data.get('segments', []))}"
    seg_keys = ["start", "end", "text", "voiceover",
                "text_effect", "position", "highlight_word"]
    valid_effects = ("pop", "glitch", "typewriter", "bounce", "glow", "slide")
    
    # ── Duration, Role & Hook Validation ──────────────────────────────────────
    roles = ["hook", "stakes", "build", "payoff", "button"]
    for i, s in enumerate(data["segments"]):
        # Auto-fill missing non-critical keys
        if "role" not in s:
            s["role"] = roles[min(i, len(roles) - 1)]
        if "visual_query" not in s or not s["visual_query"]:
            s["visual_query"] = data.get("search_keyword", "digital security server")
        if "text_effect" not in s or s["text_effect"] not in valid_effects:
            s["text_effect"] = "pop" if i == 0 else "typewriter"
        if "position" not in s:
            s["position"] = "top" if i == 0 else ("bottom" if i == len(data["segments"]) - 1 else "center")
        if "highlight_word" not in s or not s["highlight_word"]:
            words = s.get("text", "").split()
            s["highlight_word"] = words[0] if words else ""

        # Check required fields
        if not all(k in s for k in ["text", "voiceover"]):
            return False, f"Segment {i} missing text or voiceover"
        
        # Auto-compute start/end if missing
        if "start" not in s:
            s["start"] = 0.0 if i == 0 else data["segments"][i-1].get("end", 0.0)
        if "end" not in s:
            # Approx 2.2 words per second + 0.5s pause
            vo_len = len(s.get("voiceover", "").split())
            duration_est = max(2.5, round(vo_len / 2.2, 1))
            s["end"] = s["start"] + duration_est

        # Force Hook constraints (Segment 0)
        if i == 0 and s.get("end", 99) > 3.5:
            s["end"] = 3.5
            if len(data["segments"]) > 1:
                data["segments"][1]["start"] = max(3.5, data["segments"][1].get("start", 3.5))

        # Force Shorts constraint (MAX 59.0s)
        if s.get("start", 0) >= 59.0:
            print(f"  Warning: Truncating segment {i} (starts at {s['start']}s >= 59s)")
            data["segments"] = data["segments"][:i]
            break
        
        if s.get("end", 0) > 59.0:
            print(f"  Warning: Capping segment {i} end time at 59.0s (was {s['end']}s)")
            s["end"] = 59.0
            data["segments"] = data["segments"][:i+1] # This is the last valid segment
            break

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
# ══════════════════════════════════════════════════════════════════

_JSON_SCHEMA_EXAMPLE = """{
  "topic": "The $81M Bank Typo Hack",
  "category": "us-centric",
  "hook_style": "number",
  "search_keyword": "Cyber Security Hacker",
  "backup_keywords": ["Bank Vault Security", "Server Room Dark"],
  "title": "A Single Typo Cost Hackers $81 Million",
  "description": "In 2016, hackers nearly stole $1 billion from a national bank until a single misspelled word triggered an alarm. Here is how the impossible heist was caught.\\n\\n#shorts #cybersecurity #techfacts",
  "pinned_comment": "Fun fact: The hackers misspelled 'foundation' as 'fandation' on transfer #5. Would you have caught it?",
  "tags": ["shorts","cybersecurity","heist","tech facts","bank hack","money","history","crazy stories","explained"],
  "segments": [
    {
      "role": "hook",
      "start": 0.0,
      "end": 2.5,
      "text": "TYPO HACK",
      "voiceover": "A one-letter typo stopped an eighty-million-dollar cyber heist.",
      "visual_query": "bank vault digital security hacker code",
      "text_effect": "pop",
      "position": "top",
      "highlight_word": "TYPO"
    },
    {
      "role": "stakes",
      "start": 2.5,
      "end": 7.0,
      "text": "BANK BREACH",
      "voiceover": "In 2016, hackers infiltrated the central bank of Bangladesh.",
      "visual_query": "server room flashing led lights dark",
      "text_effect": "typewriter",
      "position": "center",
      "highlight_word": "BREACH"
    },
    {
      "role": "build",
      "start": 7.0,
      "end": 28.0,
      "text": "FED SERVERS",
      "voiceover": "They routed dozens of fake payment requests through Federal Reserve servers in New York.",
      "visual_query": "financial stock ticker digital data",
      "text_effect": "glitch",
      "position": "center",
      "highlight_word": "SERVERS"
    },
    {
      "role": "payoff",
      "start": 28.0,
      "end": 42.0,
      "text": "MISSPELLED",
      "voiceover": "Their fifth transfer misspelled foundation as fandation... triggering alarms instantly.",
      "visual_query": "keyboard typing closeup red error screen",
      "text_effect": "glow",
      "position": "center",
      "highlight_word": "MISSPELLED"
    },
    {
      "role": "button",
      "start": 42.0,
      "end": 48.0,
      "text": "ESCAPED CASH",
      "voiceover": "How much cash did they escape with before the plug was pulled?",
      "visual_query": "money stacks counting currency",
      "text_effect": "bounce",
      "position": "bottom",
      "highlight_word": "CASH"
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
    dynamic_section = f"""You are the head scriptwriter for a high-retention YouTube Shorts channel called Hazy Insight, which produces 30-45 second trivia and news explainer videos.
Your ONLY job is to write scripts that survive the first 3 seconds and hold attention to the final second. You are graded on watch-through rate, not on information density.

CATEGORY: {category.upper()}
THEME: {theme}
SFX STYLE: {sfx_style}
PACING: {pace_guide}
AUDIENCE: US-based (use US slang, cultural references, and American-English).

ANALYTICS FEEDBACK:
{analytics_feedback if analytics_feedback else "No feedback yet — use YouTube Shorts best practices."}

DO NOT repeat these recent topics:
{forbidden_topics}

DO NOT USE THE EXAMPLE TOPIC FROM THE SCHEMA.

STYLE REFERENCE (match energy, do not copy topics):
{examples}

══════════════════════════════════════════════════════════
PART 1 — NON-NEGOTIABLE HOOK RULES (FIRST 3 SECONDS)
══════════════════════════════════════════════════════════
H1. The first sentence must be under 8 words.
H2. The first sentence must be a specific, concrete, surprising CLAIM or NUMBER — never a setup, never a question, never a category label.
H3. BANNED opening phrases (AUTO-REJECT and rewrite if generated):
    "Did you know", "Here's why", "Let's talk about", "Today we're looking at",
    "Have you ever wondered", "This is the story of", "Imagine if", "Wait, actually",
    "So basically", "You see", "In a world where".
H4. The hook must create a curiosity gap: state the claim boldly, withhold the full explanation for at least two more sentences.

══════════════════════════════════════════════════════════
PART 2 — 5-STAGE NARRATIVE STRUCTURE (MANDATORY IN THIS ORDER)
══════════════════════════════════════════════════════════
Every video MUST contain exactly 5 to 6 segments following this structure:
1. HOOK (role: "hook", 1 sentence, <8 words) — the surprising claim or number.
2. STAKES (role: "stakes", 1 sentence) — why this claim matters or what's at risk / who it affects.
3. BUILD (role: "build", 1-2 sentences) — deliver the explanation, escalating specificity, one new fact per sentence, never repeat a fact.
4. PAYOFF (role: "payoff", 1 sentence) — the twist, resolution, or core revelation.
5. BUTTON (role: "button", 1 sentence) — a punchy line that either (a) recontextualizes the whole video, or (b) poses a next-level question that makes a comment/rewatch likely. NEVER a generic "let me know what you think" CTA.

══════════════════════════════════════════════════════════
PART 3 — VISUAL SYNC REQUIREMENT (FOR EVERY SEGMENT)
══════════════════════════════════════════════════════════
For EVERY segment, you MUST output a `visual_query` field:
- A concrete, literal, filmable search term (2-5 words) for stock footage that matches what is being SAID at that exact moment.
- Bad: "science concept", "technology idea", "money problem".
- Good: "bank vault digital security hacker code", "scientist pipette lab closeup", "server room flashing led lights dark".

══════════════════════════════════════════════════════════
PART 4 — PACING & WORD BUDGET (EDGE-TTS VOICE OPTIMIZATION)
══════════════════════════════════════════════════════════
W1. TOTAL SCRIPT WORD COUNT: 70 to 105 words total across all segments.
    (Approx 2.2 words/second at natural TTS pace, leaving room for dramatic pauses).
    Target duration is EXACTLY 35.0 to 45.0 seconds.
W2. One idea per sentence. No compound sentences stacking two facts.
W3. Average sentence length: 8-14 words. Short sentences hit harder.
W4. Use "..." (ellipsis) for dramatic pauses (600ms silence). Use 1-2 per video.
W5. Use contractions always: "it's", "they've", "didn't", "can't", "you'd".
W6. NO "AI SLOP" words: Unleash, Delve, Uncover, Secrets, Mysterious, Testament,
    Shrouded, Landscape, Embark, Journey, Realm, Tapestry, Vibrant, Elevate, Revolutionize.

══════════════════════════════════════════════════════════
PART 5 — METADATA & VISUAL CAPTION RULES
══════════════════════════════════════════════════════════
R1. topic: Short internal topic name ending in "..."
R2. title: Punchy viral title under 50 characters, leading with the hook's core claim.
R3. description: 50-80 words max. 2-3 engaging, conversational sentences summarizing the core story + exactly 3 hashtags (#shorts and 2 topic hashtags).
R4. pinned_comment: Unique bonus trivia fact or high-engagement discussion question tailored to the topic.
R5. tags: exactly 10 to 15 lowercase strings.
R6. text (on-screen caption): 1-3 WORDS ONLY. Dynamic contextual topic label (e.g., "TYPO HACK", "BANK BREACH"). Never placeholder text.
R7. text_effect: Cycle across segments: "pop", "glitch", "typewriter", "bounce", "glow", "slide".
R8. position: "top" for hook, "center" for body, "bottom" for button/CTA.
R9. highlight_word: One exact word from text that renders WHITE (others render gold).

Return ONLY the JSON object. No preamble, no markdown, no explanation.
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

    if category == "us-centric":
        theme        = "High-energy US & Tech stories: Cybersecurity mysteries, dark web heists, rogue AI glitches, financial anomalies, and secret American history."
        examples     = (
            "- How a single zero-day bug shut down a major US oil pipeline for 6 days...\\n"
            "- The mystery of the guy who threw away a hard drive with $500M in Bitcoin into a landfill...\\n"
            "- How hackers used a connected aquarium thermometer to rob a US casino's database...\\n"
            "- The 1987 ATM glitch in Chicago that let people withdraw unlimited cash for 4 hours...\\n"
            "- Why the US government actually tried to outlaw pinball machines for 30 years...\\n"
            "- The classified code glitch that almost started an accidental nuclear response in 1983..."
        )
        keyword_hint = 'Return a 2-3 word Pexels/Pixabay search term matching the exact subject (e.g., "Cyber Security", "Hacker Code", "Server Room", "Matrix Code", "Bank Vault", "American Flag", "New York Night"). Be specific to the topic — avoid generic terms like Parkour.'
        sfx_style    = "punchy, tech, modern US style — digital glitch, pop, and bass drops"
        pace_guide   = "High energy. Use US slang, tech terminology, and suspenseful pacing. Hook must grab attention in the first 2 seconds."
        
        # Inject the specific user feedback for US retention
        feedback += "\nUS & TECH RETENTION STRATEGY: Focus on Cybersecurity, Tech Heists, Rogue Code, and Bizarre US Anomalies. Use distinct hook archetypes (Reverse Logic, Secret Disclosure, High Stakes Loss). Never leave the core mystery unanswered!"
    else:
        theme        = "DEEPLY OBSCURE and MIND-BLOWING science, history, and psychology. NO SURFACE-LEVEL TRIVIA. The facts must be so niche and thoroughly researched that even experts would be surprised. DO NOT generate 'AI slop' listicles."
        examples     = (
            "- Why a 19th-century solar storm caused telegraph machines to send messages while completely unplugged...\\n"
            "- The classified Soviet project that accidentally created a lake so radioactive it could kill you in one hour...\\n"
            "- The bizarre psychological condition where the brain perceives loved ones as identical imposters (Capgras delusion)...\\n"
            "- How the CIA spent 20 million dollars training acoustic kitty spies, only for the first cat to be hit by a taxi...\\n"
            "- The physiological reason why human tears have different crystal structures depending on the emotion that caused them..."
        )
        keyword_hint = (
            "A STRICTLY RELEVANT 2-word Pexels video search term that visually matches the topic.\\n"
            "Space/astronomy -> 'Space Nebula'. Ocean -> 'Deep Ocean'. Brain -> 'Human Brain'.\\n"
            "History -> 'Ancient Ruins'. Biology -> 'Microscope Cell'. Abstract/Tech -> 'Abstract Data'.\\n"
            "DO NOT default to 'Parkour' or generic gameplay. The B-roll MUST visually represent the topic.\\n"
            "Return ONLY the 2-word keyword. Also provide 2 highly specific backup_keywords."
        )
        sfx_style    = "cinematic, atmospheric — riser, whoosh, and subtle heartbeat effects for tension"
        pace_guide   = "Build tension slowly but keep cuts fast. Drop the fact. Let voiceover breathe slightly, but maintain momentum."

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

                # ── DOOM REPETITION SAFETY CHECK ────────────────────────────
                generated_topic = package.get("topic", "").lower()
                if "doom" in generated_topic and "minecraft" in generated_topic:
                    last_err = "Model returned the 'Doom/Minecraft' example topic."
                    print(f"  Warning: {last_err} — forcing retry with next model.")
                    # Add to excludes so it doesn't happen again
                    used_topics.append(package.get("topic"))
                    break

                # Persist to Supabase (Enables Self-Healing Recovery)
                db = _get_supabase()
                if db:
                    try:
                        full_script = " ".join(s["voiceover"] for s in package["segments"])
                        with_supabase_retry(
                            db.table("videos").insert({
                                "topic":    package["topic"],
                                "title":    package["title"],
                                "script":   full_script,
                                "category": category, # Pro Move: Isolated channel recovery
                                "payload":  package,  # Pro Move: Full recovery of timing/keywords
                                "tiktok_status": "INITIALIZED", 
                            })
                        )
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