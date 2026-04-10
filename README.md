# Hazy Chanel Automator
**Professional Short-Form Video Factory for YouTube Shorts (High Concurrency Cloud)**

Hazy Chanel Automator is a high-performance, automated video production pipeline designed for high-retention content (90-120s). The system is currently optimized for **YouTube Shorts Cloud Production** with extreme stability and parallel rendering.

---

## The hardened Cloud Pipeline (v11)

To ensure maximum reliability and speed, the system has been hardened against cloud-scale bottlenecks:

1.  **Single-Shift Production (`run_factory.py`)**
    -   Produces ONE high-quality short per run (category: gaming or general).
    -   **Intelligence**: High-retention scripts via Gemini 1.5.
    -   **Visuals**: Smart B-roll syncing with real-time progress bars (transfer from Drive → S3).
    -   **Stability**: Exponential backoff retries on all network calls to prevent transient failures.

2.  **High-Parallel AWS Assembly (`src/media/builder.py`)**
    -   **Concurrency-Aware**: Configured specifically for high AWS Concurrency Quotas (1001+ nodes).
    -   **Fast Stitching**: Uses optimized `frames_per_lambda` (60-120) and `concurrency_per_lambda` (2-8) to render 90s videos in parallel chunks.
    -   **Self-Healing**: Automatically detects AWS "Rate Exceeded" or "Concurrency Limit" errors and triggers a cooldown-backoff retry.

3.  **Automated YouTube Syndication**
    -   Immediate upload to YouTube Shorts with SEO-optimized titles, descriptions, and tags.
    -   State logging to Supabase with YouTube Video IDs.

---

## Prerequisites

- **Python**: 3.10 or higher.
- **AWS CLI**: IAM credentials for Lambda/S3.
- **AWS Quota**: 1000+ Unreserved Concurrency (Recommended for peak performance).
- **Supabase**: A project with `videos` and `used_clips` tables.
- **Google Cloud**: `client_secrets.json` for YouTube/Drive APIs.

---

## Setup & Installation

1.  **Clone & Install**
    ```powershell
    git clone https://github.com/Hazy019/youtube-shorts-automator.git
    cd youtube-shorts-automator
    pip install -r requirements.txt
    ```

2.  **Configure `.env`**
    Ensure these keys are present:
    `GEMINI_API_KEY`, `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `FUNCTION_NAME`, `SUPABASE_URL`, `SUPABASE_KEY`, `DISCORD_WEBHOOK_URL`.

3.  **Google Cloud Authentication**
    Run `python tools/update_tokens.py` to generate `token_youtube.json` and `token_drive.json`.

---

## Operational Workflow

### Run the Factory
```powershell
python run_factory.py
```
-   The bot will select a category.
-   It will sync b-roll (showing **transfer progress %** and **MB sizes**).
-   It will initiate the AWS Lambda render (tracking progress in real-time).
-   It will upload to YouTube and **ping you on Discord** when complete.

---

## Maintenance & Features

### Real-Time Transparency
The factory now provides full feedback during the "Syncing" phase. You will see exactly how much data is being transferred and the % progress of each clip being mirrored from Google Drive to S3.

### Self-Recovery
If AWS Lambda is busy or your account hits a burst limit, the bot will notify you in the console, wait for a 60-second cooldown, and retry the entire render automatically.

### Discord Notifications
Monitor your production via your Discord webhooks. You will receive:
- 🏗️ **Factory Start** alerts.
- ✅ **Production Complete** summaries with a **Literal Ping** to notify you.
- 🚨 **Emergency Alerts** with full tracebacks for any service failures.

---

---

## Project Structure

- `src/ai/`: Brain (Gemini) and TTS (ElevenLabs) integration.
- `src/api/`: YouTube and TikTok API wrappers.
- `src/media/`: Video assembly and asset deduplication logic.
- `tools/`: Utility scripts for cookies, tokens, and bulk posting.
- `.env`: (Ignored) Local secrets and configuration.
