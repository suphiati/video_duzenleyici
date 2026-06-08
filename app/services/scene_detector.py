"""FFmpeg-based scene detection with on-disk caching.

No extra dependencies: uses FFmpeg's built-in `select='gt(scene,X)'` filter plus
`showinfo` and parses the resulting timestamps from stderr. Downscales the stream
to 320px before analysis so it runs in seconds even on long clips.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from app.config import FFMPEG_BIN, SCENES_CACHE_FILE


_scene_regex = re.compile(r"pts_time:([\d.]+)")


def _cache_key(video_path: str) -> str | None:
    p = Path(video_path)
    try:
        st = p.stat()
        return f"{p.resolve()}|{st.st_size}|{int(st.st_mtime)}"
    except FileNotFoundError:
        return None


def _load_cache() -> dict:
    if not SCENES_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(SCENES_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: dict) -> None:
    try:
        SCENES_CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def detect_scenes(
    video_path: str,
    total_duration: float,
    threshold: float = 0.35,
    min_duration: float = 1.5,
) -> list[tuple[float, float]]:
    """Return a list of (start, end) scene boundaries in seconds.

    Falls back to a single scene spanning the full clip when detection fails
    or yields nothing.
    """
    if total_duration <= 0:
        return []

    key = _cache_key(video_path)
    cache = _load_cache()
    if key and key in cache:
        cached = cache[key]
        return [tuple(x) for x in cached]

    cmd = [
        FFMPEG_BIN, "-hide_banner", "-nostats",
        "-i", video_path,
        "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo",
        "-an", "-sn", "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=240,
        )
    except subprocess.TimeoutExpired:
        return [(0.0, total_duration)]

    cuts: list[float] = []
    for line in result.stderr.splitlines():
        if "showinfo" not in line:
            continue
        m = _scene_regex.search(line)
        if m:
            t = float(m.group(1))
            if 0.5 < t < total_duration - 0.2:
                cuts.append(t)

    boundaries = [0.0] + sorted(set(round(c, 2) for c in cuts)) + [round(total_duration, 2)]
    scenes: list[tuple[float, float]] = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        if e - s >= min_duration:
            scenes.append((s, e))

    if not scenes:
        scenes = [(0.0, total_duration)]

    if key:
        cache[key] = scenes
        # Trim cache if it gets too large
        if len(cache) > 500:
            cache = dict(list(cache.items())[-400:])
        _save_cache(cache)

    return scenes
