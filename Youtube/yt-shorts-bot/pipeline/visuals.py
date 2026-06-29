"""
Phase 3 — Visuals sourcing.

Priority order:
  1. Pexels video API  (if PEXELS_API_KEY is set)
  2. Pexels photo API  (fallback within Pexels)
  3. Local gradient background generated with Pillow (no key needed)

All output goes to output/clips/<run_id>/.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

OUTPUT_CLIPS_DIR = Path(__file__).parent.parent / "output" / "clips"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"

GRADIENT_PALETTES = [
    [(15, 12, 41), (48, 43, 99), (36, 36, 62)],
    [(240, 98, 146), (255, 152, 0), (244, 67, 54)],
    [(0, 150, 136), (33, 150, 243), (63, 81, 181)],
    [(76, 175, 80), (139, 195, 74), (205, 220, 57)],
    [(63, 81, 181), (103, 58, 183), (233, 30, 99)],
    [(255, 87, 34), (255, 193, 7), (255, 235, 59)],
]

_FFMPEG_WINGET = (
    r"C:\Users\WottaCore - 01\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
)


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    if Path(_FFMPEG_WINGET).exists():
        return _FFMPEG_WINGET
    raise RuntimeError(
        "ffmpeg not found. Install it with: winget install Gyan.FFmpeg\n"
        "Then restart your terminal."
    )


def _load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


# ---------------------------------------------------------------------------
# Pexels helpers
# ---------------------------------------------------------------------------

def _pexels_headers() -> dict:
    return {"Authorization": os.environ.get("PEXELS_API_KEY", "")}


def _search_pexels_video(keyword: str, session: Any) -> str | None:
    try:
        resp = session.get(
            PEXELS_VIDEO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "orientation": "portrait", "per_page": 8, "size": "medium"},
            timeout=15,
        )
        resp.raise_for_status()
        for video in resp.json().get("videos", []):
            for vf in video.get("video_files", []):
                if vf.get("quality") in ("hd", "sd") and vf.get("height", 0) >= 720:
                    return vf["link"]
    except Exception as exc:
        print(f"    Pexels video error for '{keyword}': {exc}", file=sys.stderr)
    return None


def _search_pexels_photo(keyword: str, session: Any) -> str | None:
    try:
        resp = session.get(
            PEXELS_PHOTO_URL,
            headers=_pexels_headers(),
            params={"query": keyword, "orientation": "portrait", "per_page": 5},
            timeout=15,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if photos:
            return photos[0]["src"]["large2x"]
    except Exception as exc:
        print(f"    Pexels photo error for '{keyword}': {exc}", file=sys.stderr)
    return None


def _download(url: str, dest: Path, session: Any) -> bool:
    try:
        with session.get(url, stream=True, timeout=90) as r:
            r.raise_for_status()
            dest.write_bytes(r.content)
        return True
    except Exception as exc:
        print(f"    Download failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Photo → video conversion (Ken Burns zoom effect)
# ---------------------------------------------------------------------------

def _photo_to_video(photo_path: Path, duration: float) -> Path:
    """Convert a still image to an MP4 with a slow Ken Burns zoom."""
    ffmpeg = _find_ffmpeg()
    out = photo_path.with_suffix(".mp4")
    frames = max(1, int(duration * 30))
    cmd = [
        ffmpeg, "-y",
        "-loop", "1", "-i", str(photo_path),
        "-vf", (
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,"
            f"zoompan=z='min(zoom+0.0003,1.05)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s=1080x1920:fps=30"
        ),
        "-t", str(duration),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out),
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    photo_path.unlink(missing_ok=True)
    return out


# ---------------------------------------------------------------------------
# Gradient fallback
# ---------------------------------------------------------------------------

def _gradient_png(out_path: Path, palette_index: int) -> Path:
    from PIL import Image

    W, H = 1080, 1920
    palette = GRADIENT_PALETTES[palette_index % len(GRADIENT_PALETTES)]
    img = Image.new("RGB", (W, H))
    pixels = img.load()
    stops = len(palette)
    for y in range(H):
        t = y / (H - 1) * (stops - 1)
        lo = int(t)
        hi = min(lo + 1, stops - 1)
        frac = t - lo
        r = int(palette[lo][0] * (1 - frac) + palette[hi][0] * frac)
        g = int(palette[lo][1] * (1 - frac) + palette[hi][1] * frac)
        b = int(palette[lo][2] * (1 - frac) + palette[hi][2] * frac)
        for x in range(W):
            pixels[x, y] = (r, g, b)
    img.save(str(out_path))
    return out_path


def _gradient_video(out_path: Path, duration: float, palette_index: int) -> Path:
    png = out_path.with_suffix(".png")
    _gradient_png(png, palette_index)
    result = _photo_to_video(png, duration)
    if result != out_path:
        result.rename(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def fetch_visuals(script_path: Path, voiceover_duration: float = 35.0) -> list[Path]:
    """
    Download/generate visual assets for the script.
    Returns a list of local MP4 paths ready for Phase 5.
    """
    import requests as req

    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    keywords: list[str] = script_data.get("visual_keywords", [])
    if not keywords:
        raise ValueError("Script JSON has no 'visual_keywords' field.")

    run_id = script_path.stem
    out_dir = OUTPUT_CLIPS_DIR / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    clip_duration = voiceover_duration / len(keywords)
    collected: list[Path] = []

    if pexels_key:
        print(f"  Pexels key found — fetching stock footage for {len(keywords)} keywords...")
        session = req.Session()

        for i, keyword in enumerate(keywords):
            print(f"  [{i+1}/{len(keywords)}] '{keyword}'")

            # 1. Try Pexels video
            url = _search_pexels_video(keyword, session)
            if url:
                dest = out_dir / f"{i:02d}_{keyword.replace(' ', '_')}.mp4"
                if _download(url, dest, session):
                    print(f"    Video clip saved: {dest.name}")
                    collected.append(dest)
                    time.sleep(0.3)
                    continue

            # 2. Try Pexels photo → convert to video
            url = _search_pexels_photo(keyword, session)
            if url:
                photo_dest = out_dir / f"{i:02d}_{keyword.replace(' ', '_')}.jpg"
                if _download(url, photo_dest, session):
                    print(f"    Photo downloaded, converting to video...")
                    vid = _photo_to_video(photo_dest, clip_duration)
                    print(f"    Video created: {vid.name}")
                    collected.append(vid)
                    time.sleep(0.3)
                    continue

            # 3. Gradient fallback
            print(f"    No Pexels result — using gradient fallback.")
            grad = out_dir / f"{i:02d}_gradient.mp4"
            _gradient_video(grad, clip_duration, i)
            collected.append(grad)

    else:
        print("  No PEXELS_API_KEY — generating gradient backgrounds.")
        print("  Get a free key at https://www.pexels.com/api/ for real stock footage.\n")
        for i, keyword in enumerate(keywords):
            print(f"  [{i+1}/{len(keywords)}] Gradient for: '{keyword}'")
            grad = out_dir / f"{i:02d}_gradient_{keyword.replace(' ', '_')}.mp4"
            _gradient_video(grad, clip_duration, i)
            collected.append(grad)

    if not collected:
        raise RuntimeError("No visuals collected. Check Pexels key or network.")

    print(f"\n  {len(collected)} clip(s) saved to: {out_dir}")
    return collected
