# Hazy Chanel Automator
**Professional Short-Form Video Factory for YouTube Shorts & TikTok**

Hazy Chanel Automator is a high-performance, automated video production pipeline designed for high-retention content (90-120s). It uses a **Hybrid Production Model** to combine the power of AWS Cloud rendering with the safety of local syndication.

---

## The Hybrid Production Model (v10)

To bypass platform restrictions (like datacenter IP blocking on TikTok), this system splits production into two distinct phases:

1.  **Phase 1: Cloud Production (`run_factory.py`)**
    -   **Intelligence**: Scripts generated via Gemini 1.5.
    -   **Audio**: High-fidelity narration via ElevenLabs.
    -   **Assembly**: Parallel rendering in **AWS Lambda** (Remotion).
    -   **YouTube**: Immediate upload to YouTube Shorts.
    -   **State**: The TikTok upload is queued in **Supabase** as `PENDING`.

2.  **Phase 2: Local Syndication (`tools/bulk_tiktok_poster.py`)**
    -   **Queue Management**: Drains the Supabase backlog.
    -   **Automation**: Launches a local browser session (Playwright) to upload videos.
    -   **Safety**: Allows for manual captcha solving in the window to ensure high success rates.

---

## Prerequisites

- **Python**: 3.10 or higher.
- **Node.js**: Required locally for Remotion rendering (if testing locally).
- **AWS CLI**: Configured with IAM credentials for Lambda/S3.
- **Supabase**: A project with `videos` and `used_clips` tables.
- **Playwright**: Run `playwright install chromium` after setting up.

---

## Setup & Installation

1.  **Clone & Install**
    ```powershell
    git clone https://github.com/Hazy019/youtube-shorts-automator.git
    cd youtube-shorts-automator
    pip install -r requirements.txt
    playwright install chromium
    ```

2.  **Configure `.env`**
    Create a `.env` file in the root directory and populate it with your secrets:

    | Key | Description |
    | :--- | :--- |
    | `GEMINI_API_KEY` | Google Gemini AI for script generation. |
    | `ELEVENLABS_API_KEY` | ElevenLabs for voice narration. |
    | `PEXELS_API_KEY` | B-roll video search. |
    | `AWS_ACCESS_KEY_ID` | IAM User for S3/Lambda access. |
    | `AWS_SECRET_ACCESS_KEY` | IAM Secret. |
    | `FUNCTION_NAME` | Your Remotion Lambda function name. |
    | `SUPABASE_URL` | Your Supabase project URL. |
    | `SUPABASE_KEY` | Your Supabase service_role or anon key. |
    | `DISCORD_WEBHOOK_URL` | Primary channel for production logs. |
    | `WEBHOOK_QUEUE` | (Optional) Dedicated channel for TikTok queue alerts. |

3.  **Google Cloud Authentication**
    - Place your `client_secrets.json` in the root.
    - Run `python tools/update_tokens.py` to generate `token_youtube.json` and `token_drive.json`.

---

## Operational Workflow

### 1. Generating Content
Run the factory orchestrator to start a production shift:
```powershell
python run_factory.py
```
This script validates your credits, checks the queue, and produces videos until your target count or API limits are reached.

### 2. Uploading to TikTok
When you are ready to process your backlog:
```powershell
python tools/bulk_tiktok_poster.py
```
- A browser will open.
- The script will automatically navigate to TikTok and start uploading.
- **Crucial**: If a "Got It" or "Captcha" popup appears, simply click it in the browser window.

---

## Maintenance & Troubleshooting

### TikTok Auth Issues
If you see "Invalid or Missing Cookies":
1.  Run `python tools/capture_tiktok_cookies.py`.
2.  Log in to TikTok in the browser window that appears.
3.  The script will automatically detect your `sessionid` and update `tiktok_cookies.json`.

### Asset Deduplication
The system uses "Semantic Deduplication." Every clip fetched from Pexels or Google Drive is logged in the Supabase `used_clips` table. The system will **never** use the same clip twice in the same niche until the entire asset pool is exhausted.

### Discord Notifications
Monitor your production via your Discord webhooks. You will receive:
- 🏗️ **Factory Start** alerts.
- ✅ **Production Complete** summaries (YouTube link included).
- 🏁 **Queue Fully Processed** alerts for TikTok.
- 🚨 **Emergency Alerts** with full tracebacks for any failures.

---

## Project Structure

- `src/ai/`: Brain (Gemini) and TTS (ElevenLabs) integration.
- `src/api/`: YouTube and TikTok API wrappers.
- `src/media/`: Video assembly and asset deduplication logic.
- `tools/`: Utility scripts for cookies, tokens, and bulk posting.
- `.env`: (Ignored) Local secrets and configuration.
