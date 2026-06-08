"""Opt-in FFmpeg smoke tests — actually invoke ffmpeg on tiny generated media.

These are slow and require ffmpeg on PATH, so they are marked ``slow`` and
skipped by the default ``-m "not slow"`` run. Run explicitly with:
    pytest -m slow
All media is synthesised into a tmp dir; nothing is written under data/.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from app.config import FFMPEG_BIN
from app.services import ffmpeg_service, audio_mixer

pytestmark = pytest.mark.slow

_ffmpeg_missing = shutil.which("ffmpeg") is None and not Path(FFMPEG_BIN).exists()
skip_no_ffmpeg = pytest.mark.skipif(_ffmpeg_missing, reason="ffmpeg not on PATH")


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    d = tmp_path_factory.mktemp("smoke")

    img = d / "frame.png"
    subprocess.run(
        [FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:duration=1",
         "-frames:v", "1", str(img)],
        check=True, capture_output=True,
    )

    clips = []
    for i in range(2):
        c = d / f"clip{i}.mp4"
        subprocess.run(
            [FFMPEG_BIN, "-y",
             "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-ar", "48000", "-shortest", str(c)],
            check=True, capture_output=True,
        )
        clips.append(str(c))

    music = d / "music.mp3"
    subprocess.run(
        [FFMPEG_BIN, "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=3", str(music)],
        check=True, capture_output=True,
    )

    return {"dir": d, "img": str(img), "clips": clips, "music": str(music)}


@skip_no_ffmpeg
def test_create_slideshow(media):
    out = str(media["dir"] / "slideshow.mp4")
    ffmpeg_service.create_slideshow([media["img"]], out, duration_per_image=1.0)
    assert Path(out).exists()
    assert ffmpeg_service._get_duration(out) > 0.5


@skip_no_ffmpeg
def test_concat_with_demuxer(media):
    out = str(media["dir"] / "concat.mp4")
    ffmpeg_service._concat_with_demuxer(media["clips"], out)
    assert Path(out).exists()
    # Two ~2s clips -> ~4s total.
    assert ffmpeg_service._get_duration(out) >= 3.0


@skip_no_ffmpeg
def test_concat_with_xfade(media):
    out = str(media["dir"] / "xfade.mp4")
    ffmpeg_service._concat_with_xfade(media["clips"], out, "fade", 0.5, "320", "240")
    assert Path(out).exists()
    assert ffmpeg_service._get_duration(out) > 0


@skip_no_ffmpeg
def test_mix_with_music(media):
    out = str(media["dir"] / "mixed.mp4")
    audio_mixer.mix_with_music(
        media["clips"][0], media["music"], out,
        video_volume=0.6, music_volume=0.4,
    )
    assert Path(out).exists()
    assert ffmpeg_service._get_duration(out) > 0


@skip_no_ffmpeg
def test_detect_scenes_detailed_shape(media):
    from app.services import scene_detector
    scenes = scene_detector.detect_scenes_detailed(media["clips"][0], 2.0)
    assert isinstance(scenes, list) and scenes
    for s in scenes:
        assert {"start", "end", "luminance"} <= set(s.keys())
    assert scenes[0]["start"] == 0.0


@skip_no_ffmpeg
async def test_export_project_with_color_effect(media, tmp_path):
    """The any-effects path re-encodes the clip with an eq filter applied."""
    from app.services.ffmpeg_service import export_project

    clips = [{
        "media_path": media["clips"][0], "in_point": 0.0, "out_point": 1.5,
        "brightness": 0.1, "contrast": 1.2, "saturation": 1.1,
    }]
    out = str(tmp_path / "export_fx.mp4")
    await export_project(clips=clips, audio_tracks=[], subtitles=[], output_path=out)
    assert Path(out).exists()
    assert ffmpeg_service._get_duration(out) > 0


@skip_no_ffmpeg
async def test_export_project_with_transform(media, tmp_path):
    """hflip + 2x speed: output should be roughly half the source duration."""
    from app.services.ffmpeg_service import export_project

    clips = [{
        "media_path": media["clips"][0], "in_point": 0.0, "out_point": 2.0,
        "hflip": True, "speed": 2.0,
    }]
    out = str(tmp_path / "export_tf.mp4")
    await export_project(clips=clips, audio_tracks=[], subtitles=[], output_path=out)
    assert Path(out).exists()
    d = ffmpeg_service._get_duration(out)
    assert 0.5 < d < 1.8  # ~1s from a 2s source at 2x


@skip_no_ffmpeg
async def test_create_batch_video_parallel_orders_and_concats(media, tmp_path):
    """End-to-end: parallel segment encode + order-preserving concat."""
    from app.services import batch_service

    src = media["clips"][0]  # ~2s clip
    plan = [
        {"type": "video", "path": src, "start": 0.0, "end": 1.0},
        {"type": "video", "path": src, "start": 0.5, "end": 1.5},
        {"type": "video", "path": src, "start": 1.0, "end": 2.0},
    ]
    out = str(tmp_path / "batch_out.mp4")
    stats = await batch_service.create_batch_video(
        content_plan=plan, output_path=out,
        transition="none", transition_duration=0.5, resolution="320x240",
    )
    assert Path(out).exists()
    assert stats["rendered"] == 3
    assert stats["dropped"] == 0
    assert ffmpeg_service._get_duration(out) > 1.5
