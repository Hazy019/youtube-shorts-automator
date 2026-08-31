                             ┌───────────────────────────────────┐
                             │  GitHub Actions (CI/CD Scheduler) │
                             │  Runs 2x Daily: 6:30 AM & 6:30 PM │
                             └─────────────────┬─────────────────┘
                                               │
                                               ▼
                              ┌──────────────────────────────────┐
                              │  run_factory.py (Control Plane)  │
                              └────────────────┬─────────────────┘
                                               │
                 ┌─────────────────────────────┼─────────────────────────────┐
                 │                             │                             │
                 ▼                             ▼                             ▼
    ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────────────┐
    │  1. AI Script Engine     │  │  2. Neural Voiceover     │  │  3. Smart Asset Sourcing │
    │  (src/ai/brain.py)       │  │  (src/ai/tts.py)         │  │  (src/media/assets.py)   │
    │  • Google Gemini 3 Flash │  │  • Microsoft Edge-TTS    │  │  • Pexels / Pixabay APIs │
    │  • Multi-Model Fallbacks │  │  • Nanosecond Timestamps │  │  • Fast FFmpeg Trimming  │
    │  • Anti-Slop Guidelines  │  │  • Channel Voice Pool    │  │  • S3 Fast Transfer      │
    └────────────┬─────────────┘  └────────────┬─────────────┘  └────────────┬─────────────┘
                 │                             │                             │
                 └─────────────────────────────┼─────────────────────────────┘
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │    4. Hybrid Rendering Engine     │
                             │       (src/media/builder.py)      │
                             │  ───────────────────────────────  │
                             │  [LOCAL MODE] Remotion CLI ($0)   │
                             │  [CLOUD MODE] AWS Lambda Parallel │
                             │  (React Remotion + OffthreadVideo)│
                             └─────────────────┬─────────────────┘
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │   5. Multi-Platform Syndication   │
                             ├───────────────────────────────────┤
                             │ • YouTube Data API (Auto-Schedule)│
                             │ • Meta Graph API (FB & IG Reels)  │
                             │ • TikTok Playwright Upload Queue  │
                             └─────────────────┬─────────────────┘
                                               │
                                               ▼
                             ┌───────────────────────────────────┐
                             │ 6. Closed-Loop Telemetry & Health │
                             ├───────────────────────────────────┤
                             │ • Discord Webhook Alerts          │
                             │ • Supabase Self-Healing State     │
                             │ • YouTube Analytics Feedback Loop │
                             └───────────────────────────────────┘