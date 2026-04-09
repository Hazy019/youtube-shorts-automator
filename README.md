# Hazy Chanel Automator V176+ 🚀

Fully automated short-form video factory for YouTube Shorts and TikTok. Optimized for high-retention 90-120s content with advanced semantic asset intelligence.

## 🛠️ The New Workflow (V176+)

We have moved away from cloud-based TikTok uploads to avoid datacenter blocking. The system now follows a "Hybrid Production" model:

1.  **Cloud Production (`run_factory.py`)**: Renders videos in AWS and pushes them immediately to YouTube.
2.  **Local Syndication (`tools/bulk_tiktok_poster.py`)**: Drains a Supabase queue to upload to TikTok from your local machine, allowing for manual captcha solving.

## Project Architecture

```text
youtube-shorts-automator/
├── src/                        # Core application logic
│   ├── ai/                     # LLM & TTS Engines (brain.py, tts.py)
│   ├── api/                    # Integrations (youtube, tiktok-uploader)
│   ├── media/                  # ASSEMBLY: builder (Assembly), assets (Deduplication)
│   └── utils/                  # Discord Notifications & Loggers
├── tools/                      # REGISTRY & MAINTENANCE
│   ├── bulk_tiktok_poster.py   # 📥 Local Retry Manager (Drains the Queue)
│   ├── capture_tiktok_cookies.py
│   └── update_tokens.py
├── run_factory.py              # 🚀 PRIMARY ENTRY: Production & YouTube Push
└── run_analytics.py            # 📊 ANALYSIS: Weekly YouTube Insights
```

---

## 🚀 How to Run

### 1. Daily Production
```bash
python run_factory.py
```
*   **Action**: Generates a 90-120s script, downloads background clips, renders in AWS, and uploads to **YouTube**.
*   **Result**: The TikTok upload is automatically queued in Supabase as `PENDING`.

### 2. Clear TikTok Queue (Local Manager)
```bash
python tools/bulk_tiktok_poster.py
```
*   **Action**: Launches a local browser session, loads your TikTok cookies, and automatically uploads the pending backlog.
*   **Note**: If TikTok triggers a captcha, you can solve it manually in the window.

---

## 🧠 Asset Intelligence & Specs

- **Deduplication**: The system tracks every video ID from **Google Drive** and **Pexels** in Supabase. It will never use the same clip twice until the entire pool is exhausted.
- **Topic-Aligned Variety**: Uses "Semantic Routing" to pick background videos based on the category (Science vs. Nature vs. History).
- **Duration**: Target duration is **90-120 seconds** (8-12 segments), optimized for high-retention monetization.
- **Discord Integration**: Real-time status updates including a bulleted "Queue List" at the end of every factory run.

## 🔑 Tech Stack
- **AI Brain**: Google Gemini 2.5 Flash / 3.1 Flash Lite
- **Voiceover**: ElevenLabs (High fidelity)
- **Media Assembly**: Remotion Lambda (AWS)
- **Database**: Supabase (State Management)
- **Search**: Pexels API + Google Drive API v3

## ⚙️ Setup & Secrets

### GitHub Secrets / .env
- `GEMINI_API_KEY`: Google AI credentials.
- `ELEVENLABS_API_KEY`: Voice generation.
- `PEXELS_API_KEY`: Background video search.
- `SUPABASE_URL` / `SUPABASE_KEY`: Logic & Deduplication state.
- `WEBHOOK_QUEUE`: Dedicated channel for queue notifications.

### Local Maintenance
Run these scripts if you see "Token Expired" or "Invalid Cookies" errors:
1. `python tools/update_tokens.py` (For YouTube/Drive)
2. `python tools/capture_tiktok_cookies.py` (For TikTok)
