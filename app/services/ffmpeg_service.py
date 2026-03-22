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
