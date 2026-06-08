"""Optional beat / tempo detection via librosa.

librosa is a heavy dependency, so it is imported lazily. If it is missing the
pro pipeline simply falls back to linear cut spacing.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BeatInfo:
    tempo: float
    beats: list[float]  # beat timestamps in seconds


def is_available() -> bool:
    try:
        import librosa  # noqa: F401
        return True
    except Exception:
        return False


def analyze(audio_path: str) -> BeatInfo | None:
    """Return tempo + beat timestamps or None if librosa is unavailable."""
    try:
        import librosa
        import numpy as np  # noqa: F401
    except Exception:
        return None

    try:
        y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=600.0)
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        tempo_val = float(tempo) if not hasattr(tempo, "__len__") else float(tempo[0])
        return BeatInfo(tempo=round(tempo_val, 1),
                        beats=[round(float(b), 3) for b in beats])
    except Exception:
        return None


def snap_to_beat(target_time: float, beats: list[float], window: float = 0.5) -> float:
    """Return the beat closest to target_time within ±window seconds, or target."""
    if not beats:
        return target_time
    best = target_time
    best_delta = window + 1e-6
    # Beats are sorted; binary search would be faster but the list is small.
    for b in beats:
        d = abs(b - target_time)
        if d < best_delta:
            best_delta = d
            best = b
        if b > target_time + window:
            break
    return best


def split_into_phrases(beats: list[float], bars: int = 4) -> list[float]:
    """Approximate musical-phrase boundaries (every ``bars`` bars of 4 beats)."""
    if not beats:
        return []
    step = bars * 4
    return [beats[i] for i in range(0, len(beats), step)]


def round_bar_duration(duration: float, tempo: float, bars: int = 4) -> float:
    """Quantize a duration to the nearest full bar length."""
    if tempo <= 0:
        return duration
    bar_sec = (60.0 / tempo) * 4 * bars
    if bar_sec <= 0:
        return duration
    return max(bar_sec, round(duration / bar_sec) * bar_sec)


def suggested_clip_range(tempo: float) -> tuple[float, float]:
    """Heuristic: faster tempo → shorter cuts."""
    if tempo <= 0:
        return (3.5, 6.0)
    if tempo >= 130:
        return (1.8, 3.2)
    if tempo >= 100:
        return (2.5, 4.5)
    if tempo >= 80:
        return (3.5, 6.0)
    return (5.0, 8.0)


