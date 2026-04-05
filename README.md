# Hazy Chanel Automator V5 🚀

Fully automated short-form video factory for YouTube Shorts and TikTok.

## Core Features
- **AI Brain (Gemini 1.5 Flash)**: Merged 3-in-1 generation for Topic, Script, and B-Roll Keywords.
- **Quota Optimized**: Uses only 2 Gemini calls per day (Gaming + General Facts).
- **Roblox & Parkour Routing**: Smart asset selection for gaming and universal facts.
- **Analytics Loop**: Weekly feedback loop to track views and retention (YouTube).
- **Self-Healing Auth**: Consolidated Google token refresh toolkit.

## Tech Stack
- **AI**: Google Gemini (1.5 Flash)
- **Voice**: ElevenLabs / Edge TTS Fallback
- **Storage**: AWS S3 & Google Drive
- **Render**: Remotion Lambda (AWS)
- **Database**: Supabase
- **Syndication**: YouTube Data API v3 & TikTok (via Playwright)

## Setup & Maintenance

### 1. GitHub Secrets Configuration
To deploy this via GitHub Actions, add these EXACT keys to your repository under **Settings > Secrets and variables > Actions**:

#### API Keys & URLs
- `GEMINI_API_KEY`: Your Google Gemini API Key
- `ELEVENLABS_API_KEY`: Your ElevenLabs API Key
- `PEXELS_API_KEY`: Your Pexels API Key
- `SUPABASE_URL`: Your Supabase Project URL
- `SUPABASE_KEY`: Your Supabase Service Key
- `DISCORD_WEBHOOK_URL`: Your Discord Webhook for alerts

#### AWS Remotion Lambda details
- `AWS_ACCESS_KEY_ID`: AWS Access Key
- `AWS_SECRET_ACCESS_KEY`: AWS Secret Key
- `BUCKET_NAME`: Remotion AWS S3 Bucket Name
- `SERVE_URL`: Webpack Serve URL

#### Google Drive Folder IDs
- `ROBLOX_FOLDER_ID`: Folder ID for gaming b-roll
- `PARKOUR_FOLDER_ID`: Folder ID for fallback/educational b-roll
- `SFX_FOLDER_ID`: Folder ID for sound effects
- `BGM_FOLDER_ID`: Folder ID for background music

#### Complex JSON Credentials
1. `CLIENT_SECRETS_JSON`: The raw JSON content of your Google Cloud `client_secrets.json`
2. `DRIVE_TOKEN_JSON`: The raw JSON content of your `token_drive.json`
3. `YOUTUBE_TOKEN_JSON`: The raw JSON content of your `token_youtube.json`
4. `TIKTOK_COOKIES_JSON`: The raw JSON content of your `tiktok_cookies.json`

*(To generate the last three JSON files, you can run `python tools/update_tokens.py` and `python tools/capture_tiktok_cookies.py` locally and then copy their content).*

### 3. Production Run
The factory runs automatically via GitHub Actions at 7 AM and 7 PM ET. To trigger manually:
```bash
python orchestrator.py
```

## Deleted Features
- **Instagram**: Removed to prioritize YouTube/TikTok and reduce account flag risks.
- **Minecraft**: All non-Roblox b-roll is now routed to the Parkour folder for higher retention.
- **Legacy Auth**: Multiple fragmented auth scripts replaced by `tools/update_tokens.py`.
