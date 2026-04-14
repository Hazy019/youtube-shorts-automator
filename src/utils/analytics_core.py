import os
import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google import genai
from google.genai import types
from supabase import create_client, Client
from src.utils.discord import ping_error, ping_analytics_insight
from dotenv import load_dotenv

load_dotenv()

# Own Gemini client — Using high-volume fallback model for analytics stable runs
gemini_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
ANALYTICS_MODEL = "gemini-2.5-flash-lite"  # 500 RPD — high reliability for automated scripts

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]


def get_analytics_service():
    if not os.path.exists("token_youtube.json"):
        err = "token_youtube.json missing. Analytics loop aborted."
        print(err)
        ping_error(err, "Analytics Service")
        return None
    creds = Credentials.from_authorized_user_file("token_youtube.json", SCOPES)
    if not creds or not creds.valid:
        err = "YouTube Token invalid/expired. Run tools/update_tokens.py and update secrets."
        print(err)
        ping_error(err, "Analytics Service")
        return None
    try:
        return build("youtubeAnalytics", "v2", credentials=creds)
    except Exception as e:
        err = f"Failed to build YouTube Analytics service: {e}"
        print(err)
        ping_error(err, "Analytics Service")
        return None


def run_weekly_analytics():
    print("Starting Weekly Analytics Feedback Loop...")
    today      = datetime.datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")

    service = get_analytics_service()
    if not service:
        return

    try:
        resp = (
            supabase.table("videos")
            .select("id, youtube_id, topic")
            .is_("avg_view_pct", "null")
            .not_.is_("youtube_id", "null")
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
    except Exception as e:
        print(f"Supabase fetch error: {e}")
        return

    for video in resp.data:
        yt_id = video.get("youtube_id")
        if not yt_id:
            continue
        print(f"Metrics for: {video['topic']} ({yt_id})")
        try:
            result = service.reports().query(
                ids="channel==MINE",
                startDate=start_date,
                endDate=today,
                metrics="averageViewPercentage,averageViewDuration,views,likes,comments",
                dimensions="video",
                filters=f"video=={yt_id}",
            ).execute()

            if result.get("rows"):
                row = result["rows"][0]
                avg_pct, avg_dur, views, likes = row[0], row[1], row[2], row[3]
                print(f"  {avg_pct:.1f}% retention | {views} views | {likes} likes")
                supabase.table("videos").update({
                    "avg_view_pct": avg_pct,
                    "views_48h":    views,
                }).eq("id", video["id"]).execute()
            else:
                print(f"  No data yet (needs 48h).")
        except Exception as e:
            print(f"  Error for {yt_id}: {e}")

    try:
        top = supabase.table("videos").select("topic, views_48h, avg_view_pct") \
            .order("avg_view_pct", desc=True).limit(5).execute()
        low = supabase.table("videos").select("topic, views_48h, avg_view_pct") \
            .order("avg_view_pct", desc=False).limit(5).execute()

        prompt = (
            f"Analyze YouTube Shorts performance for Hazy Chanel.\n"
            f"TOP PERFORMERS: {top.data}\n"
            f"LOW PERFORMERS: {low.data}\n\n"
            "In 120 words: what hook/topic patterns drove high retention? "
            "What to avoid? Give one concrete script change for next week."
        )
        resp = gemini_client.models.generate_content(
            model=ANALYTICS_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.5),
        )
        insight = resp.text.strip()
        print(f"\nAI Insight:\n{insight}")
        ping_analytics_insight(insight)

    except Exception as e:
        err_msg = f"Analytics Insight generation failed: {e}"
        print(err_msg)
        ping_error(err_msg, "Analytics AI")

    print("\nWeekly Analytics Sync Complete!")


if __name__ == "__main__":
    run_weekly_analytics()