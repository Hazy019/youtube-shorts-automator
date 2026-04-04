# Hazy Chanel Automator

A fully automated production pipeline for generating fact and insight YouTube Shorts using AI, AWS Remotion, and Google Cloud APIs.

## Features
- **AI Brain**: Gemini Flash creates engaging, educational scripts and identifies visually appealing themes.
- **Dynamic Voiceover**: Generates professional voices through ElevenLabs with a built-in safety net fallback leveraging Microsoft Edge Neural TTS.
- **Professional Audio Layering**: Automatically fetches and syncs SFX and background music (BGM) for high-retention cinematic editing.
- **Smart B-Roll Engine**: Automatically syncs either user-uploaded background video from Google Drive (e.g., Roblox or Parkour clips) or fetches curated stock footage depending on the context of the script.
- **Double Shift Mode**: Automated multi-category production (Gaming + General Facts) in a single run.
- **Cloud Rendering**: Uses AWS Lambda + Remotion for instant, high-quality cloud video synthesis.
- **Automated YouTube Publish**: Directly integrates with the YouTube Data API with smart SEO tagging and categorization.

## Local Setup

### 1. Requirements
Ensure you are using Python 3.10+ and install all necessary dependencies:
```bash
pip install -r requirements.txt
```

### 2. Environment Variables (.env)
Create a `.env` file in the root directory containing the following:
```ini
GEMINI_API_KEY=your_gemini_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
ELEVENLABS_API_KEY=your_elevenlabs_key
PEXELS_API_KEY=your_pexels_key
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
DISCORD_WEBHOOK_URL=your_discord_webhook 
BGM_FOLDER_ID=your_bgm_folder_id 
ROBLOX_FOLDER_ID=your_roblox_folder_id
PARKOUR_FOLDER_ID=your_parkour_folder_id
SFX_FOLDER_ID=your_sfx_folder_id
```

### 3. Google API Authentication
This application uses Google Drive (to get background videos) and YouTube (to upload finished videos). You need a valid Google API project with OAuth credentials.
1. Download your `client_secrets.json` from the Google Cloud Console and place it in the root directory.
2. Run the authentication script locally:
```bash
python tools/update_tokens.py
```
3. A browser tab will open for Google Auth. After giving access, this tool generates two files: `token_drive.json` and `token_youtube.json`.

## Usage & Deployment

### Running Locally
To generate one video and upload it:
```bash
python orchestrator.py
```

### GitHub Actions (CI/CD)
This project is configured to run automatically once a day using GitHub Actions (`.github/workflows/factory.yml`). 

To make this work securely, you must configure **GitHub Repository Secrets**. Look inside the generated `token_drive.json` and `token_youtube.json` files and paste their exact JSON contents into the respective GitHub Secrets.

**Required GitHub Runtime Secrets:**
- `DRIVE_TOKEN_JSON`
- `YOUTUBE_TOKEN_JSON`
- `CLIENT_SECRETS_JSON`
- `GEMINI_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `ELEVENLABS_API_KEY`
- `PEXELS_API_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `DISCORD_WEBHOOK_URL` 

When setting up your automated pipeline, periodically run `tools/update_tokens.py` locally and update the Secrets if your refresh tokens expire.
