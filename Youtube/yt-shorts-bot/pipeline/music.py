"""
Phase 3b — Background music generation (zero API keys needed).

Detects mood from script keywords, then procedurally generates a loopable
ambient/beat track using numpy and exports it via ffmpeg.

Mood -> musical feel mapping:
  energetic   -> fast BPM, punchy kick + hi-hat, bright major chord
  motivational-> medium BPM, rising pad, major chord, bass pulse
  upbeat      -> medium-fast BPM, bouncy feel, major chord
  calm        -> slow BPM, soft pad only, minor chord
  corporate   -> medium BPM, clean pad, major 7th chord
  cinematic   -> slow BPM, sweeping pad, minor chord
"""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import wave
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from dotenv import load_dotenv

load_dotenv()

ASSETS_MUSIC = Path(__file__).parent.parent / "assets" / "music"
CONFIG_PATH  = Path(__file__).parent.parent / "config.yaml"

_FFMPEG_WINGET = (
    r"C:\Users\WottaCore - 01\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build\bin\ffmpeg.exe"
)

# Each mood: (bpm, root_hz, chord_intervals, has_beat, pad_brightness)
# chord_intervals in semitones above root
_MOODS: dict[str, dict] = {
    "energetic":    {"bpm": 128, "root": 110.0, "chord": [0,4,7,12], "beat": True,  "brightness": 0.8},
    "motivational": {"bpm": 100, "root": 98.0,  "chord": [0,4,7,11], "beat": True,  "brightness": 0.7},
    "upbeat":       {"bpm": 115, "root": 130.8,  "chord": [0,4,7],    "beat": True,  "brightness": 0.75},
    "calm":         {"bpm": 70,  "root": 82.4,  "chord": [0,3,7],    "beat": False, "brightness": 0.4},
    "corporate":    {"bpm": 90,  "root": 110.0, "chord": [0,4,7,11], "beat": False, "brightness": 0.6},
    "cinematic":    {"bpm": 60,  "root": 73.4,  "chord": [0,3,7,10], "beat": False, "brightness": 0.35},
    "joyful":       {"bpm": 110, "root": 130.8, "chord": [0,4,7],    "beat": True,  "brightness": 0.85},
    "electronic":   {"bpm": 120, "root": 110.0, "chord": [0,7,12],   "beat": True,  "brightness": 0.9},
    "romantic":     {"bpm": 75,  "root": 82.4,  "chord": [0,4,7,9],  "beat": False, "brightness": 0.45},
    "focus":        {"bpm": 80,  "root": 98.0,  "chord": [0,7],      "beat": False, "brightness": 0.3},
}

_KEYWORD_MOOD: list[tuple[list[str], str]] = [
    (["money","finance","saving","invest","budget","income","earn"],  "motivational"),
    (["fitness","workout","gym","exercise","health","sport"],         "energetic"),
    (["food","cook","recipe","kitchen","eat","bake"],                 "joyful"),
    (["tech","gadget","code","software","phone","app","computer"],    "electronic"),
    (["travel","adventure","explore","trip","nature","outdoor"],      "cinematic"),
    (["motivation","success","mindset","goal","growth","hustle"],     "motivational"),
    (["love","relationship","couple","romance","heart"],              "romantic"),
    (["study","learn","book","education","skill","focus"],            "focus"),
    (["comedy","funny","laugh","joke","prank"],                       "upbeat"),
    (["hack","tip","trick","diy","life","easy","quick","clean"],      "upbeat"),
    (["business","startup","corporate","professional"],               "corporate"),
]
_DEFAULT_MOOD = "upbeat"


def _find_ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    if Path(_FFMPEG_WINGET).exists():
        return _FFMPEG_WINGET
    raise RuntimeError("ffmpeg not found. Run: winget install Gyan.FFmpeg")


def _semitone(base_hz: float, semitones: int) -> float:
    return base_hz * (2 ** (semitones / 12))


def _detect_mood(script_data: dict) -> str:
    haystack = " ".join([
        *script_data.get("visual_keywords", []),
        *script_data.get("tags", []),
        script_data.get("_meta", {}).get("topic", ""),
        script_data.get("script", ""),
    ]).lower()

    best_mood, best_score = _DEFAULT_MOOD, 0
    for keywords, mood in _KEYWORD_MOOD:
        score = sum(1 for kw in keywords if kw in haystack)
        if score > best_score:
            best_mood, best_score = mood, score
    return best_mood


def _pad_tone(freq: float, duration: float, sr: int, amplitude: float, brightness: float) -> np.ndarray:
    """Generate a single pad tone: sine + soft harmonics with slow attack/release."""
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Fundamental + harmonics (higher brightness = more harmonics)
    wave_data = np.sin(2 * np.pi * freq * t)
    wave_data += brightness * 0.4 * np.sin(2 * np.pi * freq * 2 * t)
    wave_data += brightness * 0.15 * np.sin(2 * np.pi * freq * 3 * t)

    # ADSR envelope — clamp to 1/3 of total so short segments don't overflow
    n = len(t)
    attack  = min(int(sr * 0.15), n // 3)
    release = min(int(sr * 0.3),  n // 3)
    env = np.ones(n)
    if attack > 0:
        env[:attack] = np.linspace(0, 1, attack)
    if release > 0:
        env[-release:] = np.linspace(1, 0, release)

    return wave_data * env * amplitude


def _kick(sr: int) -> np.ndarray:
    """Synthesize a punchy kick drum."""
    dur = 0.25
    t   = np.linspace(0, dur, int(sr * dur), endpoint=False)
    freq_env = 150 * np.exp(-30 * t)
    sig  = np.sin(2 * np.pi * freq_env * t)
    env  = np.exp(-20 * t)
    return sig * env * 0.9


def _hihat(sr: int, open_: bool = False) -> np.ndarray:
    """Synthesize a hi-hat (closed or open)."""
    dur = 0.06 if not open_ else 0.18
    t   = np.linspace(0, dur, int(sr * dur), endpoint=False)
    noise = np.random.randn(len(t))
    env   = np.exp(-50 * t) if not open_ else np.exp(-15 * t)
    # High-pass filter approximation: subtract low frequencies
    filtered = noise - np.convolve(noise, np.ones(8)/8, mode="same")
    return filtered * env * 0.25


def _build_beat_track(mood_cfg: dict, duration: float, sr: int) -> np.ndarray:
    """Build a drum beat track for the full duration."""
    bpm      = mood_cfg["bpm"]
    beat_dur = 60.0 / bpm          # duration of one beat in seconds
    bar_dur  = beat_dur * 4        # 4/4 time
    n_samples = int(sr * duration)
    track = np.zeros(n_samples)

    kick_samples  = _kick(sr)
    hihat_samples = _hihat(sr)
    open_samples  = _hihat(sr, open_=True)

    bar_samples = int(sr * bar_dur)
    beat_samples = int(sr * beat_dur)
    half_beat    = beat_samples // 2

    # Pattern: kick on 1&3, hihat on every 8th, open on beat 2&4
    kick_positions  = [0, beat_samples * 2]
    hihat_positions = [i * half_beat for i in range(8)]
    open_positions  = [beat_samples, beat_samples * 3]

    def _add(buf: np.ndarray, s: int, snd: np.ndarray) -> None:
        avail = n_samples - s
        if avail > 0:
            take = min(len(snd), avail)
            buf[s:s + take] += snd[:take]

    bar = 0
    while bar * bar_samples < n_samples:
        offset = bar * bar_samples
        for pos in kick_positions:
            _add(track, offset + pos, kick_samples)
        for pos in hihat_positions:
            _add(track, offset + pos, hihat_samples)
        for pos in open_positions:
            _add(track, offset + pos, open_samples)
        bar += 1

    return track


def _generate_music(mood: str, duration: float, sr: int = 44100) -> np.ndarray:
    """Generate a full ambient/beat track for the given mood and duration."""
    cfg = _MOODS.get(mood, _MOODS[_DEFAULT_MOOD])
    root  = cfg["root"]
    chord = cfg["chord"]
    brightness = cfg["brightness"]

    # Pad layer: sustain chord throughout
    pad = np.zeros(int(sr * duration))
    for semitones in chord:
        freq = _semitone(root, semitones)
        pad += _pad_tone(freq, duration, sr, amplitude=0.18, brightness=brightness)
        # Add octave up for shimmer
        pad += _pad_tone(freq * 2, duration, sr, amplitude=0.06, brightness=brightness * 0.5)

    # Beat layer (if mood calls for it)
    if cfg["beat"]:
        beat = _build_beat_track(cfg, duration, sr)
    else:
        beat = np.zeros(int(sr * duration))

    # Bass pulse: root note, one pulse per bar
    bpm = cfg["bpm"]
    bar_dur = (60.0 / bpm) * 4
    bass_freq = root / 2  # one octave below
    n_samples = int(sr * duration)
    bass = np.zeros(n_samples)
    bar = 0
    while bar * bar_dur < duration:
        seg_dur = min(bar_dur * 0.7, duration - bar * bar_dur)
        if seg_dur > 0.05:
            seg = _pad_tone(bass_freq, seg_dur, sr, amplitude=0.25, brightness=0.1)
            s = int(bar * bar_dur * sr)
            # clamp to avoid out-of-bounds regardless of float rounding
            avail = n_samples - s
            if avail > 0:
                take = min(len(seg), avail)
                bass[s:s + take] += seg[:take]
        bar += 1

    mix = pad + beat * 0.5 + bass

    # Normalize to -6 dBFS
    peak = np.max(np.abs(mix))
    if peak > 0:
        mix = mix / peak * 0.5

    # Fade in/out (0.5 sec each)
    fade = int(sr * 0.5)
    mix[:fade]  *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)

    return mix.astype(np.float32)


def _write_wav(samples: np.ndarray, path: Path, sr: int = 44100) -> None:
    pcm = (samples * 32767).astype(np.int16)
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    ffmpeg = _find_ffmpeg()
    subprocess.run(
        [ffmpeg, "-y", "-i", str(wav_path), "-codec:a", "libmp3lame",
         "-qscale:a", "4", str(mp3_path)],
        capture_output=True,
        check=True,
    )
    wav_path.unlink(missing_ok=True)


def fetch_music(script_path: Path, duration: float = 60.0) -> Path:
    """
    Generate background music matching the script mood.
    Returns path to MP3 file in assets/music/.
    """
    script_data = json.loads(script_path.read_text(encoding="utf-8"))
    mood = _detect_mood(script_data)
    print(f"  Detected mood: '{mood}'")

    ASSETS_MUSIC.mkdir(parents=True, exist_ok=True)
    run_id   = script_path.stem
    mp3_path = ASSETS_MUSIC / f"{run_id}_{mood}.mp3"

    if mp3_path.exists():
        print(f"  Already generated: {mp3_path.name}")
        return mp3_path

    # Generate slightly longer than needed so Phase 5 can trim
    gen_duration = max(duration + 5, 65.0)
    print(f"  Generating {gen_duration:.0f}s '{mood}' track...")

    samples = _generate_music(mood, gen_duration)
    wav_path = mp3_path.with_suffix(".wav")
    _write_wav(samples, wav_path)
    _wav_to_mp3(wav_path, mp3_path)

    size_kb = mp3_path.stat().st_size // 1024
    print(f"  Music saved: {mp3_path.name} ({size_kb} KB)")
    return mp3_path
