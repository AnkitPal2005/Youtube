"""
Phase 4 — Caption generation.

Runs OpenAI Whisper locally on the voiceover MP3 to get word-level timestamps,
then produces an .ass subtitle file styled for YouTube Shorts:
  - Bold, high-contrast text
  - 2-4 words per line (punchy, readable)
  - Centered lower-third position
  - White text with thick black outline
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

# Whisper calls ffmpeg internally — inject the winget install path if needed
_FFMPEG_BIN = (
    r"C:\Users\WottaCore - 01\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build\bin"
)
if Path(_FFMPEG_BIN).exists() and _FFMPEG_BIN not in os.environ.get("PATH", ""):
    os.environ["PATH"] = _FFMPEG_BIN + os.pathsep + os.environ.get("PATH", "")

OUTPUT_AUDIO_DIR = Path(__file__).parent.parent / "output" / "audio"
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def _load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _seconds_to_ass(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format H:MM:SS.cc"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _build_ass(groups: list[dict], config: dict) -> str:
    """
    Build a full .ass file string from word groups.
    Each group: {"text": "...", "start": float, "end": float}
    """
    cap_cfg = config.get("captions", {})
    font_size  = cap_cfg.get("font_size", 72)
    font_color = cap_cfg.get("font_color", "white")
    outline_w  = cap_cfg.get("outline_width", 3)

    # ASS colour format is &H00BBGGRR (alpha 00 = opaque)
    color_map = {
        "white":  "&H00FFFFFF",
        "yellow": "&H0000FFFF",
        "cyan":   "&H00FFFF00",
    }
    primary_color = color_map.get(font_color, "&H00FFFFFF")

    # Video is 1080x1920; place text in lower third (MarginV pushes up from bottom)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Shorts,Arial,{font_size},{primary_color},&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,{outline_w},0,2,60,60,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for g in groups:
        start = _seconds_to_ass(g["start"])
        end   = _seconds_to_ass(g["end"])
        text  = g["text"].strip().upper()
        lines.append(f"Dialogue: 0,{start},{end},Shorts,,0,0,0,,{text}")

    return header + "\n".join(lines) + "\n"


def _group_words(words: list[dict], words_per_line: int) -> list[dict]:
    """
    Chunk Whisper word-level segments into groups of N words.
    Each word dict has: {"word": str, "start": float, "end": float}
    """
    groups: list[dict] = []
    i = 0
    while i < len(words):
        chunk = words[i : i + words_per_line]
        text = " ".join(w["word"].strip() for w in chunk)
        groups.append({
            "text":  text,
            "start": chunk[0]["start"],
            "end":   chunk[-1]["end"],
        })
        i += words_per_line
    return groups


def generate_captions(audio_path: Path) -> Path:
    """
    Run Whisper on *audio_path* and write an .ass caption file.
    Returns the path to the .ass file.
    """
    import whisper

    config  = _load_config()
    cap_cfg = config.get("captions", {})
    words_per_line = cap_cfg.get("words_per_line", 3)

    run_id   = audio_path.stem
    ass_path = audio_path.parent / f"{run_id}.ass"

    print("  Loading Whisper model 'base' (downloads ~150 MB on first run)...")
    model = whisper.load_model("base")

    print(f"  Transcribing: {audio_path.name}")
    result = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en",
        fp16=False,          # fp16 off for CPU compatibility
    )

    # Flatten all word-level timestamps from all segments
    all_words: list[dict] = []
    for seg in result.get("segments", []):
        for w in seg.get("words", []):
            all_words.append({
                "word":  w["word"],
                "start": w["start"],
                "end":   w["end"],
            })

    if not all_words:
        raise RuntimeError(
            "Whisper returned no word-level timestamps. "
            "Try a longer audio file or check that the MP3 is not silent."
        )

    print(f"  {len(all_words)} words transcribed — grouping into {words_per_line}-word captions...")
    groups = _group_words(all_words, words_per_line)
    ass_content = _build_ass(groups, config)
    ass_path.write_text(ass_content, encoding="utf-8")

    print(f"  {len(groups)} caption lines written.")
    return ass_path
