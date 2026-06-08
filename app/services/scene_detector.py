"""FFmpeg-based scene detection with on-disk caching.

No extra dependencies: uses FFmpeg's built-in `select='gt(scene,X)'` filter plus
`showinfo` and parses the resulting timestamps from stderr. Downscales the stream
to 320px before analysis so it runs in seconds even on long clips. The same pass
also reports each scene-boundary frame's mean luminance (showinfo `mean:[Y ...]`),
used to bias clip selection toward well-exposed scenes.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from app.config import FFMPEG_BIN, SCENES_CACHE_FILE


_scene_regex = re.compile(r"pts_time:([\d.]+)")
_mean_regex = re.compile(r"mean:\[(\d+)")


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


def _to_dicts(cached: list) -> list[dict]:
    """Read cache entries. Old entries are [start, end]; new are [start, end, lum]."""
    out = []
    for x in cached:
        lum = x[2] if len(x) > 2 else None
        out.append({"start": x[0], "end": x[1], "luminance": lum})
    return out


def _to_cache(scenes: list[dict]) -> list:
    return [[s["start"], s["end"], s["luminance"]] for s in scenes]


def detect_scenes_detailed(
    video_path: str,
    total_duration: float,
    threshold: float = 0.35,
    min_duration: float = 1.5,
) -> list[dict]:
    """Return scenes as ``{"start", "end", "luminance"}`` dicts (luminance may be None).

    Falls back to a single scene spanning the full clip when detection fails
    or yields nothing.
    """
    if total_duration <= 0:
        return []

    key = _cache_key(video_path)
    cache = _load_cache()
    if key and key in cache:
        return _to_dicts(cache[key])

    def _remember(scenes: list[dict]) -> list[dict]:
        """Persist a result (including fallbacks) so it is not recomputed."""
        if key:
            cache[key] = _to_cache(scenes)
            if len(cache) > 500:
                trimmed = dict(list(cache.items())[-400:])
                trimmed[key] = _to_cache(scenes)
                _save_cache(trimmed)
            else:
                _save_cache(cache)
        return scenes

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
        # Cache the fallback too — otherwise a problem file re-pays the 4-min
        # timeout on every batch run.
        return _remember([{"start": 0.0, "end": round(total_duration, 2), "luminance": None}])

    cuts: list[float] = []
    lum_by_cut: dict[float, int] = {}
    for line in result.stderr.splitlines():
        if "showinfo" not in line:
            continue
        m = _scene_regex.search(line)
        if not m:
            continue
        t = float(m.group(1))
        if 0.5 < t < total_duration - 0.2:
            ct = round(t, 2)
            cuts.append(ct)
            lm = _mean_regex.search(line)
            if lm:
                lum_by_cut[ct] = int(lm.group(1))

    boundaries = [0.0] + sorted(set(cuts)) + [round(total_duration, 2)]
    scenes: list[dict] = []
    for i in range(len(boundaries) - 1):
        s, e = boundaries[i], boundaries[i + 1]
        if e - s >= min_duration:
            scenes.append({"start": s, "end": e, "luminance": lum_by_cut.get(s)})

    if not scenes:
        scenes = [{"start": 0.0, "end": round(total_duration, 2), "luminance": None}]

    return _remember(scenes)


def detect_scenes(
    video_path: str,
    total_duration: float,
    threshold: float = 0.35,
    min_duration: float = 1.5,
) -> list[tuple[float, float]]:
    """Backward-compatible ``(start, end)`` view over :func:`detect_scenes_detailed`."""
    return [
        (s["start"], s["end"])
        for s in detect_scenes_detailed(video_path, total_duration, threshold, min_duration)
    ]
