import subprocess
import os
import re
from pathlib import Path

from app.config import FFMPEG_BIN, TEMP_DIR, YOUTUBE_EXPORT_SETTINGS

# ---------------------------------------------------------------------------
# GPU encoder detection (cached)
# ---------------------------------------------------------------------------
_gpu_encoder_cache: str | None = "__unset__"


def detect_gpu_encoder() -> str | None:
    """Detect available GPU encoder (cached after first call)."""
    global _gpu_encoder_cache
    if _gpu_encoder_cache != "__unset__":
        return _gpu_encoder_cache

    result = subprocess.run(
        [FFMPEG_BIN, "-hide_banner", "-encoders"],
        capture_output=True, text=True
    )
    for encoder in ["h264_nvenc", "h264_amf", "h264_qsv"]:
        if encoder in result.stdout:
            _gpu_encoder_cache = encoder
            return _gpu_encoder_cache
    _gpu_encoder_cache = None
    return _gpu_encoder_cache


def trim_clip(input_path: str, output_path: str, in_point: float, out_point: float):
    """Trim a clip using stream copy (fast, no re-encoding)."""
    cmd = [FFMPEG_BIN, "-y", "-i", input_path]
    if in_point > 0:
        cmd.extend(["-ss", str(in_point)])
    if out_point > 0:
        # out_point is absolute time; duration = out_point - in_point
        cmd.extend(["-t", str(out_point - in_point)])
    # out_point == -1 means "rest of file from in_point" -- no -t needed
    cmd.extend(["-c", "copy", "-avoid_negative_ts", "make_zero", output_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg trim hatasi: {result.stderr[-500:]}")


def concat_clips(clip_paths: list[str], output_path: str) -> str:
    """Concatenate clips using concat demuxer."""
    list_file = TEMP_DIR / "concat_list.txt"
    with open(list_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            safe = p.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    cmd = [
        FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file), "-c", "copy", output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat hatasi: {result.stderr[-500:]}")
    return output_path


async def export_project(
    clips: list[dict],
    audio_tracks: list[dict],
    subtitles: list[dict],
    output_path: str,
    progress_callback=None,
    cancel_event=None,
):
    """Full export pipeline: trim + concat + audio mix + subtitles."""
    import asyncio
    settings = YOUTUBE_EXPORT_SETTINGS
    temp_files: list[str] = []

    try:
        # Step 1: Trim clips
        trimmed_paths = []
        for i, clip in enumerate(clips):
            media_path = clip["media_path"]
            if not Path(media_path).exists():
                raise RuntimeError(f"Klip dosyasi bulunamadi: {media_path}")
            trimmed = str(TEMP_DIR / f"trimmed_{i}.mp4")
            if clip.get("in_point", 0) > 0 or clip.get("out_point", -1) > 0:
                trim_clip(media_path, trimmed, clip.get("in_point", 0), clip.get("out_point", -1))
                temp_files.append(trimmed)
            else:
                trimmed = media_path
            trimmed_paths.append(trimmed)

        # Step 2: Build FFmpeg command
        if len(trimmed_paths) == 1 and not audio_tracks and not subtitles:
            input_file = trimmed_paths[0]
        elif len(trimmed_paths) > 1:
            concat_out = str(TEMP_DIR / "concat_out.mp4")
            concat_clips(trimmed_paths, concat_out)
            temp_files.append(concat_out)
            input_file = concat_out
        else:
            input_file = trimmed_paths[0]

        # Build complex filter if needed
        cmd = [FFMPEG_BIN, "-y", "-i", input_file]
        filter_complex = []
        audio_inputs = []

        # Audio tracks
        for j, at in enumerate(audio_tracks):
            cmd.extend(["-i", at["media_path"]])
            audio_inputs.append(j + 1)

        # Determine encoder
        gpu_enc = detect_gpu_encoder()

        needs_filter = bool(audio_tracks) or bool(subtitles)

        if needs_filter:
            vfilter_parts = []

            # Subtitle filter
            if subtitles:
                ass_path = str(TEMP_DIR / "subs.ass")
                _generate_ass(subtitles, ass_path)
                temp_files.append(ass_path)
                # Escape backslashes and single quotes for the ASS filter path
                escaped_ass = ass_path.replace("\\", "/").replace(":", "\\:")
                vfilter_parts.append(f"ass='{escaped_ass}'")

            # Scale to target resolution
            w, h = settings["resolution"].split("x")
            vfilter_parts.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease")
            vfilter_parts.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
            vfilter_parts.append(f"format={settings['pixel_format']}")

            cmd.extend(["-vf", ",".join(vfilter_parts)])

            # Audio mixing
            if audio_tracks:
                audio_filter = f"[0:a]volume=1.0[a0];"
                for j, at in enumerate(audio_tracks):
                    vol = at.get("volume", 1.0)
                    fade_in = at.get("fade_in", 0)
                    fade_out = at.get("fade_out", 0)
                    af = f"[{j+1}:a]volume={vol}"
                    if fade_in > 0:
                        af += f",afade=t=in:d={fade_in}"
                    if fade_out > 0:
                        af += f",afade=t=out:d={fade_out}"
                    af += f"[a{j+1}];"
                    audio_filter += af
                inputs = "".join(f"[a{k}]" for k in range(len(audio_tracks) + 1))
                audio_filter += f"{inputs}amix=inputs={len(audio_tracks)+1}:duration=longest[aout]"
                cmd.extend(["-filter_complex", audio_filter, "-map", "0:v", "-map", "[aout]"])
            else:
                cmd.extend(["-map", "0:v", "-map", "0:a?"])

            # Encoder settings
            encoder = gpu_enc or settings["video_codec"]
            cmd.extend([
                "-c:v", encoder,
                "-b:v", settings["video_bitrate"],
                "-c:a", settings["audio_codec"],
                "-b:a", settings["audio_bitrate"],
                "-ar", str(settings["audio_sample_rate"]),
            ])
            if encoder == "libx264":
                cmd.extend([
                    "-preset", settings["preset"],
                    "-profile:v", settings["profile"],
                    "-level", settings["level"],
                ])
            cmd.extend(["-g", str(settings["keyint"]), "-movflags", "+faststart"])
        else:
            # Simple re-encode to YouTube specs
            w, h = settings["resolution"].split("x")
            encoder = gpu_enc or settings["video_codec"]
            cmd.extend([
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,format={settings['pixel_format']}",
                "-c:v", encoder,
                "-b:v", settings["video_bitrate"],
                "-c:a", settings["audio_codec"],
                "-b:a", settings["audio_bitrate"],
                "-ar", str(settings["audio_sample_rate"]),
                "-g", str(settings["keyint"]),
                "-movflags", "+faststart",
            ])
            if encoder == "libx264":
                cmd.extend([
                    "-preset", settings["preset"],
                    "-profile:v", settings["profile"],
                    "-level", settings["level"],
                ])

        cmd.append(output_path)

        # Run with progress tracking using Popen for real-time output
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, encoding="utf-8", errors="replace"
        )

        while True:
            if cancel_event and cancel_event.is_set():
                proc.kill()
                proc.wait()
                raise RuntimeError("Export iptal edildi")
            line = proc.stderr.readline()
            if not line and proc.poll() is not None:
                break
            time_match = re.findall(r"time=(\d{2}):(\d{2}):(\d{2})\.(\d{2})", line)
            if time_match and progress_callback:
                h_val, m_val, s_val, cs_val = time_match[-1]
                current = int(h_val) * 3600 + int(m_val) * 60 + int(s_val) + int(cs_val) / 100
                await progress_callback(current)
            # Yield control to event loop
            await asyncio.sleep(0)

        if proc.returncode != 0:
            stderr_remaining = proc.stderr.read()
            raise RuntimeError(f"Export hatasi: {stderr_remaining[-500:]}")
        return output_path

    finally:
        # Clean up temp files
        for tf in temp_files:
            try:
                Path(tf).unlink(missing_ok=True)
            except Exception:
                pass


def create_slideshow(
    images: list[str],
    output_path: str,
    duration_per_image: float = 5.0,
    transition: str = "fade",
    transition_duration: float = 1.0,
):
    """Create a slideshow video from images with transitions."""
    if len(images) < 1:
        raise ValueError("En az 1 resim gerekli")

    cmd = [FFMPEG_BIN, "-y"]
    filter_parts = []

    for i, img in enumerate(images):
        cmd.extend(["-loop", "1", "-t", str(duration_per_image), "-i", img])
        filter_parts.append(
            f"[{i}:v]scale=1920:1080:force_original_aspect_ratio=decrease,"
            f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p[v{i}]"
        )

    if len(images) == 1:
        filter_str = filter_parts[0]
        cmd.extend(["-filter_complex", filter_str, "-map", f"[v0]"])
    else:
        xfade_chain = f"[v0]"
        for i in range(1, len(images)):
            offset = i * duration_per_image - transition_duration * i
            if offset < 0:
                offset = 0
            out_label = f"xf{i}" if i < len(images) - 1 else "vout"
            filter_parts.append(
                f"{xfade_chain}[v{i}]xfade=transition={transition}:"
                f"duration={transition_duration}:offset={offset}[{out_label}]"
            )
            xfade_chain = f"[{out_label}]"

        filter_str = ";".join(filter_parts)
        cmd.extend(["-filter_complex", filter_str, "-map", "[vout]"])

    cmd.extend([
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        output_path
    ])

    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"Slayt gosterisi hatasi: {result.stderr[-500:]}")

    # Add silent audio track for browser compatibility
    temp_out = output_path + ".tmp.mp4"
    import shutil
    shutil.move(output_path, temp_out)
    try:
        add_audio_cmd = [
            FFMPEG_BIN, "-y",
            "-i", temp_out,
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
            "-shortest", "-movflags", "+faststart",
            output_path
        ]
        result2 = subprocess.run(add_audio_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if result2.returncode != 0:
            raise RuntimeError(f"Ses ekleme hatasi: {result2.stderr[-500:]}")
    finally:
        try:
            Path(temp_out).unlink(missing_ok=True)
        except Exception:
            pass
    return output_path


def create_video_mix(
    video_infos: list[dict],
    target_duration: float,
    clip_duration: float,
    transition: str,
    transition_duration: float,
    shuffle: bool,
    resolution: str,
    output_path: str,
) -> dict:
    """
    Create a video mix/montage from multiple source videos.

    Cuts segments from each video, optionally shuffles them, and concatenates
    with transitions to create a montage of the requested duration.

    Args:
        video_infos: list of {"path": str, "duration": float}
        target_duration: desired output duration in seconds
        clip_duration: how long each segment should be
        transition: xfade transition type (fade, dissolve, wipeleft, etc.)
        transition_duration: transition duration in seconds
        shuffle: randomize segment order
        resolution: output resolution e.g. "1920x1080"
        output_path: where to save the final video

    Returns:
        {"segments": [...], "total_duration": float}
    """
    import random
    import math

    w, h = resolution.split("x")

    # ── 1. Plan segments ──
    # Distribute target_duration across source videos
    num_videos = len(video_infos)
    num_segments_needed = math.ceil(target_duration / clip_duration)

    segments = []  # list of {"path", "start", "end", "source_idx"}

    # Round-robin across videos to pick segments
    for seg_idx in range(num_segments_needed):
        src_idx = seg_idx % num_videos
        src = video_infos[src_idx]
        src_dur = src["duration"]

        # How many segments have we already picked from this source?
        existing = [s for s in segments if s["source_idx"] == src_idx]
        n_existing = len(existing)

        # Calculate start time: spread segments evenly across the source
        # Avoid picking the same region twice
        available_dur = src_dur - clip_duration
        if available_dur <= 0:
            # Source is shorter than clip_duration, use full source
            start = 0
            end = min(src_dur, clip_duration)
        else:
            # Spread evenly
            step = available_dur / max(1, math.ceil(num_segments_needed / num_videos))
            start = (n_existing * step) % available_dur
            end = start + clip_duration
            if end > src_dur:
                start = max(0, src_dur - clip_duration)
                end = src_dur

        segments.append({
            "path": src["path"],
            "start": round(start, 2),
            "end": round(end, 2),
            "source_idx": src_idx,
        })

    if shuffle:
        random.shuffle(segments)

    # Trim total to target_duration
    accumulated = 0
    trimmed_segments = []
    for seg in segments:
        seg_dur = seg["end"] - seg["start"]
        if accumulated + seg_dur > target_duration + 1:
            # Shorten last segment
            remaining = target_duration - accumulated
            if remaining > 0.5:
                seg["end"] = seg["start"] + remaining
                trimmed_segments.append(seg)
                accumulated += remaining
            break
        trimmed_segments.append(seg)
        accumulated += seg_dur

    segments = trimmed_segments

    if not segments:
        raise ValueError("Yeterli segment olusturulamadi")

    # ── 2. Extract each segment with FFmpeg ──
    temp_clips = []
    temp_files = []
    try:
        for i, seg in enumerate(segments):
            temp_path = str(TEMP_DIR / f"mix_seg_{i}.mp4")
            temp_files.append(temp_path)

            seg_dur = seg["end"] - seg["start"]
            cmd = [
                FFMPEG_BIN, "-y",
                "-ss", str(seg["start"]),
                "-t", str(seg_dur),
                "-i", seg["path"],
                "-vf", f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                       f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
                "-movflags", "+faststart",
                temp_path,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding="utf-8", errors="replace"
            )
            if result.returncode != 0:
                raise RuntimeError(f"Segment {i} kesilemedi: {result.stderr[-300:]}")
            temp_clips.append(temp_path)

        # ── 3. Concatenate with transitions ──
        if len(temp_clips) == 1:
            # Single clip, just copy
            import shutil
            shutil.copy2(temp_clips[0], output_path)
        elif len(temp_clips) <= 3 or transition == "none":
            # Use concat demuxer (fast, no transitions) for many clips
            _concat_with_demuxer(temp_clips, output_path)
        else:
            # Use xfade transitions (limited by FFmpeg complexity)
            _concat_with_xfade(temp_clips, output_path, transition, transition_duration, w, h)

        actual_dur = _get_duration(output_path)
        return {
            "segments": [
                {"source": os.path.basename(s["path"]), "start": s["start"], "end": s["end"]}
                for s in segments
            ],
            "total_duration": actual_dur,
        }

    finally:
        for tf in temp_files:
            try:
                Path(tf).unlink(missing_ok=True)
            except Exception:
                pass


def _concat_with_demuxer(clips: list[str], output_path: str):
    """Fast concat using demuxer (no transitions, but handles many clips)."""
    list_file = str(TEMP_DIR / "mix_concat.txt")
    with open(list_file, "w", encoding="utf-8") as f:
        for c in clips:
            safe = c.replace("\\", "/").replace("'", "'\\''")
            f.write(f"file '{safe}'\n")

    cmd = [
        FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0",
        "-i", list_file, "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        Path(list_file).unlink(missing_ok=True)
    except Exception:
        pass
    if result.returncode != 0:
        raise RuntimeError(f"Concat hatasi: {result.stderr[-500:]}")


def _concat_with_xfade(clips: list[str], output_path: str,
                        transition: str, trans_dur: float, w: str, h: str):
    """Concat with xfade transitions. Falls back to demuxer if too many clips."""
    # xfade becomes very slow with >20 clips, use demuxer fallback
    if len(clips) > 20:
        return _concat_with_demuxer(clips, output_path)

    cmd = [FFMPEG_BIN, "-y"]
    for c in clips:
        cmd.extend(["-i", c])

    # Get durations for offset calculation
    durations = []
    for c in clips:
        d = _get_duration(c)
        durations.append(d if d > 0 else 5.0)

    # Build xfade filter chain
    filter_parts = []
    # First, prepare all video streams
    for i in range(len(clips)):
        filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

    # Chain xfade
    cumulative_offset = 0
    prev_label = "[v0]"
    for i in range(1, len(clips)):
        cumulative_offset += durations[i - 1] - trans_dur
        if cumulative_offset < 0:
            cumulative_offset = 0
        out_label = f"[xf{i}]" if i < len(clips) - 1 else "[vout]"
        filter_parts.append(
            f"{prev_label}[v{i}]xfade=transition={transition}:"
            f"duration={trans_dur}:offset={cumulative_offset}{out_label}"
        )
        prev_label = out_label
        # Adjust cumulative offset: after xfade the output duration is shorter
        # The output of xfade is: duration[0..i] - (i * trans_dur)
        # Reset cumulative for next iteration
        cumulative_offset = sum(durations[:i + 1]) - i * trans_dur - trans_dur

    # Audio: concat audio streams
    audio_inputs = "".join(f"[{i}:a]" for i in range(len(clips)))
    filter_parts.append(f"{audio_inputs}concat=n={len(clips)}:v=0:a=1[aout]")

    filter_str = ";".join(filter_parts)

    cmd.extend([
        "-filter_complex", filter_str,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output_path,
    ])

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=600,  # 10 minute timeout
    )
    if result.returncode != 0:
        # Fallback to demuxer on xfade failure
        try:
            _concat_with_demuxer(clips, output_path)
        except Exception:
            raise RuntimeError(f"Video birlestirme hatasi: {result.stderr[-500:]}")


def _get_duration(file_path: str) -> float:
    """Get duration of a media file using ffprobe."""
    from app.config import FFPROBE_BIN as probe_bin
    import json as _json
    cmd = [
        probe_bin, "-v", "quiet", "-print_format", "json",
        "-show_format", file_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    try:
        data = _json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0


def _generate_ass(subtitles: list[dict], output_path: str):
    """Generate ASS subtitle file."""
    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Default,Segoe UI,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,2,20,20,40,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for sub in subtitles:
        start = _seconds_to_ass_time(sub.get("start_time", 0))
        end = _seconds_to_ass_time(sub.get("end_time", 5))
        text = sub.get("text", "").replace("\n", "\\N")
        pos = sub.get("position", "bottom")
        alignment = {"top": 8, "center": 5, "bottom": 2}.get(pos, 2)
        color = sub.get("color", "#FFFFFF")
        font_size = sub.get("font_size", 48)
        ass_color = _hex_to_ass_color(color)
        override = f"{{\\an{alignment}\\fs{font_size}\\c{ass_color}}}"
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{override}{text}")

    with open(output_path, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))


def _seconds_to_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_ass_color(hex_color: str) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    return f"&H00{b:02X}{g:02X}{r:02X}"
