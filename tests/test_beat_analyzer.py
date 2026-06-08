"""Unit tests for beat_analyzer pure helpers (no librosa required)."""

from app.services import beat_analyzer


def test_snap_to_beat_within_window():
    assert beat_analyzer.snap_to_beat(2.1, [1.0, 2.0, 3.0], window=0.5) == 2.0


def test_snap_to_beat_outside_window_returns_target():
    assert beat_analyzer.snap_to_beat(5.0, [1.0, 2.0, 3.0], window=0.3) == 5.0


def test_snap_to_beat_no_beats_returns_target():
    assert beat_analyzer.snap_to_beat(2.0, [], window=0.5) == 2.0


def test_suggested_clip_range_faster_tempo_shorter_clips():
    fast = beat_analyzer.suggested_clip_range(140)
    slow = beat_analyzer.suggested_clip_range(70)
    assert fast[0] <= slow[0]
    assert fast[1] <= slow[1]


def test_suggested_clip_range_zero_tempo_default():
    assert beat_analyzer.suggested_clip_range(0) == (3.5, 6.0)


def test_round_bar_duration_quantizes():
    # tempo 120 -> beat 0.5s -> 1 bar (4 beats) = 2.0s
    assert beat_analyzer.round_bar_duration(4.2, 120.0, bars=1) == 4.0


def test_round_bar_duration_minimum_one_bar():
    assert beat_analyzer.round_bar_duration(0.3, 120.0, bars=1) == 2.0


def test_round_bar_duration_zero_tempo_passthrough():
    assert beat_analyzer.round_bar_duration(7.0, 0.0) == 7.0


def test_split_into_phrases_step():
    beats = [float(b) for b in range(32)]
    # step = bars*4 = 16 -> indices 0 and 16
    assert beat_analyzer.split_into_phrases(beats, bars=4) == [0.0, 16.0]


def test_split_into_phrases_empty():
    assert beat_analyzer.split_into_phrases([], bars=4) == []
