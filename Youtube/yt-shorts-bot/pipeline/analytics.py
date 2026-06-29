"""
Phase 7 — Analytics & upload history.

- report : show all uploaded videos with IDs, URLs, dates
- refresh : pull latest view/like counts from YouTube API
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"
POST_LOG = DATA_DIR / "post_log.json"


def _load_log() -> list[dict]:
    if not POST_LOG.exists():
        return []
    try:
        return json.loads(POST_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_log(log: list[dict]) -> None:
    POST_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")


def show_report() -> None:
    """Print all uploaded videos in a clean table."""
    log = _load_log()

    if not log:
        print("  No uploads yet. Run: python main.py upload ...")
        return

    print(f"\n{'='*65}")
    print(f"  UPLOAD HISTORY  ({len(log)} video{'s' if len(log) != 1 else ''})")
    print(f"{'='*65}")

    for i, entry in enumerate(reversed(log), 1):
        uploaded = entry.get("uploaded_at", "")
        try:
            dt = datetime.fromisoformat(uploaded).astimezone()
            date_str = dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            date_str = uploaded[:16]

        vid_id = entry.get("video_id", "unknown")
        title  = entry.get("title", "Untitled")[:45]
        views  = entry.get("views")
        likes  = entry.get("likes")

        print(f"\n  [{i}] {title}")
        print(f"      ID      : {vid_id}")
        print(f"      URL     : https://youtube.com/shorts/{vid_id}")
        print(f"      Date    : {date_str}")
        if entry.get("publish_at"):
            print(f"      Publish : {entry['publish_at']}")
        if views is not None:
            print(f"      Views   : {views:,}  |  Likes: {likes or 0:,}")
        else:
            print(f"      Stats   : Not fetched yet (run: python main.py refresh-stats)")

    print(f"\n{'='*65}\n")


def refresh_stats() -> None:
    """Pull latest view/like counts from YouTube API and update post_log.json."""
    log = _load_log()
    if not log:
        print("  No uploads in log.")
        return

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        token_file = DATA_DIR / "token.json"
        if not token_file.exists():
            print("  ERROR: Not authenticated. Run upload first to set up token.")
            return

        creds = Credentials.from_authorized_user_file(str(token_file))
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        youtube = build("youtube", "v3", credentials=creds)

        video_ids = [e["video_id"] for e in log if e.get("video_id")]
        if not video_ids:
            print("  No video IDs found in log.")
            return

        # YouTube API allows up to 50 IDs per request
        for chunk_start in range(0, len(video_ids), 50):
            chunk = video_ids[chunk_start:chunk_start + 50]
            resp = youtube.videos().list(
                part="statistics",
                id=",".join(chunk),
            ).execute()

            stats_map = {
                item["id"]: item.get("statistics", {})
                for item in resp.get("items", [])
            }

            for entry in log:
                vid_id = entry.get("video_id")
                if vid_id in stats_map:
                    s = stats_map[vid_id]
                    entry["views"] = int(s.get("viewCount", 0))
                    entry["likes"] = int(s.get("likeCount", 0))
                    print(f"  {vid_id} — Views: {entry['views']:,} | Likes: {entry['likes']:,}")

        _save_log(log)
        print(f"\n  Stats updated in: {POST_LOG}")

    except Exception as exc:
        print(f"  ERROR fetching stats: {exc}")
