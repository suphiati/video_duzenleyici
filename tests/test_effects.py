"""Unit tests for per-clip colour-effect helpers (pure, no ffmpeg)."""

from app.services.ffmpeg_service import _clip_has_effects, _eq_filter


def test_neutral_clip_has_no_effects():
    clip = {"brightness": 0.0, "contrast": 1.0, "saturation": 1.0}
    assert not _clip_has_effects(clip)
    assert _eq_filter(clip) is None


def test_missing_fields_treated_neutral():
    assert not _clip_has_effects({})
    assert _eq_filter({}) is None


def test_none_values_treated_neutral():
    assert not _clip_has_effects(
        {"brightness": None, "contrast": None, "saturation": None}
    )


def test_brightness_triggers_effects():
    clip = {"brightness": 0.2, "contrast": 1.0, "saturation": 1.0}
    assert _clip_has_effects(clip)
    f = _eq_filter(clip)
    assert f.startswith("eq=")
    assert "brightness=0.200" in f


def test_contrast_and_saturation_in_filter():
    f = _eq_filter({"brightness": 0.0, "contrast": 1.3, "saturation": 0.5})
    assert "contrast=1.300" in f
    assert "saturation=0.500" in f
