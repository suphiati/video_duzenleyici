"""Scene-aware planner used when the user enables Pro Mode.

Responsibilities:
- Detect scenes in every source video (cached).
- Pick the "middle" of each scene as a candidate clip.
- Respect per-style duration ranges and transition preferences.
- Optionally snap cuts to music beats when a beat map is supplied.
- Produce plans shaped identically to ``batch_service.plan_content_distribution``
  so the existing renderer consumes them unchanged.
"""

from __future__ import annotations

import math
import random
from typing import Any

from app.services import scene_detector, beat_analyzer


STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "auto": {
        "clip_length": (3.5, 6.0),
        "photo_duration": 4.0,
        "transition": "fade",
        "transition_duration": 0.5,
        "prefer_mood": "generic",
        "beat_sync": True,
        "original_audio_volume": 0.55,
        "music_volume": 0.4,
        "shuffle_photos": False,
    },
    "vlog": {
        "clip_length": (2.2, 3.6),
        "photo_duration": 3.0,
        "transition": "none",
        "transition_duration": 0.25,
        "prefer_mood": "energetic",
        "beat_sync": True,
        "original_audio_volume": 0.65,
        "music_volume": 0.3,
        "shuffle_photos": False,
    },
    "cinematic": {
        "clip_length": (5.5, 8.5),
        "photo_duration": 5.5,
        "transition": "dissolve",
        "transition_duration": 1.0,
        "prefer_mood": "cinematic",
        "beat_sync": False,
        "original_audio_volume": 0.35,
        "music_volume": 0.55,
        "shuffle_photos": False,
    },
    "highlight": {
        "clip_length": (2.5, 4.5),
        "photo_duration": 3.5,
        "transition": "fade",
        "transition_duration": 0.35,
        "prefer_mood": "energetic",
        "beat_sync": True,
        "original_audio_volume": 0.45,
        "music_volume": 0.5,
        "shuffle_photos": True,
    },
    "calm": {
        "clip_length": (4.5, 7.5),
        "photo_duration": 6.0,
        "transition": "fade",
        "transition_duration": 0.8,
        "prefer_mood": "calm",
        "beat_sync": False,
        "original_audio_volume": 0.4,
        "music_volume": 0.5,
        "shuffle_photos": False,
    },
}


def get_profile(style: str) -> dict[str, Any]:
    return STYLE_PROFILES.get(style, STYLE_PROFILES["auto"])


def _pick_candidate(scene: tuple[float, float], clip_length: tuple[float, float]) -> tuple[float, float]:
    """Pick the cleanest (middle) clip from within a scene."""
    s_start, s_end = scene
    s_dur = s_end - s_start
    target_len = min(s_dur, random.uniform(*clip_length))
    # Prefer mid-scene to skip cuts at hard boundaries
    mid = s_start + s_dur / 2.0
    clip_start = max(s_start, mid - target_len / 2.0)
    clip_end = min(s_end, clip_start + target_len)
    clip_start = max(s_start, clip_end - target_len)
    return (round(clip_start, 2), round(clip_end, 2))


def _score_candidate(scene: tuple[float, float], src_index: int, total: int) -> float:
    """Heuristic scoring: longer scenes + mid-file position get a bump."""
    s_start, s_end = scene
    s_dur = s_end - s_start

    # Duration score: favour ~4-10s scenes
    if s_dur < 1.5:
        dur_score = 0.0
    elif s_dur < 4.0:
        dur_score = s_dur / 4.0
    elif s_dur < 10.0:
        dur_score = 1.0
    else:
        dur_score = max(0.5, 10.0 / s_dur)

    # Position score: slight preference for middle parts of the source list
    if total <= 1:
        pos_score = 0.8
    else:
        rel = src_index / (total - 1)
        pos_score = 1.0 - abs(rel - 0.5) * 0.6

    return round(dur_score * 0.7 + pos_score * 0.3, 3)


def build_candidates(videos: list[dict]) -> list[dict]:
    """Run scene detection per video and return flat candidate list."""
    candidates: list[dict] = []
    for idx, v in enumerate(videos):
        scenes = scene_detector.detect_scenes(v["path"], v["duration"])
        for scene in scenes:
            s_dur = scene[1] - scene[0]
            if s_dur < 1.5:
                continue
            candidates.append({
                "path": v["path"],
                "scene": scene,
                "score": _score_candidate(scene, idx, len(videos)),
                "video_index": idx,
            })
    return candidates


def _distribute_candidates(candidates: list[dict], num_videos: int) -> list[list[dict]]:
    """Split candidates into N chronological groups while spreading sources evenly."""
    if not candidates:
        return [[] for _ in range(num_videos)]

    # Group by source video first, then interleave so each output pulls from
    # every source when possible.
    by_source: dict[int, list[dict]] = {}
    for c in candidates:
        by_source.setdefault(c["video_index"], []).append(c)
    for group in by_source.values():
        group.sort(key=lambda c: c["scene"][0])

    buckets: list[list[dict]] = [[] for _ in range(num_videos)]
    for src_idx, group in by_source.items():
        # Each source's scenes are spread chronologically across buckets.
        per_bucket = max(1, math.ceil(len(group) / num_videos))
        for i, cand in enumerate(group):
            bucket = min(num_videos - 1, i // per_bucket) if per_bucket else 0
            buckets[bucket].append(cand)

    # Inside each bucket, sort by original timestamp to keep a storytelling flow.
    for b in buckets:
        b.sort(key=lambda c: (c["video_index"], c["scene"][0]))
    return buckets


def _fill_plan(
    bucket: list[dict],
    photos: list[dict],
    profile: dict[str, Any],
    target_duration: float,
    beats: list[float] | None,
    tempo: float | None,
) -> list[dict]:
    """Turn a bucket of candidates + photos into a concrete content plan."""
    plan: list[dict] = []
    if not bucket and not photos:
        return plan

    clip_range = profile["clip_length"]
    if tempo and profile["beat_sync"]:
        # Override clip range with tempo-aware suggestion if more aggressive.
        suggested = beat_analyzer.suggested_clip_range(tempo)
        clip_range = (min(clip_range[0], suggested[0]), min(clip_range[1], suggested[1]))

    photo_dur = profile["photo_duration"]
    photo_interval = max(2, len(bucket) // max(1, len(photos) + 1)) if photos else 10**9
    photo_idx = 0
    accumulated = 0.0

    # Rank candidates by score but keep some chronological order — sort by score
    # for "highlight" style, otherwise keep the bucket order.
    ordered = list(bucket)
    if profile is STYLE_PROFILES["highlight"]:
        ordered.sort(key=lambda c: -c["score"])

    for i, cand in enumerate(ordered):
        clip_start, clip_end = _pick_candidate(cand["scene"], clip_range)

        # Beat-sync adjustment: nudge the end of the clip to a beat edge.
        if beats and profile["beat_sync"]:
            desired_end = accumulated + (clip_end - clip_start)
            snapped = beat_analyzer.snap_to_beat(desired_end, beats, window=0.45)
            delta = snapped - desired_end
            if abs(delta) < (clip_end - clip_start) * 0.35:
                clip_end = max(clip_start + 1.2, clip_end + delta)

        item_dur = clip_end - clip_start
        if accumulated + item_dur > target_duration + 0.5:
            remaining = target_duration - accumulated
            if remaining > 1.0:
                clip_end = clip_start + remaining
                plan.append({"type": "video", "path": cand["path"],
                             "start": round(clip_start, 2), "end": round(clip_end, 2)})
                accumulated += remaining
            break

        plan.append({"type": "video", "path": cand["path"],
                     "start": round(clip_start, 2), "end": round(clip_end, 2)})
        accumulated += item_dur

        if photos and photo_idx < len(photos) and (i + 1) % photo_interval == 0:
            if accumulated + photo_dur <= target_duration + 0.5:
                plan.append({"type": "photo", "path": photos[photo_idx]["path"],
                             "duration": photo_dur})
                accumulated += photo_dur
                photo_idx += 1

    # Any leftover photos get appended if there is room.
    while photo_idx < len(photos) and accumulated + photo_dur <= target_duration + 0.5:
        plan.append({"type": "photo", "path": photos[photo_idx]["path"], "duration": photo_dur})
        accumulated += photo_dur
        photo_idx += 1

    return plan


def build_plans(
    videos: list[dict],
    photos: list[dict],
    num_videos: int,
    target_duration: float,
    style: str,
    beats: list[float] | None = None,
    tempo: float | None = None,
) -> tuple[list[list[dict]], dict[str, Any]]:
    """Build ``num_videos`` pro-edited plans. Returns (plans, meta)."""
    profile = get_profile(style)
    candidates = build_candidates(videos)
    buckets = _distribute_candidates(candidates, num_videos)

    photo_groups = _split_photos(photos, num_videos, profile["shuffle_photos"])
    plans = []
    for i in range(num_videos):
        plan = _fill_plan(
            bucket=buckets[i],
            photos=photo_groups[i],
            profile=profile,
            target_duration=target_duration,
            beats=beats,
            tempo=tempo,
        )
        plans.append(plan)

    meta = {
        "style": style,
        "profile": profile,
        "total_candidates": len(candidates),
        "beats_available": bool(beats),
        "tempo": tempo,
    }
    return plans, meta


def _split_photos(photos: list[dict], n: int, shuffle: bool) -> list[list[dict]]:
    if not photos:
        return [[] for _ in range(n)]
    pool = list(photos)
    if shuffle:
        random.shuffle(pool)
    groups: list[list[dict]] = [[] for _ in range(n)]
    for i, p in enumerate(pool):
        groups[i % n].append(p)
    return groups
