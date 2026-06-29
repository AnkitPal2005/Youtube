"""
Phase 2 — Voiceover generation.

Converts the script text to a natural-sounding MP3 using edge-tts
(Microsoft Edge TTS — completely free, no API key required).
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

OUTPUT_AUDIO_DIR = Path(__file__).parent.parent / "output" / "audio"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


_FFPROBE_CANDIDATES = [
    "ffprobe",
    r"C:\Users\WottaCore - 01\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.2-full_build\bin\ffprobe.exe",
]


def _find_ffprobe() -> str | None:
    import shutil
    for candidate in _FFPROBE_CANDIDATES:
        found = shutil.which(candidate) or (Path(candidate).exists() and candidate)
        if found:
            return found
    return None


def _get_audio_duration(mp3_path: Path) -> float:
    """Return duration in seconds using ffprobe."""
    ffprobe = _find_ffprobe()
    if not ffprobe:
        return 0.0
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(mp3_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


async def _synthesize(text: str, voice: str, rate: str, volume: str, out_path: Path) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
    await communicate.save(str(out_path))


def generate_voiceover(script_path: Path) -> tuple[Path, float]:
    """
    Generate a voiceover MP3 from a script JSON file.

    Returns (mp3_path, duration_seconds).
    """
    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    script_text = script_data.get("script", "")
    if not script_text:
        raise ValueError(f"Script JSON at {script_path} has no 'script' field.")

    config = _load_config()
    voice_cfg = config.get("voice", {})
    voice = voice_cfg.get("name", "en-IN-NeerjaNeural")
    rate = voice_cfg.get("rate", "+0%")
    volume = voice_cfg.get("volume", "+0%")

    run_id = script_path.stem
    OUTPUT_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_AUDIO_DIR / f"{run_id}.mp3"

    print(f"  Voice : {voice}")
    print(f"  Rate  : {rate}  |  Volume: {volume}")
    print(f"  Text  : {script_text[:80]}{'...' if len(script_text) > 80 else ''}")

    asyncio.run(_synthesize(script_text, voice, rate, volume, out_path))

    duration = _get_audio_duration(out_path)
    if duration > 0:
        print(f"  Duration: {duration:.1f}s")
        if duration > 60:
            print(
                f"  WARNING: audio is {duration:.1f}s — over YouTube Shorts 60s limit!",
                file=sys.stderr,
            )
    else:
        print("  Duration: unknown (ffprobe not found or not in PATH)")

    return out_path, duration
