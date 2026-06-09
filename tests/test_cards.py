"""Tests for intro/outro card injection + PNG rendering.

Card injection is pure logic. Card rendering uses Pillow only (no ffmpeg), so
it stays out of the ``slow`` bucket. All output goes to a tmp dir.
"""

from pathlib import Path

from app.services.batch_service import _inject_cards


def test_inject_both_cards_wraps_plan():
    plan = [{"type": "video", "path": "a.mp4", "start": 0, "end": 5}]
    out = _inject_cards(plan, intro_path="intro.png", outro_path="outro.png",
                        duration=2.0)
    assert len(out) == 3
    assert out[0] == {"type": "photo", "path": "intro.png", "duration": 2.0}
    assert out[-1] == {"type": "photo", "path": "outro.png", "duration": 2.0}
    assert out[1] is plan[0]  # original content untouched in the middle


def test_inject_no_cards_is_noop():
    plan = [{"type": "video", "path": "a.mp4", "start": 0, "end": 5}]
    out = _inject_cards(plan, None, None)
    assert out == plan
    assert out is not plan  # returns a fresh list, never mutates the input


def test_inject_intro_only():
    plan = [{"type": "photo", "path": "p.jpg", "duration": 4}]
    out = _inject_cards(plan, intro_path="intro.png", outro_path=None, duration=3)
    assert len(out) == 2
    assert out[0]["path"] == "intro.png"
    assert out[1] is plan[0]


def test_make_card_image_creates_png(tmp_path):
    from app.services import thumbnail_service
    out = tmp_path / "card.png"
    result = thumbnail_service.make_card_image(
        "Tatil Roma - Bolum 1", str(out), sub_text="Bolum 1")
    assert Path(result).exists()
    # Valid 1920x1080 image.
    from PIL import Image
    with Image.open(out) as img:
        assert img.size == (1920, 1080)


def test_make_card_image_handles_long_text(tmp_path):
    from app.services import thumbnail_service
    out = tmp_path / "long.png"
    long_title = "Bu cok uzun bir baslik " * 8
    result = thumbnail_service.make_card_image(long_title, str(out))
    assert Path(result).exists()
