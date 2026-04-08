# Hazy Chanel Automator V5 🚀

Fully automated short-form video factory for YouTube Shorts and TikTok.

## Project Architecture

The repository has been logically restructured to cleanly separate internal code from entry commands:

```text
hazy-shorts-automator/
├── src/                        # Core application logic
│   ├── ai/                     # LLM and TTS Engines (brain.py, tts.py)
│   ├── api/                    # Integrations (youtube, tiktok, google drive)
│   ├── media/                  # Assembly & Download (builder, assets, maker)
│   └── utils/                  # Analytics & Discord Bot
├── tools/                      # Manual maintenance scripts (update tokens, captchas, retries)
├── run_factory.py              # 🚀 ENTRY 1: Daily Video Production
├── run_analytics.py            # 🚀 ENTRY 2: Weekly YouTube Data Sync
└── .github/workflows/          # Automated execution definitions
```

## How to Run

Instead of navigating the complex web of sub-functions, anyone interacting with the codebase only needs to run the top-level scripts located in the root!

### 1. Manual Generation (Single Video Run)
```bash
python run_factory.py
```
*This fetches a topic, generates a script, downloads assets, renders the video in Remotion, and pushes to YouTube and TikTok.*

### 2. Manual Analytics Report
```bash
python run_analytics.py
```
*Connects to YouTube Analytics API, updates Supabase views/retention, and generates an AI Insights summary sent to Discord.*

---

## Tech Stack
- **AI**: Google Gemini (2.0 Flash)
- **Voice**: ElevenLabs / Microsoft Edge Neural Fallback
- **Storage**: AWS S3 & Google Drive
- **Render**: Remotion Lambda (AWS)
- **Database**: Supabase
- **Syndication**: YouTube Data API v3 & TikTok-Uploader

## Setup & Maintenance

### 1. GitHub Secrets Configuration
To deploy this via GitHub Actions, add these EXACT keys to your repository under **Settings > Secrets and variables > Actions**:

#### API Keys & URLs
- `GEMINI_API_KEY`: Your Google Gemini API Key
- `ELEVENLABS_API_KEY`: Your ElevenLabs API Key
- `PEXELS_API_KEY`: Your Pexels API Key
- `SUPABASE_URL`: Your Supabase Project URL
- `SUPABASE_KEY`: Your Supabase Service Key

#### Discord Webhooks (Organized)
- `WEBHOOK_LOGS` / `WEBHOOK_ERRORS` / `WEBHOOK_POSTS` / `WEBHOOK_INSIGHTS`

#### Google Drive Folder IDs
- `ROBLOX_FOLDER_ID` / `PARKOUR_FOLDER_ID` / `SFX_FOLDER_ID` / `GENERAL_BGM_FOLDER_ID` / `GAMING_BGM_FOLDER_ID`

#### Complex JSON Credentials (Store in root directory for local runs)
1. `CLIENT_SECRETS_JSON`
2. `DRIVE_TOKEN_JSON`
3. `YOUTUBE_TOKEN_JSON`
4. `TIKTOK_COOKIES_JSON`

*(To generate the last three JSON files, you can run `python tools/update_tokens.py` and `python tools/capture_tiktok_cookies.py` locally and then copy their content).*

## Database Note
If TikTok uploads fail due to an unhandled block or softban, `run_factory.py` queues it via Supabase to a `PENDING` status.
You can manually run `python tools/bulk_tiktok_poster.py` to auto-launch a visible browser and clear your backlog!
