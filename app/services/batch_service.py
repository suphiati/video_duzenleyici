import asyncio
import math
import os
import shutil
import subprocess
import uuid
from datetime import datetime
from pathlib import Path

from app.config import FFMPEG_BIN, TEMP_DIR, EXPORTS_DIR
from app.services.ffmpeg_service import (
    create_slideshow,
    _concat_with_demuxer,
    _concat_with_xfade,
    segment_encoder_args,
)
from app.services.folder_scanner import scan_folder
from app.services import (
    youtube_service,
    ai_service,
    pro_planner,
    music_library,
    beat_analyzer,
    audio_mixer,
    thumbnail_service,
)


# ---------------------------------------------------------------------------
# Plan preview (no rendering) — reuses the planners for a dry-run summary
# ---------------------------------------------------------------------------

async def preview_plans(
    folder_path: str,
    num_videos: int,
    target_duration: float,
    clip_duration: float,
    photo_duration: float,
    pro_settings: dict | None = None,
) -> dict:
    """Scan + plan without encoding, returning a per-output segment summary.

    Pro mode still runs scene detection (cached), but nothing is rendered.
    """
    scan_result = await asyncio.to_thread(scan_folder, folder_path)
    if not scan_result["videos"] and not scan_result["photos"]:
        raise RuntimeError("Klasorde video veya fotograf bulunamadi")

    pro_enabled = bool(pro_settings and pro_settings.get("enabled"))
    if pro_enabled:
        style = pro_settings.get("style", "auto")
        plans, meta = await asyncio.to_thread(
            pro_planner.build_plans,
            scan_result["videos"], scan_result["photos"],
            num_videos, target_duration, style, None, None,
        )
        mode = f"pro:{meta['style']}"
    else:
        plans = plan_content_distribution(
            videos=scan_result["videos"], photos=scan_result["photos"],
            num_videos=num_videos, target_duration=target_duration,
            clip_duration=clip_duration, photo_duration=photo_duration,
        )
        mode = "legacy"

    videos_summary = []
    for i, plan in enumerate(plans):
        items = []
        total = 0.0
        for it in plan:
            if it["type"] == "video":
                dur = round(it["end"] - it["start"], 2)
                items.append({"type": "video", "name": Path(it["path"]).name,
                              "start": it["start"], "end": it["end"], "duration": dur})
            else:
                dur = round(it.get("duration", 0.0), 2)
                items.append({"type": "photo", "name": Path(it["path"]).name,
                              "duration": dur})
            total += dur
        videos_summary.append({
            "index": i,
            "item_count": len(items),
            "total_duration": round(total, 1),
            "items": items,
        })

    return {
        "mode": mode,
        "folder_name": scan_result["folder_name"],
        "video_count": scan_result["video_count"],
        "photo_count": scan_result["photo_count"],
        "videos": videos_summary,
    }


# ---------------------------------------------------------------------------
# Legacy planner (used when pro mode is disabled)
# ---------------------------------------------------------------------------

def plan_content_distribution(
    videos: list[dict],
    photos: list[dict],
    num_videos: int,
    target_duration: float,
    clip_duration: float,
    photo_duration: float,
) -> list[list[dict]]:
    plans = [[] for _ in range(num_videos)]
    video_groups = _split_into_groups(videos, num_videos)
    photo_groups = _split_into_groups(photos, num_videos)

    for i in range(num_videos):
        group_videos = video_groups[i]
        group_photos = photo_groups[i]

        photo_total_time = len(group_photos) * photo_duration
        video_target_time = target_duration - photo_total_time
        if video_target_time < target_duration * 0.5:
            video_target_time = target_duration * 0.7
            photo_total_time = target_duration * 0.3

        video_segments = _plan_video_segments(group_videos, video_target_time, clip_duration)
        plan = _interleave_content(video_segments, group_photos, photo_duration)

        accumulated = 0.0
        trimmed_plan = []
        for item in plan:
            item_dur = (item["end"] - item["start"]) if item["type"] == "video" else item["duration"]
            if accumulated + item_dur > target_duration + 1:
                remaining = target_duration - accumulated
                if remaining > 0.5:
                    if item["type"] == "video":
                        item["end"] = item["start"] + remaining
                    else:
                        item["duration"] = remaining
                    trimmed_plan.append(item)
                break
            trimmed_plan.append(item)
            accumulated += item_dur

        plans[i] = trimmed_plan

    return plans


def _split_into_groups(items: list, n: int) -> list[list]:
    if not items:
        return [[] for _ in range(n)]
    groups = []
    size = len(items)
    base = size // n
    remainder = size % n
    start = 0
    for i in range(n):
        chunk = base + (1 if i < remainder else 0)
        groups.append(items[start:start + chunk])
        start += chunk
    return groups


def _plan_video_segments(videos: list[dict], target_time: float, clip_duration: float) -> list[dict]:
    if not videos:
        return []
    segments = []
    num_segments_needed = max(1, math.ceil(target_time / clip_duration))
    num_videos = len(videos)
    for seg_idx in range(num_segments_needed):
        src_idx = seg_idx % num_videos
        src = videos[src_idx]
        src_dur = src["duration"]
        existing = [s for s in segments if s["path"] == src["path"]]
        n_existing = len(existing)
        available_dur = src_dur - clip_duration
        if available_dur <= 0:
            start, end = 0.0, min(src_dur, clip_duration)
        else:
            step = available_dur / max(1, math.ceil(num_segments_needed / num_videos))
            start = (n_existing * step) % available_dur
            end = start + clip_duration
            if end > src_dur:
                start = max(0.0, src_dur - clip_duration)
                end = src_dur
        segments.append({
            "type": "video", "path": src["path"],
            "start": round(start, 2), "end": round(end, 2),
        })
    return segments


def _interleave_content(video_segments: list[dict], photos: list[dict],
                        photo_duration: float) -> list[dict]:
    if not photos:
        return video_segments
    if not video_segments:
        return [{"type": "photo", "path": p["path"], "duration": photo_duration} for p in photos]
    result = []
    insert_interval = max(1, len(video_segments) // (len(photos) + 1))
    photo_idx = 0
    for i, seg in enumerate(video_segments):
        result.append(seg)
        if (i + 1) % insert_interval == 0 and photo_idx < len(photos):
            result.append({"type": "photo", "path": photos[photo_idx]["path"],
                           "duration": photo_duration})
            photo_idx += 1
    while photo_idx < len(photos):
        result.append({"type": "photo", "path": photos[photo_idx]["path"],
                       "duration": photo_duration})
        photo_idx += 1
    return result


# ---------------------------------------------------------------------------
# Blocking helpers
# ---------------------------------------------------------------------------

def _build_segment_cmd(item: dict, temp_path: str, w: str, h: str,
                       encoder_args: list[str]) -> list[str]:
    seg_dur = item["end"] - item["start"]
    return [
        FFMPEG_BIN, "-y",
        "-ss", str(item["start"]),
        "-t", str(seg_dur),
        "-i", item["path"],
        "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
        *encoder_args,
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        temp_path,
    ]


def _encode_video_segment(item: dict, temp_path: str, w: str, h: str) -> bool:
    encoder_args = segment_encoder_args(20)
    cmd = _build_segment_cmd(item, temp_path, w, h, encoder_args)
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode == 0:
        return True
    # A validated GPU encoder can still fail on a specific input — retry on CPU
    # so one awkward clip doesn't drop a segment from the plan.
    if encoder_args[:2] != ["-c:v", "libx264"]:
        cpu_cmd = _build_segment_cmd(
            item, temp_path, w, h,
            ["-c:v", "libx264", "-preset", "fast", "-crf", "20"],
        )
        cpu_result = subprocess.run(cpu_cmd, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace")
        return cpu_result.returncode == 0
    return False


def _encode_photo_segment(item: dict, temp_path: str) -> bool:
    try:
        create_slideshow(
            images=[item["path"]],
            output_path=temp_path,
            duration_per_image=item["duration"],
            transition="fade",
            transition_duration=0.5,
        )
        return True
    except Exception:
        return False


def _segment_concurrency() -> int:
    """How many segment encodes to run at once.

    A GPU encoder is a single hardware session, so keep it serial. On CPU,
    libx264 is already multithreaded — use a small pool to overlap process
    startup without oversubscribing the cores.
    """
    from app.services.ffmpeg_service import detect_gpu_encoder
    if detect_gpu_encoder():
        return 1
    return max(1, min(3, (os.cpu_count() or 2) // 2))


class BatchCancelled(Exception):
    """Raised when a cancel is requested mid-render."""


async def create_batch_video(
    content_plan: list[dict],
    output_path: str,
    transition: str,
    transition_duration: float,
    resolution: str = "1920x1080",
    progress_callback=None,
    cancel_event: asyncio.Event = None,
) -> dict:
    """Render one batch video from a content plan. FFmpeg runs in a thread.

    Returns render stats ``{output_path, total, rendered, dropped}``. Raises
    ``BatchCancelled`` if ``cancel_event`` is set between segments.
    """
    w, h = resolution.split("x")
    temp_clips: list[str] = []
    temp_files: list[str] = []
    batch_id = str(uuid.uuid4())[:8]
    dropped = 0

    try:
        total_items = len(content_plan)
        sem = asyncio.Semaphore(_segment_concurrency())
        rendered_by_index: dict[int, str] = {}
        progress_state = {"done": 0, "dropped": 0}

        async def _encode_item(idx: int, plan_item: dict):
            if cancel_event and cancel_event.is_set():
                raise BatchCancelled()
            async with sem:
                if cancel_event and cancel_event.is_set():
                    raise BatchCancelled()
                if plan_item["type"] == "video":
                    tp = str(TEMP_DIR / f"batch_{batch_id}_seg_{idx}.mp4")
                    ok = await asyncio.to_thread(_encode_video_segment, plan_item, tp, w, h)
                elif plan_item["type"] == "photo":
                    tp = str(TEMP_DIR / f"batch_{batch_id}_photo_{idx}.mp4")
                    ok = await asyncio.to_thread(_encode_photo_segment, plan_item, tp)
                else:
                    return
                if ok:
                    temp_files.append(tp)
                    rendered_by_index[idx] = tp
                else:
                    progress_state["dropped"] += 1
            progress_state["done"] += 1
            if progress_callback:
                await progress_callback((progress_state["done"] / max(1, total_items)) * 75)

        tasks = [asyncio.create_task(_encode_item(i, item))
                 for i, item in enumerate(content_plan)]
        try:
            await asyncio.gather(*tasks)
        except BaseException:
            for t in tasks:
                t.cancel()
            raise

        dropped = progress_state["dropped"]
        # Concat in original plan order regardless of completion order.
        temp_clips = [rendered_by_index[i] for i in sorted(rendered_by_index)]

        if not temp_clips:
            raise RuntimeError("Hicbir klip olusturulamadi")

        if len(temp_clips) == 1:
            await asyncio.to_thread(shutil.copy2, temp_clips[0], output_path)
        elif transition != "none" and 4 <= len(temp_clips) <= 20:
            await asyncio.to_thread(_concat_with_xfade, temp_clips, output_path,
                                    transition, transition_duration, w, h)
        else:
            await asyncio.to_thread(_concat_with_demuxer, temp_clips, output_path)

        if progress_callback:
            await progress_callback(85)

        return {
            "output_path": output_path,
            "total": total_items,
            "rendered": len(temp_clips),
            "dropped": dropped,
        }
    finally:
        for tf in temp_files:
            try:
                Path(tf).unlink(missing_ok=True)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Pro pipeline glue
# ---------------------------------------------------------------------------

def _select_music(profile: dict, settings: dict, used: set[str]) -> dict | None:
    mode = (settings or {}).get("music_mode", "auto")
    if mode == "none":
        return None
    if mode == "specific":
        path = (settings or {}).get("music_path")
        if not path or not Path(path).exists():
            return None
        return {"path": path, "mood": "custom"}
    # auto: pick from library, prefer profile mood
    track = music_library.pick_track(
        preferred_mood=profile.get("prefer_mood"),
        exclude=used,
    )
    return track


def _analyze_beats_sync(music_path: str) -> tuple[list[float] | None, float | None]:
    info = beat_analyzer.analyze(music_path)
    if not info:
        return None, None
    return info.beats, info.tempo


async def _build_pro_plans(
    scan_result: dict,
    num_videos: int,
    target_duration: float,
    pro_settings: dict,
    send_message,
):
    """Run scene detection + beat analysis, return (plans, meta, music_pick)."""
    profile = pro_planner.get_profile(pro_settings.get("style", "auto"))

    # Music pre-selection so beat analysis can feed into planning.
    music_pick = _select_music(profile, pro_settings, used=set())

    beats: list[float] | None = None
    tempo: float | None = None
    if music_pick and profile.get("beat_sync"):
        if beat_analyzer.is_available():
            await send_message({"type": "pro_status",
                                "message": f"Muzik ritmi analiz ediliyor: {Path(music_pick['path']).name}"})
            beats, tempo = await asyncio.to_thread(_analyze_beats_sync, music_pick["path"])
        else:
            # The chosen style wants beat-sync but librosa is missing — tell the
            # user instead of silently falling back to linear spacing.
            await send_message({
                "type": "pro_status",
                "message": "Ritim senkronu icin librosa yuklu degil; "
                           "duz aralikli kesim kullanilacak "
                           "(pip install -r requirements-pro.txt).",
            })

    await send_message({"type": "pro_status",
                        "message": "Sahneler tespit ediliyor..."})
    plans, meta = await asyncio.to_thread(
        pro_planner.build_plans,
        scan_result["videos"],
        scan_result["photos"],
        num_videos,
        target_duration,
        pro_settings.get("style", "auto"),
        beats,
        tempo,
    )

    await send_message({
        "type": "pro_status",
        "style": meta["style"],
        "candidates": meta["total_candidates"],
        "tempo": meta.get("tempo"),
        "music": Path(music_pick["path"]).name if music_pick else None,
    })
    return plans, meta, music_pick


async def _apply_music_track(
    raw_path: str,
    final_path: str,
    music_path: str,
    profile: dict,
    overrides: dict,
) -> None:
    # Explicit None checks so a deliberate 0.0 (mute) is honoured instead of
    # being silently replaced by the profile default.
    ov_video = overrides.get("original_audio_volume")
    ov_music = overrides.get("music_volume")
    video_vol = ov_video if ov_video is not None else profile.get("original_audio_volume", 0.55)
    music_vol = ov_music if ov_music is not None else profile.get("music_volume", 0.45)
    await asyncio.to_thread(
        audio_mixer.mix_with_music,
        raw_path, music_path, final_path,
        float(video_vol), float(music_vol),
    )


# ---------------------------------------------------------------------------
# Intro / outro title cards
# ---------------------------------------------------------------------------

def _inject_cards(
    plan: list[dict],
    intro_path: str | None = None,
    outro_path: str | None = None,
    duration: float = 2.5,
) -> list[dict]:
    """Wrap a content plan with intro/outro card photo items.

    Cards are plain stills rendered to PNG, so they ride the existing photo
    encode path (``_encode_photo_segment`` -> slideshow) and match the batch
    render format automatically.
    """
    new_plan: list[dict] = []
    if intro_path:
        new_plan.append({"type": "photo", "path": intro_path, "duration": duration})
    new_plan.extend(plan)
    if outro_path:
        new_plan.append({"type": "photo", "path": outro_path, "duration": duration})
    return new_plan


def _render_cards(
    card_settings: dict | None,
    title: str,
    part_number: int,
) -> tuple[str | None, str | None, list[str]]:
    """Render the intro/outro PNGs for one video. Returns (intro, outro, temps)."""
    cs = card_settings or {}
    intro_path: str | None = None
    outro_path: str | None = None
    temps: list[str] = []

    if cs.get("intro", True):
        intro_text = (cs.get("intro_text") or "").strip() or title
        path = str(TEMP_DIR / f"card_intro_{uuid.uuid4().hex[:8]}.png")
        try:
            thumbnail_service.make_card_image(
                intro_text, path, sub_text=f"Bolum {part_number}")
            intro_path = path
            temps.append(path)
        except Exception:
            intro_path = None

    if cs.get("outro", True):
        # No "subscribe" CTA by request — a neutral closing line only.
        outro_text = (cs.get("outro_text") or "").strip() or "Izlediginiz icin tesekkurler"
        path = str(TEMP_DIR / f"card_outro_{uuid.uuid4().hex[:8]}.png")
        try:
            thumbnail_service.make_card_image(outro_text, path)
            outro_path = path
            temps.append(path)
        except Exception:
            outro_path = None

    return intro_path, outro_path, temps


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

async def _build_metadata(
    folder_name: str,
    part_number: int,
    total_parts: int,
    target_duration: float,
    youtube_settings: dict,
    ai_settings: dict | None,
) -> tuple[str, str, list[str]]:
    default_title = youtube_settings.get(
        "title_template", "{folder_name} - Bolum {part_number}"
    ).format(folder_name=folder_name, part_number=part_number)
    default_desc = youtube_settings.get("description", "") or ""
    default_tags = list(youtube_settings.get("tags", []) or [])

    if not ai_settings or not ai_settings.get("enabled"):
        return default_title, default_desc, default_tags

    meta = await ai_service.generate_metadata(
        folder_name=folder_name,
        part_number=part_number,
        total_parts=total_parts,
        duration_seconds=target_duration,
        language=ai_settings.get("language", "tr"),
        model=ai_settings.get("model"),
        provider=ai_settings.get("provider", "auto"),
    )
    if not meta:
        return default_title, default_desc, default_tags

    description = meta.description
    if ai_settings.get("append_default_description", True) and default_desc.strip():
        description = f"{description}\n\n{default_desc}".strip()

    merged: list[str] = []
    for t in default_tags + meta.tags:
        t_clean = t.strip()
        if t_clean and t_clean.lower() not in {m.lower() for m in merged}:
            merged.append(t_clean)
        if len(merged) >= 25:
            break

    return meta.title, description, merged


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

async def run_batch(
    folder_path: str,
    num_videos: int,
    target_duration: float,
    clip_duration: float,
    photo_duration: float,
    transition: str,
    transition_duration: float,
    shuffle: bool,
    upload_to_youtube: bool,
    youtube_settings: dict,
    send_message,
    cancel_event: asyncio.Event = None,
    ai_settings: dict | None = None,
    pro_settings: dict | None = None,
    auto_thumbnail: bool = True,
    card_settings: dict | None = None,
):
    await send_message({"type": "status", "message": "Klasor taraniyor..."})
    scan_result = await asyncio.to_thread(scan_folder, folder_path)

    if not scan_result["videos"] and not scan_result["photos"]:
        raise RuntimeError("Klasorde video veya fotograf bulunamadi")

    folder_name = scan_result["folder_name"]
    await send_message({
        "type": "scan_complete",
        "folder_name": folder_name,
        "video_count": scan_result["video_count"],
        "photo_count": scan_result["photo_count"],
        "total_duration": scan_result["total_video_duration"],
    })

    pro_enabled = bool(pro_settings and pro_settings.get("enabled"))
    pro_meta: dict = {}
    pro_music_pick: dict | None = None
    pro_profile: dict | None = None

    if pro_enabled:
        plans, pro_meta, pro_music_pick = await _build_pro_plans(
            scan_result, num_videos, target_duration, pro_settings, send_message,
        )
        pro_profile = pro_meta["profile"]
        # Pro mode overrides transition defaults
        transition = pro_profile["transition"]
        transition_duration = pro_profile["transition_duration"]
    else:
        plans = plan_content_distribution(
            videos=scan_result["videos"],
            photos=scan_result["photos"],
            num_videos=num_videos,
            target_duration=target_duration,
            clip_duration=clip_duration,
            photo_duration=photo_duration,
        )

    ai_active = False
    if ai_settings and ai_settings.get("enabled"):
        ai_backend = await ai_service.resolve_backend(
            ai_settings.get("provider", "auto"), ai_settings.get("model"))
        ai_active = ai_backend is not None
        if not ai_active:
            await send_message({
                "type": "ai_status",
                "available": False,
                "message": "AI saglayici yok (Ollama/Claude/OpenAI), "
                           "sablon basliklar kullanilacak.",
            })
        else:
            await send_message({
                "type": "ai_status",
                "available": True,
                "provider": ai_backend.provider,
                "model": ai_backend.model,
            })

    await send_message({
        "type": "started",
        "total_videos": num_videos,
        "folder_name": folder_name,
    })

    results = []
    loop = asyncio.get_running_loop()
    used_music: set[str] = set()
    if pro_music_pick:
        used_music.add(pro_music_pick["path"])

    for i in range(num_videos):
        if cancel_event and cancel_event.is_set():
            await send_message({"type": "cancelled", "completed_count": len(results)})
            return results

        plan = plans[i]
        if not plan:
            await send_message({
                "type": "video_status", "index": i, "status": "error",
                "error": "Bu video icin yeterli icerik yok",
            })
            continue

        title, description, tags = await _build_metadata(
            folder_name=folder_name,
            part_number=i + 1,
            total_parts=num_videos,
            target_duration=target_duration,
            youtube_settings=youtube_settings,
            ai_settings=ai_settings if ai_active else None,
        )

        await send_message({
            "type": "video_status", "index": i, "status": "creating",
            "title": title, "progress": 0,
        })

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in folder_name)
        output_path = str(EXPORTS_DIR / f"{safe_name}_B{i+1}_{timestamp}.mp4")

        async def creation_progress(percent, idx=i):
            await send_message({
                "type": "video_status", "index": idx, "status": "creating",
                "progress": round(percent, 1),
            })

        # Intro/outro title cards (no subscribe CTA) wrap the content plan.
        intro_card, outro_card, card_temps = _render_cards(
            card_settings, title, i + 1)
        card_dur = float((card_settings or {}).get("duration", 2.5) or 2.5)
        plan_to_render = _inject_cards(plan, intro_card, outro_card, card_dur)

        # Render to a raw path first so we can post-mix music if pro mode is on.
        render_target = output_path
        raw_path: str | None = None
        music_for_this: dict | None = None
        if pro_enabled and pro_profile and pro_settings.get("music_mode") != "none":
            # Pick music per-video (first one was picked for beat analysis).
            if i == 0 and pro_music_pick:
                music_for_this = pro_music_pick
            elif pro_meta.get("beats_available") and pro_music_pick:
                # Plans were beat-synced to this track's tempo — reuse the same
                # track across the batch so the cuts actually land on the beat.
                music_for_this = pro_music_pick
            else:
                music_for_this = _select_music(pro_profile, pro_settings, used=used_music)
            if music_for_this:
                used_music.add(music_for_this["path"])
                raw_path = str(TEMP_DIR / f"batch_raw_{uuid.uuid4().hex[:8]}.mp4")
                render_target = raw_path

        try:
            render_stats = await create_batch_video(
                content_plan=plan_to_render,
                output_path=render_target,
                transition=transition,
                transition_duration=transition_duration,
                progress_callback=creation_progress,
                cancel_event=cancel_event,
            )

            if raw_path and music_for_this and pro_profile:
                await send_message({
                    "type": "video_status", "index": i, "status": "creating",
                    "progress": 88,
                })
                try:
                    await _apply_music_track(
                        raw_path=raw_path,
                        final_path=output_path,
                        music_path=music_for_this["path"],
                        profile=pro_profile,
                        overrides=pro_settings or {},
                    )
                finally:
                    try:
                        Path(raw_path).unlink(missing_ok=True)
                    except Exception:
                        pass
        except BatchCancelled:
            # Drop the half-written output and report a clean cancel.
            try:
                Path(render_target).unlink(missing_ok=True)
            except Exception:
                pass
            await send_message({"type": "cancelled", "completed_count": len(results)})
            return results
        except Exception as e:
            await send_message({
                "type": "video_status", "index": i, "status": "error",
                "error": f"Video olusturma hatasi: {str(e)}",
            })
            continue
        finally:
            # Card stills are only needed during the render — clean them up.
            for _c in card_temps:
                try:
                    Path(_c).unlink(missing_ok=True)
                except Exception:
                    pass

        dropped = render_stats.get("dropped", 0) if isinstance(render_stats, dict) else 0
        if dropped:
            await send_message({
                "type": "video_status", "index": i, "status": "creating",
                "title": title, "progress": 90,
                "warning": f"{dropped} segment kodlanamadi ve atlandi",
            })

        video_result = {
            "index": i, "title": title,
            "output_path": output_path, "youtube_url": "",
            "dropped_segments": dropped,
        }

        # Best-frame thumbnail with a title overlay (uploaded with the video).
        thumb_path: str | None = None
        if auto_thumbnail:
            candidate = str(Path(output_path).with_suffix(".jpg"))
            try:
                made = await asyncio.to_thread(
                    thumbnail_service.generate_youtube_thumbnail,
                    output_path, candidate, title, f"Bolum {i+1}",
                )
                thumb_path = str(made) if made else None
            except Exception:
                thumb_path = None
        if thumb_path:
            video_result["thumbnail_path"] = thumb_path

        if upload_to_youtube:
            await send_message({
                "type": "video_status", "index": i, "status": "uploading",
                "title": title, "progress": 0,
            })

            def progress_bridge(percent, idx=i):
                fut = asyncio.run_coroutine_threadsafe(
                    send_message({
                        "type": "video_status", "index": idx,
                        "status": "uploading", "progress": round(percent, 1),
                    }),
                    loop,
                )
                try:
                    fut.result(timeout=5)
                except Exception:
                    pass

            try:
                youtube_url = await asyncio.to_thread(
                    youtube_service.upload_video,
                    file_path=output_path,
                    title=title,
                    description=description,
                    tags=tags,
                    privacy=youtube_settings.get("privacy", "private"),
                    category_id=youtube_settings.get("category_id", "22"),
                    progress_callback=progress_bridge,
                    thumbnail=thumb_path,
                )
                video_result["youtube_url"] = youtube_url
                await send_message({
                    "type": "video_status", "index": i, "status": "completed",
                    "title": title, "youtube_url": youtube_url,
                    "output_path": output_path, "thumbnail_path": thumb_path,
                })
            except Exception as e:
                await send_message({
                    "type": "video_status", "index": i, "status": "upload_error",
                    "title": title, "error": f"YouTube yukleme hatasi: {str(e)}",
                    "output_path": output_path,
                })
        else:
            await send_message({
                "type": "video_status", "index": i, "status": "completed",
                "title": title, "output_path": output_path,
                "thumbnail_path": thumb_path,
            })

        results.append(video_result)

    await send_message({
        "type": "batch_completed",
        "total": num_videos,
        "completed": len(results),
        "results": results,
    })
    return results
