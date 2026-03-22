import asyncio
from pathlib import Path
import hashlib

from app.config import FFMPEG_BIN, THUMBNAILS_DIR, IMAGE_EXTENSIONS


def _thumb_path(file_path: str) -> Path:
    h = hashlib.md5(file_path.encode()).hexdigest()
    return THUMBNAILS_DIR / f"{h}.jpg"


async def get_thumbnail(file_path: str) -> Path | None:
    thumb = _thumb_path(file_path)
    if thumb.exists():
        return thumb

    ext = Path(file_path).suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return await _image_thumbnail(file_path, thumb)
    return await _video_thumbnail(file_path, thumb)


async def _video_thumbnail(file_path: str, thumb: Path) -> Path | None:
    cmd = [
        FFMPEG_BIN, "-y", "-i", file_path,
        "-ss", "00:00:02", "-vframes", "1",
        "-vf", "scale=320:-1",
        "-q:v", "5",
        str(thumb)
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return thumb if thumb.exists() else None


async def _image_thumbnail(file_path: str, thumb: Path) -> Path | None:
    from PIL import Image
    img = Image.open(file_path)
    img.thumbnail((320, 320))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(str(thumb), "JPEG", quality=80)
    img.close()
    return thumb
