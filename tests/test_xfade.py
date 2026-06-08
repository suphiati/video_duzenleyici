"""Unit tests for the pure xfade-offset helper (no FFmpeg)."""

from app.services.ffmpeg_service import compute_xfade_offsets


def test_uniform_durations():
    # clip0..2 each 5s, 1s crossfades:
    #   t1 = 5 - 1 = 4 ; t2 = (5+5) - 2 = 8
    assert compute_xfade_offsets([5.0, 5.0, 5.0], 1.0) == [4.0, 8.0]


def test_single_clip_has_no_transitions():
    assert compute_xfade_offsets([5.0], 1.0) == []


def test_empty_durations():
    assert compute_xfade_offsets([], 1.0) == []


def test_offset_count_is_n_minus_one():
    durs = [3.0, 4.0, 2.0, 6.0, 5.0]
    assert len(compute_xfade_offsets(durs, 0.5)) == len(durs) - 1


def test_offsets_are_monotonic_increasing():
    durs = [3.0, 4.0, 2.0, 6.0, 5.0]
    offs = compute_xfade_offsets(durs, 0.5)
    assert all(b >= a for a, b in zip(offs, offs[1:]))


def test_offset_formula():
    durs = [3.0, 4.0, 2.0]
    offs = compute_xfade_offsets(durs, 0.5)
    assert offs[0] == round(3.0 - 1 * 0.5, 3)        # 2.5
    assert offs[1] == round(3.0 + 4.0 - 2 * 0.5, 3)  # 6.0


def test_offsets_clamped_non_negative():
    # Transition longer than the clips -> first offset clamps to 0.
    assert compute_xfade_offsets([1.0, 1.0], 5.0) == [0.0]
