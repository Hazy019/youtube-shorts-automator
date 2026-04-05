import os
import datetime
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from supabase import create_client, Client
from discord_bot import ping_error, ping_analytics_insight
from dotenv import load_dotenv
from ai_brain import client as gemini_client


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]

def get_analytics_service():
    creds = None
    if os.path.exists('token_youtube.json'):

        creds = Credentials.from_authorized_user_file('token_youtube.json', SCOPES)
    
    if not creds or not creds.valid:
        print("Analytics Credentials invalid or missing scope. Run tools/update_tokens.py!")
        return None
        
    return build('youtubeAnalytics', 'v2', credentials=creds)

def run_weekly_analytics():
    print("Starting Weekly Analytics Feedback Loop...")
    

    today = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
    service = get_analytics_service()
    if not service:
        return


    try:
        videos_resp = supabase.table("videos")\
            .select("id, youtube_id, topic")\
            .is_("avg_view_pct", "null")\
            .not_("youtube_id", "is", "null")\
            .execute()
    except Exception as e:
        print(f"Supabase Fetch Error: {e}")
        return

    for video in videos_resp.data:
        yt_id = video.get('youtube_id')
        if not yt_id:
            continue
            
        print(f"Fetching metrics for: {video['topic']} ({yt_id})...")
        
        try:

            result = service.reports().query(
                ids="channel==MINE",
                startDate=start_date, 
                endDate=today,
                metrics="averageViewPercentage,averageViewDuration,views,likes,comments",
                dimensions="video",
                filters=f"video=={yt_id}"
            ).execute()
            
            if 'rows' in result and len(result['rows']) > 0:
                row = result['rows'][0]
                avg_view_pct = row[0]
                views = row[1]
                likes = row[2]
                
                print(f"Metrics Found: {avg_view_pct}% retention, {views} views.")
                # 2. Update Supabase
                update_data = {
                    "avg_view_pct": row[0],
                    "avg_view_dur": row[1],
                    "views_48h": row[2],
                    "like_rate": (row[3] / row[2]) if row[2] > 0 else 0
                }
                supabase.table("videos").update(update_data).eq("id", video['id']).execute()
            else:
                print(f"No analytics data found yet for {yt_id}. (May need 48h processing time)")

        except Exception as e:
            print(f"Error fetching analytics for {yt_id}: {e}")

    # --- AI Insight Generation ---
    try:
        # Fetch Top and Bottom performers to give context to Gemini
        top_perf = supabase.table("videos").select("topic, views_48h, avg_view_pct, avg_view_dur").order("avg_view_pct", desc=True).limit(5).execute()
        low_perf = supabase.table("videos").select("topic, views_48h, avg_view_pct, avg_view_dur").order("avg_view_pct", desc=False).limit(5).execute()
        
        insight_prompt = f"""
        Analyze the following YouTube Shorts performance data for the 'Hazy Chanel' factory.
        
        TOP PERFORMERS:
        {top_perf.data}
        
        LOW PERFORMERS:
        {low_perf.data}
        
        Based on this data, identify exactly what the AI should change in its scriptwriting or topic selection to improve retention and views. 
        Provide a concise, actionable summary (max 150 words) for the creator.
        Be specific about what themes or pacing worked best.
        """
        
        response = gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=insight_prompt
        )
        
        ai_insight = response.text.strip()
        print(f"AI Insight Generated: {ai_insight}")
        ping_analytics_insight(ai_insight)
        
    except Exception as e:
        print(f"Warning: Failed to generate AI insights: {e}")

    print("Weekly Analytics Sync Complete!")

if __name__ == "__main__":
    run_weekly_analytics()
