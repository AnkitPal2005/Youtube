"""
Phase 5 — Video assembly.

Combines:
  - Background video clips (output/clips/<id>/)
  - Voiceover MP3       (output/audio/<id>.mp3)
  - ASS caption file    (output/audio/<id>.ass)
  - Background music    (assets/music/<id>_<mood>.mp3)

Output: 1080x1920 vertical H.264 MP4, 30fps, under 60s
        → output/final/<id>.mp4

Two-pass ffmpeg approach:
  Pass 1 — concatenate/scale clips + mix audio
  Pass 2 — burn-in ASS captions (separate pass avoids Windows path escaping issues)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()

OUTPUT_FINAL = Path(__file__).parent.parent / "output" / "final"
OUTPUT_CLIPS = Path(__file__).parent.parent / "output" / "clips"
OUTPUT_AUDIO = Path(__file__).parent.parent / "output" / "audio"
ASSETS_MUSIC = Path(__file__).parent.parent / "assets" / "music"
CONFIG_PATH  = Path(__file__).parent.parent / "config.yaml"
PROJECT_ROOT = Path(__file__).parent.parent

_FFMPEG_WINGET  = (
    r"C:\Users\WottaCore - 01\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
)
_FFPROBE_WINGET = _FFMPEG_WINGET.replace("ffmpeg.exe", "ffprobe.exe")


def _find(binary: str) -> str:
    found = shutil.which(binary)
    if found:
        return found
    candidate = _FFMPEG_WINGET if binary == "ffmpeg" else _FFPROBE_WINGET
    if Path(candidate).exists():
        return candidate
    raise RuntimeError(f"{binary} not found. Run: winget install Gyan.FFmpeg")


def _load_config() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open() as f:
            return yaml.safe_load(f) or {}
    return {}


def _duration(path: Path) -> float:
    result = subprocess.run(
        [_find("ffprobe"), "-v", "error",
         "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1",
         str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def _run(cmd: list[str], label: str) -> None:
    print(f"  [{label}] running ffmpeg...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr[-3000:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed at step: {label}")


def assemble(run_id: str) -> Path:
    """
    Assemble all assets for *run_id* into a final MP4.
    Returns the output file path.
    """
    ffmpeg = _find("ffmpeg")
    config = _load_config()

    # ── locate assets ─────────────────────────────────────────────────────
    audio_path = OUTPUT_AUDIO / f"{run_id}.mp3"
    ass_path   = OUTPUT_AUDIO / f"{run_id}.ass"
    clips_dir  = OUTPUT_CLIPS / run_id

    if not audio_path.exists():
        raise FileNotFoundError(f"Voiceover not found: {audio_path}")
    if not clips_dir.exists():
        raise FileNotFoundError(f"Clips directory not found: {clips_dir}")

    clips = sorted([
        p for p in clips_dir.iterdir()
        if p.suffix.lower() in {".mp4", ".mov", ".jpg", ".jpeg", ".png"}
    ])
    if not clips:
        raise FileNotFoundError(f"No clips found in {clips_dir}")

    # Optional background music — pick the first match for this run_id
    music_files = sorted(ASSETS_MUSIC.glob(f"{run_id}_*.mp3"))
    music_path  = music_files[0] if music_files else None

    voice_dur = _duration(audio_path)
    print(f"  Voiceover duration : {voice_dur:.2f}s")
    print(f"  Clips found        : {len(clips)}")
    print(f"  Background music   : {music_path.name if music_path else 'none'}")
    if ass_path.exists():
        print(f"  Caption file       : {ass_path.name}")
    else:
        print("  Caption file       : not found — assembling without captions")

    OUTPUT_FINAL.mkdir(parents=True, exist_ok=True)
    final_path = OUTPUT_FINAL / f"{run_id}.mp4"
    tmp_path   = OUTPUT_FINAL / f"{run_id}_tmp.mp4"

    # ── Pass 1: concat clips + mix audio ──────────────────────────────────
    music_vol = config.get("video", {}).get("music_volume_db", -20)
    # Convert dB to linear: 10^(dB/20)
    music_linear = 10 ** (music_vol / 20)

    seg_dur = voice_dur / len(clips)
    n       = len(clips)

    # Build inputs
    inputs: list[str] = []
    for clip in clips:
        # loop each clip so short clips fill their segment
        inputs += ["-stream_loop", "-1", "-i", str(clip)]

    voice_idx = n
    inputs += ["-i", str(audio_path)]

    music_idx = None
    if music_path:
        music_idx = n + 1
        inputs += ["-i", str(music_path)]

    # Build filter_complex
    scale_filters = []
    for i in range(n):
        scale_filters.append(
            f"[{i}:v]trim=duration={seg_dur:.3f},setpts=PTS-STARTPTS,"
            f"scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,setsar=1,fps=30[v{i}]"
        )

    concat_inputs = "".join(f"[v{i}]" for i in range(n))
    concat_filter = f"{concat_inputs}concat=n={n}:v=1:a=0[vconcat]"
    trim_filter   = f"[vconcat]trim=duration={voice_dur:.3f},setpts=PTS-STARTPTS[vout]"

    # Resample everything to 44100 Hz stereo before mixing to ensure
    # compatibility across all players (edge-tts outputs 24000 Hz mono)
    if music_idx is not None:
        audio_filter = (
            f"[{voice_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume=1.5[voice];"
            f"[{music_idx}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume={music_linear:.4f},atrim=duration={voice_dur:.3f}[music];"
            f"[voice][music]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    else:
        audio_filter = (
            f"[{voice_idx}:a]aresample=44100,"
            f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"volume=1.5[aout]"
        )

    filter_complex = (
        ";".join(scale_filters)
        + ";" + concat_filter
        + ";" + trim_filter
        + ";" + audio_filter
    )

    pass1_cmd = (
        [ffmpeg, "-y"]
        + inputs
        + ["-filter_complex", filter_complex,
           "-map", "[vout]", "-map", "[aout]",
           "-c:v", "libx264", "-crf", "23", "-preset", "fast",
           "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
           str(tmp_path)]
    )
    _run(pass1_cmd, "Pass 1 — concat + audio mix")

    # ── Pass 2: burn-in ASS captions ──────────────────────────────────────
    if ass_path.exists():
        # Use a short relative path to avoid Windows path escaping in the filter
        tmp_ass = PROJECT_ROOT / "subs_tmp.ass"
        shutil.copy(ass_path, tmp_ass)
        try:
            pass2_cmd = [
                ffmpeg, "-y",
                "-i", str(tmp_path),
                "-vf", "ass=subs_tmp.ass",
                "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                str(final_path),
            ]
            _run(pass2_cmd, "Pass 2 — burn captions")
        finally:
            tmp_ass.unlink(missing_ok=True)
            tmp_path.unlink(missing_ok=True)
    else:
        # No captions — just rename the temp file
        tmp_path.rename(final_path)

    # Verify output
    out_dur  = _duration(final_path)
    out_size = final_path.stat().st_size // (1024 * 1024)
    print(f"\n  Output : {final_path}")
    print(f"  Duration: {out_dur:.2f}s | Size: {out_size} MB")

    if out_dur > 60:
        print(
            f"  WARNING: video is {out_dur:.1f}s — over YouTube Shorts 60s limit!",
            file=sys.stderr,
        )

    return final_path
