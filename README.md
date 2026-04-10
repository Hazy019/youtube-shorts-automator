# Hazy Chanel Automator
**Professional Short-Form Video Factory for YouTube Shorts (High-Concurrency Cloud Production)**

Hazy Chanel Automator is a state-of-the-art, fully automated video production pipeline. It integrates cutting-edge AI (Gemini, ElevenLabs) with cloud-scale rendering (AWS Lambda, Remotion) to produce high-retention (90–120s) YouTube Shorts and TikToks with zero human intervention.

> **See it in action**: [Hazy Chanel on YouTube](https://www.youtube.com/channel/UCize2SQoXPI6RFQYbIGemIg) — this channel is fully powered by this pipeline.

> **Privacy Notice**: This project requires API keys from multiple third-party services. Never expose your `.env` file or commit it to a public repository. Your `.env` is listed in `.gitignore` by default.

---

## The Hardened Cloud Pipeline (v11)

Version 11 represents a significant milestone in stability and performance. The system has been hardened against cloud-scale bottlenecks and API limitations:

### 1. Intelligent AI Brain (`src/ai/brain.py`)
- **Master Prompt Logic**: Uses a carefully crafted JSON-schema prompt to generate structured scripts with hooks, reveals, and CTAs — targeting 70%+ audience retention.
- **Model Resilience**: Automatically cycles through a prioritized list of Gemini models (`gemini-2.5-flash`, `gemini-2.5-flash-lite`, etc.). If one model is overloaded (503) or hits a quota limit (429), it waits with exponential backoff and retries before falling back to the next model.
- **Stable Pinning**: Uses only verified, high-quota model aliases so your pipeline does not break when Google updates their API.

### 2. Text-to-Speech (`src/ai/tts.py`)
- **Primary**: ElevenLabs neural voice for broadcast-quality narration.
- **Fallback**: Automatically switches to Microsoft Edge Neural TTS (free, local) if ElevenLabs is unavailable or over quota — so production never halts.

### 3. Advanced Multi-Tier B-roll Hierarchy (`src/media/assets.py`)
To prevent "missing asset" crashes, the system uses a 5-tier fallback search logic:
1. **Gaming Detection**: Topics matching "gaming," "Minecraft," "Roblox," etc. immediately pull curated parkour gameplay footage from your private Google Drive folder.
2. **Pexels Primary**: The AI-generated `b_roll_keyword` is sent to the Pexels API to find cinematic 4K/HD professional b-roll.
3. **Visual AI Backup**: If Pexels returns no results, Gemini generates an alternative visual keyword and retries.
4. **Categorized Fallbacks**: Broad keyword pools are tried for categories like `Science`, `Nature`, `History`, `Technology`, and `Space`.
5. **Emergency Buffer**: As a last resort, generalized high-retention parkour footage from Google Drive ensures the video always renders.

### 4. High-Concurrency AWS Assembly (`src/media/builder.py`)
Optimized for AWS accounts with high unreserved concurrency quotas (1000+):
- **Dynamic Chunking**: Automatically calculates `frames_per_lambda` (minimum 600 frames) to maximize render efficiency and prevent "stitcher" timeouts during assembly.
- **vCPU Awareness**: Maps `concurrency_per_lambda` to exactly 2 vCPUs (for 3008MB Lambda instances), preventing core over-subscription errors that cause immediate render failure.
- **Self-Healing**: Detects AWS "Rate Exceeded" or "Missing Chunks" errors and triggers an intelligent exponential-backoff retry with up to 4 automatic attempts.

---

## Prerequisites

Before getting started, ensure you have accounts and API keys for:

| Service | Purpose | Link |
| :--- | :--- | :--- |
| **Google AI Studio** | Gemini API for script generation | [aistudio.google.com](https://aistudio.google.com) |
| **ElevenLabs** | Premium neural text-to-speech | [elevenlabs.io](https://elevenlabs.io) |
| **Pexels** | Free stock footage API | [pexels.com/api](https://www.pexels.com/api/) |
| **AWS** | Lambda + S3 for cloud rendering | [aws.amazon.com](https://aws.amazon.com) |
| **Supabase** | Database for state and queue management | [supabase.com](https://supabase.com) |
| **Discord** | Webhook notifications | [discord.com/developers](https://discord.com/developers) |
| **Google Cloud** | YouTube Data API + Drive API | [console.cloud.google.com](https://console.cloud.google.com) |

You will also need:
- **Python 3.10+**
- **Node.js 18+** (for the Remotion cloud renderer)
- **AWS CLI** configured with IAM credentials that have S3 and Lambda permissions

---

## Setup & Installation

### Step 1 — Clone & Install Python Dependencies
```bash
git clone https://github.com/Hazy019/youtube-shorts-automator.git
cd youtube-shorts-automator
pip install -r requirements.txt
```

### Step 2 — Configure Environment Variables
Create a `.env` file in the project root. Copy the template below and fill in your own values:
```env
# ── AI Services ──────────────────────────────
GEMINI_API_KEY="your_gemini_api_key_here"
ELEVENLABS_API_KEY="your_elevenlabs_api_key_here"
PEXELS_API_KEY="your_pexels_api_key_here"

# ── AWS Rendering ─────────────────────────────
AWS_ACCESS_KEY_ID="your_aws_access_key_id"
AWS_SECRET_ACCESS_KEY="your_aws_secret_access_key"
BUCKET_NAME="your_remotion_lambda_s3_bucket_name"
SERVE_URL="https://your-bucket.s3.your-region.amazonaws.com/sites/your-site/index.html"
FUNCTION_NAME="your_deployed_remotion_function_name"

# ── Database ──────────────────────────────────
SUPABASE_URL="https://your-project-id.supabase.co"
SUPABASE_KEY="your_supabase_public_key"

# ── Google Drive Asset Folders ────────────────
# These are the Folder IDs from the Google Drive URL of each asset folder
PARKOUR_FOLDER_ID="your_google_drive_parkour_folder_id"
SFX_FOLDER_ID="your_sfx_folder_id"
BGM_FOLDER_ID="your_bgm_folder_id"
GAMING_BGM_FOLDER_ID="your_gaming_bgm_folder_id"
GENERAL_BGM_FOLDER_ID="your_general_bgm_folder_id"

# ── Discord Webhooks ──────────────────────────
# Create separate webhooks in your Discord server settings for each channel:
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
WEBHOOK_LOGS="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
WEBHOOK_ERRORS="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
WEBHOOK_POSTS="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
WEBHOOK_INSIGHTS="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"
WEBHOOK_QUEUE="https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN"

# ── Discord Ping ──────────────────────────────
# Enable Developer Mode in Discord, then right-click your username → Copy User ID
DISCORD_PING_USER_ID="your_discord_numeric_user_id"
```

> **Never share your `.env` file.** It contains private API keys that grant full access to your cloud account, database, and social media platforms. It is already listed in `.gitignore` — keep it that way.

### Step 3 — Authenticate Google APIs
Run the following to generate your OAuth tokens for YouTube and Google Drive:
```bash
python tools/update_tokens.py
```
This will open a browser window asking you to authorize both the YouTube Data API and the Google Drive API. Two token files will be saved locally:
- `token_youtube.json` — used for video uploads and engagement comments.
- `token_drive.json` — used to fetch b-roll and audio assets from your Drive folders.

> These token files contain private OAuth credentials. Do not commit them to version control.

### Step 4 — Deploy the Remotion Lambda Function
Follow the [Remotion Lambda Setup Guide](https://www.remotion.dev/docs/lambda) to deploy your render function to AWS. Once deployed, paste the function name and S3 serve URL into your `.env`.

---

## Operational Workflow

### Step 1: Run the Production Factory
```bash
python run_factory.py
```
- The bot will select a daily category (Gaming or General).
- It will sync b-roll (showing **transfer progress %** and **MB sizes**).
- It will initiate the AWS Lambda render (tracking **real-time % progress** in your console).
- It will upload to YouTube with an SEO-optimized title, description, and tags.
- It will automatically post and pin an engagement comment on the video.
- It will **ping you on Discord** when the full cycle is complete.
- The video's S3 link and TikTok caption are saved to Supabase as `PENDING`.

### Step 2: Post to TikTok (Local)
Because TikTok uploads require a real browser session and captcha solving, the pipeline queues videos in Supabase instead of uploading from the cloud. When you're ready to post:
```bash
python tools/bulk_tiktok_poster.py
```
- Drains all `PENDING` videos from the Supabase queue one by one.
- Opens a local browser session (with captcha support) to complete the upload.
- Upon success, marks each video as `SUCCESS` in Supabase.
- Sends a **"Video Posted to TikTok"** ping to your Discord `#factory-queue` channel for each video.
- Sends a final **"Queue Fully Processed"** summary when done.

---

## Maintenance & Features

### Real-Time Transparency
The factory provides full feedback during the "Syncing" phase. You will see exactly how much data is being transferred and the % progress of each clip being mirrored from Google Drive to S3.

### Self-Recovery
If AWS Lambda is busy or your account hits a burst limit, the bot will notify you in the console, wait for a 60-second cooldown, and retry the entire render automatically (up to 4 times with exponential backoff).

### Discord Notifications
Monitor your production pipeline entirely through Discord. You will receive:
- 🏗️ **Factory Start** alerts — so you know production has begun.
- ✅ **Production Complete** summaries with a **direct ping** to notify you.
- ✅ **Video Posted to TikTok** alerts from the bulk poster.
- 🚨 **Emergency Alerts** with full error tracebacks for any service failures.

---

## Project Structure

```
youtube-shorts-automator/
├── run_factory.py                  # Main orchestrator — run this to produce a video
├── src/
│   ├── ai/
│   │   ├── brain.py                # Gemini script generation with model failover
│   │   └── tts.py                  # ElevenLabs TTS + Microsoft Edge Neural TTS fallback
│   ├── api/
│   │   ├── youtube.py              # YouTube upload, engagement commenting & pinning
│   │   └── tiktok.py               # TikTok cookie auth + upload wrapper
│   ├── media/
│   │   ├── assets.py               # 5-tier B-roll hierarchy + Drive/S3/Pexels sync
│   │   └── builder.py              # AWS Lambda render orchestrator + dynamic chunking
│   └── utils/
│       └── discord.py              # All Discord notification webhook functions
├── tools/
│   ├── bulk_tiktok_poster.py       # Local TikTok queue drainer
│   ├── update_tokens.py            # Google OAuth token refresher
│   └── capture_tiktok_cookies.py   # TikTok browser session capture tool
├── hazy-remotion-cloud/            # React + Remotion video engine source code
├── .env                            # ⚠️ Your private secrets — NEVER commit this
├── .gitignore
└── requirements.txt
```

---

**Version 11 (Hardened Cloud Edition)** — *Solo Project by [Hazy Chanel](https://www.youtube.com/channel/UCize2SQoXPI6RFQYbIGemIg).*
