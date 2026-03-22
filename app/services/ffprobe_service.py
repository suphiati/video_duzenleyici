import json
import subprocess
from pathlib import Path

from app.config import FFPROBE_BIN, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, AUDIO_EXTENSIONS
from app.models.media import MediaInfo


async def probe_file(file_path: str) -> MediaInfo:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Dosya bulunamadi: {file_path}")
    ext = path.suffix.lower()

    if ext in IMAGE_EXTENSIONS:
        return _probe_image(path)

    cmd = [
        FFPROBE_BIN, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    stdout_str = result.stdout.strip()
    if not stdout_str:
        raise RuntimeError(f"ffprobe bos cikti verdi: {result.stderr[:300]}")
    try:
        data = json.loads(stdout_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"ffprobe JSON parse hatasi: {e}")

    info = MediaInfo(
        path=str(path),
        filename=path.name,
        file_size=path.stat().st_size,
    )

    fmt = data.get("format", {})
    info.duration = float(fmt.get("duration", 0))

    if ext in VIDEO_EXTENSIONS:
        info.media_type = "video"
    elif ext in AUDIO_EXTENSIONS:
        info.media_type = "audio"

    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and not info.video_codec:
            info.video_codec = stream.get("codec_name", "")
            info.width = int(stream.get("width", 0))
            info.height = int(stream.get("height", 0))
            r_frame_rate = stream.get("r_frame_rate", "0/1")
            num, den = r_frame_rate.split("/")
            if int(den) > 0:
                info.fps = round(int(num) / int(den), 2)
        elif stream.get("codec_type") == "audio" and not info.audio_codec:
            info.audio_codec = stream.get("codec_name", "")

    return info


def probe_file_sync(file_path: str) -> MediaInfo:
    """Synchronous wrapper around probe_file logic (no async)."""
    import asyncio
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We're inside an async context; run the sync parts directly
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Dosya bulunamadi: {file_path}")
        ext = path.suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return _probe_image(path)

        cmd = [
            FFPROBE_BIN, "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            str(path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        stdout_str = result.stdout.strip()
        if not stdout_str:
            raise RuntimeError(f"ffprobe bos cikti verdi: {result.stderr[:300]}")
        data = json.loads(stdout_str)

        info = MediaInfo(
            path=str(path),
            filename=path.name,
            file_size=path.stat().st_size,
        )
        fmt = data.get("format", {})
        info.duration = float(fmt.get("duration", 0))

        if ext in VIDEO_EXTENSIONS:
            info.media_type = "video"
        elif ext in AUDIO_EXTENSIONS:
            info.media_type = "audio"

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and not info.video_codec:
                info.video_codec = stream.get("codec_name", "")
                info.width = int(stream.get("width", 0))
                info.height = int(stream.get("height", 0))
                r_frame_rate = stream.get("r_frame_rate", "0/1")
                num, den = r_frame_rate.split("/")
                if int(den) > 0:
                    info.fps = round(int(num) / int(den), 2)
            elif stream.get("codec_type") == "audio" and not info.audio_codec:
                info.audio_codec = stream.get("codec_name", "")
        return info
    else:
        return loop.run_until_complete(probe_file(file_path))


def _probe_image(path: Path) -> MediaInfo:
    from PIL import Image
    img = Image.open(path)
    w, h = img.size
    img.close()
    return MediaInfo(
        path=str(path),
        filename=path.name,
        width=w,
        height=h,
        file_size=path.stat().st_size,
        media_type="image",
    )
