import sys
import os

# Force console output to UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.media.assets import get_background_videos

class MockSync:
    def __init__(self):
        self.called_with = None
    
    def sync_mock(self, folder_id, needed, media_type):
        self.called_with = folder_id
        return ["drive_clip_1.mp4", "drive_clip_2.mp4"]

def test_detection():
    import src.media.assets as assets
    mock = MockSync()
    
    # Temporarily monkeypatch sync_drive_to_s3 to see where it routes
    original_sync = assets.sync_drive_to_s3
    assets.sync_drive_to_s3 = mock.sync_mock
    
    # Temporarily monkeypatch _fetch_pexels to return empty (so it triggers Route 4)
    original_fetch = assets._fetch_pexels
    assets._fetch_pexels = lambda kw, n: []

    test_cases = [
        ("The quantum physics of black holes...", "SCIENCE"),
        ("Ancient Egyptian archaeology found...", "HISTORY"),
        ("The biology of cellular evolution...", "SCIENCE"),
        ("Medieval kings and ruins in Europe...", "HISTORY"),
        ("New telescope discovered a supernova...", "SCIENCE"),
        ("The fall of the Roman Empire...", "HISTORY"),
    ]

    print("Testing Keyword Detection & Routing...")
    
    for topic, expected in test_cases:
        mock.called_with = None
        # Primary keyword doesn't matter since we mocked pexels to return []
        assets.get_background_videos(topic, "test_kw", num_clips=2)
        
        target_id = os.getenv(f"{expected}_BROLL_FOLDER_ID")
        
        if mock.called_with == target_id:
            print(f"✅ PASS: Topic '{topic[:30]}...' routed to {expected}")
        else:
            print(f"❌ FAIL: Topic '{topic[:30]}...' routed to {mock.called_with} (Expected {expected})")

    # Restore
    assets.sync_drive_to_s3 = original_sync
    assets._fetch_pexels = original_fetch

if __name__ == "__main__":
    # Ensure env vars are loaded for IDs
    from dotenv import load_dotenv
    load_dotenv()
    test_detection()
