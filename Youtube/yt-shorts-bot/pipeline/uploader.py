"""
Phase 6 — YouTube upload.

Uses YouTube Data API v3 with OAuth2 (one-time browser auth, token cached).

IMPORTANT NOTE ON VISIBILITY:
  Uploads from a fresh / unaudited Google Cloud project are locked to
  "private" by the YouTube API quota system until your project passes
  YouTube's API Compliance Audit. This is normal — your video IS uploaded,
  it just won't be publicly visible until the audit passes (usually 1-3 days
  after submitting). This script will clearly tell you which state the upload
  is in so nothing fails silently.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DATA_DIR      = Path(__file__).parent.parent / "data"
TOKEN_FILE    = DATA_DIR / "token.json"
POST_LOG      = DATA_DIR / "post_log.json"
PROJECT_ROOT  = Path(__file__).parent.parent

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]

# YouTube API chunk size for resumable upload (256 KB minimum, multiple of 256 KB)
CHUNK_SIZE = 1024 * 1024  # 1 MB


def _get_client_secret_path() -> Path:
    name = os.environ.get("YOUTUBE_CLIENT_SECRET_FILE", "client_secret.json")
    path = PROJECT_ROOT / name
    if not path.exists():
        raise FileNotFoundError(
            f"client_secret.json not found at: {path}\n\n"
            "To set up YouTube upload:\n"
            "  1. Go to https://console.cloud.google.com/\n"
            "  2. Create a project → Enable 'YouTube Data API v3'\n"
            "  3. APIs & Services → Credentials → Create → OAuth 2.0 Client ID\n"
            "     Application type: Desktop App\n"
            "  4. Download JSON → rename to client_secret.json\n"
            "  5. Place it in: " + str(PROJECT_ROOT)
        )
    return path


def _get_authenticated_service() -> Any:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load cached token
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    # Refresh or re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing access token...")
            creds.refresh(Request())
        else:
            print("  Opening browser for YouTube authentication...")
            print("  (This only happens once — token will be cached)")
            secret_path = _get_client_secret_path()
            flow = InstalledAppFlow.from_client_secrets_file(str(secret_path), SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        # Cache the token
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print(f"  Token cached at: {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def _load_script_meta(script_path: Path) -> dict:
    data = json.loads(script_path.read_text(encoding="utf-8"))
    title = data.get("title", "")
    # Ensure #Shorts is in title
    if "#Shorts" not in title and "#shorts" not in title:
        title = title.rstrip() + " #Shorts"
    # YouTube title max 100 chars
    title = title[:100]

    desc = data.get("description", "")
    if "#Shorts" not in desc:
        desc = desc + "\n\n#Shorts"

    tags = data.get("tags", [])
    if "Shorts" not in tags:
        tags.append("Shorts")

    return {"title": title, "description": desc, "tags": tags}


def upload_video(
    video_path: Path,
    script_path: Path | None = None,
    publish_at: str = "",
    title: str = "",
    description: str = "",
    tags: list[str] | None = None,
) -> str:
    """
    Upload *video_path* to YouTube.

    Args:
        video_path:  Path to the MP4 file.
        script_path: Optional path to script JSON — pulls title/desc/tags from it.
        publish_at:  ISO-8601 datetime string for scheduled publish
                     e.g. "2026-06-30T18:30:00+05:30"
                     Leave empty to upload as private immediately.
        title:       Override title (ignored if script_path provided).
        description: Override description.
        tags:        Override tags list.

    Returns:
        YouTube video ID of the uploaded video.
    """
    from googleapiclient.http import MediaFileUpload

    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Pull metadata from script JSON if available
    if script_path and script_path.exists():
        meta = _load_script_meta(script_path)
        title       = title or meta["title"]
        description = description or meta["description"]
        tags        = tags or meta["tags"]
    else:
        title = title or video_path.stem
        tags  = tags or ["Shorts"]

    # Determine privacy status
    if publish_at:
        # Scheduled → must be private initially with publishAt set
        privacy_status = "private"
        try:
            # Validate the datetime string
            datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(
                f"Invalid publish_at format: '{publish_at}'\n"
                "Use ISO-8601: e.g. '2026-06-30T18:30:00+05:30'"
            )
    else:
        privacy_status = "private"  # safe default until API audit passes

    print(f"\n  Title      : {title}")
    print(f"  Privacy    : {privacy_status}" +
          (f"  (publishes at {publish_at})" if publish_at else ""))
    print(f"  Tags       : {', '.join(tags[:5])}{'...' if len(tags) > 5 else ''}")
    print(f"  File size  : {video_path.stat().st_size // (1024*1024)} MB")

    youtube = _get_authenticated_service()

    body: dict[str, Any] = {
        "snippet": {
            "title":       title,
            "description": description,
            "tags":        tags,
            "categoryId":  "28",   # Science & Technology (change if needed)
        },
        "status": {
            "privacyStatus":           privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    if publish_at:
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        chunksize=CHUNK_SIZE,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print("\n  Uploading", end="", flush=True)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"\r  Uploading  {pct}%", end="", flush=True)
    print(f"\r  Uploading  100% — done!")

    video_id  = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"

    print(f"\n  Video ID   : {video_id}")
    print(f"  Video URL  : {video_url}")

    # ── Visibility notice ──────────────────────────────────────────────────
    print("\n" + "="*60)
    print("  IMPORTANT — READ THIS:")
    print("  Your video has been uploaded successfully.")
    print(f"  Current status: PRIVATE")
    if publish_at:
        print(f"  Scheduled to go public at: {publish_at}")
        print("  NOTE: Scheduled publishing only works after your Google Cloud")
        print("  project passes YouTube's API Compliance Audit.")
    else:
        print("  To make it public: go to YouTube Studio → Content")
        print("  → click the video → change visibility to 'Public'.")
    print("  Fresh API projects are restricted until the audit passes")
    print("  (submit at: https://support.google.com/youtube/contact/yt_api_form)")
    print("="*60)

    # ── Log to post_log.json ───────────────────────────────────────────────
    _log_upload(video_id, video_url, video_path, title, publish_at)

    return video_id


def _log_upload(video_id: str, url: str, video_path: Path, title: str, publish_at: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log: list = []
    if POST_LOG.exists():
        try:
            log = json.loads(POST_LOG.read_text(encoding="utf-8"))
        except Exception:
            log = []

    log.append({
        "video_id":   video_id,
        "url":        url,
        "title":      title,
        "file":       str(video_path),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "publish_at": publish_at or None,
        "views":      None,
        "likes":      None,
    })
    POST_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Logged to  : {POST_LOG}")
