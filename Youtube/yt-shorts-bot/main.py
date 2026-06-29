"""
YouTube Shorts Bot — CLI entrypoint.

Each phase is exposed as a subcommand. Run:
    python main.py --help
to see all available commands.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    name="yt-shorts-bot",
    help="End-to-end YouTube Shorts automation pipeline.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Phase 1 — Script generation
# ---------------------------------------------------------------------------

@app.command("generate-script")
def generate_script_cmd(
    topic: str = typer.Option(
        "",
        "--topic", "-t",
        help="Topic/niche for the Short. Overrides config.yaml if provided.",
    ),
    style: str = typer.Option(
        "tips",
        "--style", "-s",
        help="Script style: 'tips' (45sec English), 'story' (60sec Hindi), 'facts' (60sec Hindi 7 facts).",
    ),
) -> None:
    """Phase 1: Generate a viral-style script with the configured LLM."""
    from pipeline.script_gen import generate_script

    if style not in ("tips", "story", "facts"):
        typer.echo("  ERROR: --style must be 'tips', 'story', or 'facts'", err=True)
        raise typer.Exit(code=1)

    effective = topic or "(from config.yaml)"
    typer.echo(f"\n[Phase 1] Generating {style} script — topic: {effective}")

    try:
        out_path = generate_script(topic, style=style)
    except EnvironmentError as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)
    except ValueError as exc:
        typer.echo(f"\n  ERROR (bad LLM response): {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Script saved: {out_path}")
    typer.echo("  Phase 1 complete. Review the JSON, then run generate-voice.\n")


# ---------------------------------------------------------------------------
# Phase 2 — Voiceover  (stub — will be filled in Phase 2)
# ---------------------------------------------------------------------------

@app.command("generate-voice")
def generate_voice_cmd(
    script: Path = typer.Option(..., "--script", "-s", help="Path to script JSON."),
) -> None:
    """Phase 2: Convert script text to a voiceover MP3 via edge-tts."""
    from pipeline.voiceover import generate_voiceover

    if not script.exists():
        typer.echo(f"  ERROR: Script file not found: {script}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n[Phase 2] Generating voiceover from: {script.name}")

    try:
        out_path, duration = generate_voiceover(script)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Audio saved: {out_path}")
    if duration > 0:
        typer.echo(f"  Duration   : {duration:.1f}s")
    typer.echo("  Phase 2 complete. Run fetch-visuals next.\n")


# ---------------------------------------------------------------------------
# Phase 3b — Background music
# ---------------------------------------------------------------------------

@app.command("fetch-music")
def fetch_music_cmd(
    script: Path = typer.Option(..., "--script", "-s", help="Path to script JSON."),
    duration: float = typer.Option(65.0, "--duration", "-d", help="Track duration in seconds."),
) -> None:
    """Phase 3b: Generate mood-matched background music (no API key needed)."""
    from pipeline.music import fetch_music

    if not script.exists():
        typer.echo(f"  ERROR: Script file not found: {script}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n[Phase 3b] Generating background music for: {script.name}")

    try:
        music_path = fetch_music(script, duration=duration)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Music saved: {music_path}")
    typer.echo("  Run assemble when all assets are ready.\n")


# ---------------------------------------------------------------------------
# Phase 3 — Visuals
# ---------------------------------------------------------------------------

@app.command("fetch-visuals")
def fetch_visuals_cmd(
    script: Path = typer.Option(..., "--script", "-s", help="Path to script JSON."),
    duration: float = typer.Option(35.0, "--duration", "-d", help="Voiceover duration in seconds."),
) -> None:
    """Phase 3: Download stock video/photo clips from Pexels (gradient fallback if no key)."""
    from pipeline.visuals import fetch_visuals

    if not script.exists():
        typer.echo(f"  ERROR: Script file not found: {script}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n[Phase 3] Fetching visuals for: {script.name}  (duration: {duration}s)")

    try:
        clips = fetch_visuals(script, voiceover_duration=duration)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  {len(clips)} clip(s) ready.")
    typer.echo("  Phase 3 complete. Run generate-captions next.\n")


# ---------------------------------------------------------------------------
# Phase 4 — Captions  (stub)
# ---------------------------------------------------------------------------

@app.command("generate-captions")
def generate_captions_cmd(
    audio: Path = typer.Option(..., "--audio", "-a", help="Path to voiceover MP3."),
) -> None:
    """Phase 4: Run Whisper locally to generate synced .ass caption file."""
    from pipeline.captions import generate_captions

    if not audio.exists():
        typer.echo(f"  ERROR: Audio file not found: {audio}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n[Phase 4] Generating captions for: {audio.name}")

    try:
        ass_path = generate_captions(audio)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Captions saved: {ass_path}")
    typer.echo("  Phase 4 complete. Run assemble next.\n")


# ---------------------------------------------------------------------------
# Phase 5 — Assembly  (stub)
# ---------------------------------------------------------------------------

@app.command("assemble")
def assemble_cmd(
    id_: str = typer.Option(..., "--id", help="Shared timestamp ID for this run."),
) -> None:
    """Phase 5: Assemble clips + voiceover + captions + music into final MP4."""
    from pipeline.assemble import assemble

    typer.echo(f"\n[Phase 5] Assembling video for run ID: {id_}")

    try:
        out_path = assemble(id_)
    except FileNotFoundError as exc:
        typer.echo(f"\n  ERROR (missing asset): {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Final video: {out_path}")
    typer.echo("  Phase 5 complete. Run upload next.\n")


# ---------------------------------------------------------------------------
# Phase 6 — Upload  (stub)
# ---------------------------------------------------------------------------

@app.command("upload")
def upload_cmd(
    video: Path = typer.Option(..., "--video", help="Path to the final MP4."),
    script: Path = typer.Option(
        Path(""), "--script", "-s",
        help="Path to script JSON (for title/description/tags). Optional.",
    ),
    publish_at: str = typer.Option(
        "", "--publish-at",
        help="Scheduled publish time. ISO-8601: e.g. '2026-06-30T18:30:00+05:30'",
    ),
) -> None:
    """Phase 6: Upload the Short to YouTube with optional scheduled publishing."""
    from pipeline.uploader import upload_video

    if not video.exists():
        typer.echo(f"\n  ERROR: Video not found: {video}", err=True)
        raise typer.Exit(code=1)

    script_path = script if script != Path("") and script.exists() else None

    typer.echo(f"\n[Phase 6] Uploading: {video.name}")

    try:
        video_id = upload_video(
            video_path=video,
            script_path=script_path,
            publish_at=publish_at,
        )
    except FileNotFoundError as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)
    except Exception as exc:
        typer.echo(f"\n  ERROR: {exc}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"\n  Upload complete! Video ID: {video_id}")
    typer.echo(f"  Watch: https://youtube.com/shorts/{video_id}\n")


# ---------------------------------------------------------------------------
# Phase 7 — Analytics  (stub)
# ---------------------------------------------------------------------------

@app.command("report")
def report_cmd() -> None:
    """Phase 7: Show all uploaded videos with IDs, URLs, dates and stats."""
    from pipeline.analytics import show_report
    show_report()


@app.command("refresh-stats")
def refresh_stats_cmd() -> None:
    """Phase 7: Pull latest view/like counts from YouTube API."""
    from pipeline.analytics import refresh_stats
    typer.echo("\n[Phase 7] Fetching latest stats from YouTube...")
    refresh_stats()


# ---------------------------------------------------------------------------
# Phase 8 — Full pipeline  (stub)
# ---------------------------------------------------------------------------

@app.command("run-full")
def run_full_cmd(
    topic: str = typer.Option("", "--topic", "-t", help="Topic for this run."),
    publish_at: str = typer.Option("", "--publish-at", help="Scheduled publish datetime."),
) -> None:
    """Phase 8: Run the full pipeline end-to-end (phases 1–6)."""
    typer.echo("[Phase 8] Not yet implemented — coming in Phase 8.")


if __name__ == "__main__":
    app()
