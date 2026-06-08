"""Unit tests for the content planners (no FFmpeg / no rendering).

``pro_planner.build_plans`` normally shells out to ffmpeg for scene detection;
we monkeypatch ``scene_detector.detect_scenes`` with synthetic scenes so the
planning logic is exercised in isolation.
"""

import random

import pytest

from app.services import batch_service, pro_planner, scene_detector

from conftest import make_videos, make_photos


def _plan_duration(plan: list[dict]) -> float:
    return sum(
        (it["end"] - it["start"]) if it["type"] == "video" else it["duration"]
        for it in plan
    )


# --------------------------------------------------------------------------
# Legacy planner
# --------------------------------------------------------------------------

def test_plan_distribution_shape_and_bounds():
    random.seed(0)
    plans = batch_service.plan_content_distribution(
        videos=make_videos(3, 30.0), photos=make_photos(2),
        num_videos=2, target_duration=20.0,
        clip_duration=4.0, photo_duration=3.0,
    )
    assert len(plans) == 2
    for plan in plans:
        assert _plan_duration(plan) <= 20.0 + 1.5


def test_plan_distribution_videos_only():
    plans = batch_service.plan_content_distribution(
        videos=make_videos(2, 30.0), photos=[],
        num_videos=1, target_duration=12.0,
        clip_duration=3.0, photo_duration=3.0,
    )
    assert len(plans) == 1
    assert plans[0], "expected a non-empty plan when videos are available"
    assert all(it["type"] == "video" for it in plans[0])


def test_split_into_groups_conserves_items():
    groups = batch_service._split_into_groups(list(range(10)), 3)
    assert len(groups) == 3
    assert sum(len(g) for g in groups) == 10


def test_split_into_groups_empty():
    assert batch_service._split_into_groups([], 3) == [[], [], []]


def test_interleave_without_photos_is_identity():
    segs = [{"type": "video", "path": "a", "start": 0, "end": 3}]
    assert batch_service._interleave_content(segs, [], 3.0) == segs


# --------------------------------------------------------------------------
# Pro planner (scene detection monkeypatched)
# --------------------------------------------------------------------------

def _fake_scenes(path, duration, threshold=0.35, min_duration=1.5):
    return [
        {"start": 0.0, "end": 5.0, "luminance": 120},
        {"start": 5.0, "end": 10.0, "luminance": 120},
        {"start": 10.0, "end": 15.0, "luminance": 120},
        {"start": 15.0, "end": 20.0, "luminance": 120},
    ]


def test_build_plans_basic(monkeypatch):
    monkeypatch.setattr(scene_detector, "detect_scenes_detailed", _fake_scenes)
    random.seed(1)
    plans, meta = pro_planner.build_plans(
        videos=make_videos(2, 20.0), photos=make_photos(2),
        num_videos=2, target_duration=15.0, style="auto",
    )
    assert len(plans) == 2
    assert meta["style"] == "auto"
    assert meta["total_candidates"] > 0
    assert any(plan for plan in plans), "at least one plan should be non-empty"
    for plan in plans:
        assert _plan_duration(plan) <= 15.0 + 1.5


def test_build_plans_unknown_style_falls_back_to_auto(monkeypatch):
    monkeypatch.setattr(scene_detector, "detect_scenes_detailed", _fake_scenes)
    random.seed(2)
    _, meta = pro_planner.build_plans(
        videos=make_videos(1, 20.0), photos=[],
        num_videos=1, target_duration=10.0, style="does-not-exist",
    )
    assert meta["profile"] is pro_planner.STYLE_PROFILES["auto"]


def test_build_candidates_skips_tiny_scenes(monkeypatch):
    def tiny(path, duration, threshold=0.35, min_duration=1.5):
        # first scene < 1.5s should be dropped
        return [{"start": 0.0, "end": 0.5, "luminance": 100},
                {"start": 0.5, "end": 6.0, "luminance": 100}]
    monkeypatch.setattr(scene_detector, "detect_scenes_detailed", tiny)
    cands = pro_planner.build_candidates(make_videos(1, 6.0))
    assert len(cands) == 1
    assert cands[0]["scene"] == (0.5, 6.0)


# --------------------------------------------------------------------------
# Plan preview (scan + planners monkeypatched, no rendering)
# --------------------------------------------------------------------------

def _fake_scan(videos, photos, name="Trip"):
    return {
        "videos": videos, "photos": photos, "folder_name": name,
        "video_count": len(videos), "photo_count": len(photos),
        "total_video_duration": sum(v["duration"] for v in videos),
    }


@pytest.mark.asyncio
async def test_preview_plans_legacy(monkeypatch):
    scan = _fake_scan(make_videos(2, 30.0), make_photos(1))
    monkeypatch.setattr(batch_service, "scan_folder", lambda p: scan)
    out = await batch_service.preview_plans(
        folder_path="X", num_videos=2, target_duration=15.0,
        clip_duration=4.0, photo_duration=3.0, pro_settings={"enabled": False},
    )
    assert out["mode"] == "legacy"
    assert out["folder_name"] == "Trip"
    assert len(out["videos"]) == 2
    assert all("items" in v and "total_duration" in v for v in out["videos"])


@pytest.mark.asyncio
async def test_preview_plans_pro(monkeypatch):
    scan = _fake_scan(make_videos(2, 20.0), [])
    monkeypatch.setattr(batch_service, "scan_folder", lambda p: scan)
    monkeypatch.setattr(scene_detector, "detect_scenes_detailed", _fake_scenes)
    random.seed(3)
    out = await batch_service.preview_plans(
        folder_path="X", num_videos=2, target_duration=15.0,
        clip_duration=4.0, photo_duration=3.0,
        pro_settings={"enabled": True, "style": "auto"},
    )
    assert out["mode"] == "pro:auto"
    assert len(out["videos"]) == 2


@pytest.mark.asyncio
async def test_preview_plans_empty_folder_raises(monkeypatch):
    monkeypatch.setattr(batch_service, "scan_folder", lambda p: _fake_scan([], []))
    with pytest.raises(RuntimeError):
        await batch_service.preview_plans(
            folder_path="X", num_videos=1, target_duration=10.0,
            clip_duration=4.0, photo_duration=3.0, pro_settings=None,
        )


# --------------------------------------------------------------------------
# Content-aware scoring + scene cache format
# --------------------------------------------------------------------------

def test_score_prefers_well_exposed_scene():
    scene = (0.0, 6.0)
    dark = pro_planner._score_candidate(scene, 0, 1, luminance=10)
    good = pro_planner._score_candidate(scene, 0, 1, luminance=120)
    blown = pro_planner._score_candidate(scene, 0, 1, luminance=250)
    assert good > dark
    assert good > blown


def test_score_unknown_luminance_is_neutral():
    s = pro_planner._score_candidate((0.0, 6.0), 0, 1, luminance=None)
    assert 0.0 <= s <= 1.0


def test_scene_cache_backward_compat():
    # Old 2-element cache entries -> luminance None; new 3-element -> value.
    old = scene_detector._to_dicts([[0.0, 5.0], [5.0, 10.0]])
    assert old[0] == {"start": 0.0, "end": 5.0, "luminance": None}
    new = scene_detector._to_dicts([[0.0, 5.0, 120]])
    assert new[0]["luminance"] == 120
    assert scene_detector._to_cache(
        [{"start": 1.0, "end": 2.0, "luminance": 90}]
    ) == [[1.0, 2.0, 90]]
