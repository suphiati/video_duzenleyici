"""Local free-music library.

Layout: data/music/<mood>/*.mp3 (or wav/m4a/ogg/flac). The subdirectory name
is the mood tag; files placed directly in data/music/ are treated as mood
``generic``.
"""

from __future__ import annotations

import random
from pathlib import Path

from app.config import MUSIC_DIR, AUDIO_EXTENSIONS
from app.services.ffmpeg_service import _get_duration

MOODS = ["energetic", "calm", "ambient", "cinematic", "generic"]


def list_tracks() -> list[dict]:
    """Return every audio file under data/music/ grouped by mood."""
    if not MUSIC_DIR.exists():
        return []

    tracks: list[dict] = []
    for p in MUSIC_DIR.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in AUDIO_EXTENSIONS:
            continue
        try:
            rel = p.relative_to(MUSIC_DIR)
        except ValueError:
            continue

        parts = rel.parts
        mood = parts[0].lower() if len(parts) > 1 else "generic"
        tracks.append({
            "path": str(p),
            "name": p.name,
            "mood": mood,
            "size": p.stat().st_size,
        })
    tracks.sort(key=lambda t: (t["mood"], t["name"].lower()))
    return tracks


def pick_track(preferred_mood: str | None = None, exclude: set[str] | None = None) -> dict | None:
    """Pick a random track, preferring the requested mood."""
    tracks = list_tracks()
    if not tracks:
        return None

    exclude = exclude or set()
    remaining = [t for t in tracks if t["path"] not in exclude]
    if not remaining:
        remaining = tracks  # allow re-use if we ran out

    if preferred_mood:
        preferred = [t for t in remaining if t["mood"] == preferred_mood.lower()]
        if preferred:
            return random.choice(preferred)

    return random.choice(remaining)


def probe_track(path: str) -> dict:
    """Return {path, duration} for a single track."""
    return {"path": path, "duration": _get_duration(path)}
