import sys
import os

# Ensure the root directory is on the path so 'src' can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.utils.analytics_core import run_weekly_analytics

if __name__ == "__main__":
    run_weekly_analytics()
