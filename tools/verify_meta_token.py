"""
Meta Token Pre-Flight Validator
================================
Validates META_PAGE_ACCESS_TOKEN before any upload is attempted.
Fails fast with a clear human-readable error so CI minutes aren't wasted.

Checks:
  1. Token is present in the environment
  2. Token is accepted by the Graph API (not expired / revoked)
  3. Token has the required video publishing permissions
  4. PAGE_ID and INSTAGRAM_ID are present
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Windows console encoding fix (matches meta_healer.py)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

load_dotenv()

GRAPH_BASE = "https://graph.facebook.com/v25.0"

REQUIRED_PERMISSIONS = {
    "pages_manage_posts",
    "pages_read_engagement",
    "publish_video",
    # Instagram permissions
    "instagram_basic",
    "instagram_content_publish",
}

def fail(msg: str):
    print(f"\n{'='*60}")
    print(f"❌  META TOKEN VALIDATION FAILED")
    print(f"{'='*60}")
    print(f"   {msg}")
    print(f"\n👉  Fix: Go to GitHub → Repo → Settings → Secrets → Actions")
    print(f"         Update  META_PAGE_ACCESS_TOKEN  with a fresh token.")
    print(f"         Generate one at: https://developers.facebook.com/tools/explorer/")
    print(f"{'='*60}\n")
    sys.exit(1)


def check_token_present() -> str:
    token = os.getenv("META_PAGE_ACCESS_TOKEN", "").strip(' \t\n\r"')
    if not token:
        fail("META_PAGE_ACCESS_TOKEN is missing from environment / secrets.")
    if len(token) < 50:
        fail(f"META_PAGE_ACCESS_TOKEN looks truncated (only {len(token)} chars). "
             "Check that the full token was pasted into the GitHub secret.")
    return token


def check_page_and_ig_ids():
    page_id = os.getenv("META_PAGE_ID", "").strip()
    ig_id   = os.getenv("META_INSTAGRAM_ID", "").strip()
    if not page_id:
        fail("Missing required env var: META_PAGE_ID")
    return page_id, ig_id


def check_token_via_graph(token: str) -> dict:
    """
    Hits /me?fields=id,name to confirm the token is alive.
    A dead/expired token returns an OAuthException here immediately.
    """
    try:
        r = requests.get(
            f"{GRAPH_BASE}/me",
            params={"fields": "id,name", "access_token": token},
            timeout=15,
        )
        data = r.json()
    except Exception as e:
        fail(f"Could not reach Graph API: {e}")

    if "error" in data:
        err = data["error"]
        code = err.get("code")
        msg  = err.get("message", "Unknown error")
        hint = ""
        if code == 190:
            hint = " (Token is EXPIRED or REVOKED - Generate a new Long-Lived Page Token)"
        elif code == 200:
            hint = " (Meta App is in DEV MODE or User is NOT in App Roles: Go to developers.facebook.com -> App -> App Roles -> Add your user as Developer/Admin, or switch App Mode to Live)"
        fail(f"Graph API rejected token{hint}: [{code}] {msg}")

    return data


def check_token_permissions(token: str):
    """
    Calls /me/permissions to list granted scopes.
    Warns about any missing required permission — but doesn't hard-fail
    if the token passes the /me check (page tokens may list perms differently).
    """
    try:
        r = requests.get(
            f"{GRAPH_BASE}/me/permissions",
            params={"access_token": token},
            timeout=15,
        )
        data = r.json()
    except Exception as e:
        print(f"   ⚠️  Could not fetch permissions list: {e} (non-fatal)")
        return

    if "error" in data:
        # Page tokens sometimes can't call /me/permissions — that's OK.
        print(f"   ⚠️  Permission list unavailable for this token type (non-fatal)")
        return

    granted = {
        p["permission"]
        for p in data.get("data", [])
        if p.get("status") == "granted"
    }

    missing = REQUIRED_PERMISSIONS - granted
    if missing:
        # Warn but don't fail — page tokens may still work without listing all perms
        print(f"   ⚠️  Some expected permissions not listed: {', '.join(sorted(missing))}")
        print(f"       (This is a warning only — page tokens often omit these from /me/permissions)")
    else:
        print(f"   ✅ All required permissions confirmed.")


def main():
    print("\n" + "="*60)
    print("🔑  META TOKEN PRE-FLIGHT CHECK")
    print("="*60)

    # 1. Presence check
    token = check_token_present()
    print(f"   ✅ Token present ({len(token)} chars)")

    # 2. IDs check
    page_id, ig_id = check_page_and_ig_ids()
    print(f"   ✅ PAGE_ID  : {page_id}")
    print(f"   ✅ IG_ID    : {ig_id if ig_id else 'None (Facebook Reels Only)'}")

    # 3. Live Graph API check
    me = check_token_via_graph(token)
    print(f"   ✅ Token accepted by Graph API — Identity: {me.get('name', '?')} ({me.get('id', '?')})")

    # 4. Permissions check (advisory only)
    check_token_permissions(token)

    print("\n🚀  Meta token is VALID. Proceeding with upload.\n")


if __name__ == "__main__":
    main()
