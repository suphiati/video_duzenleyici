import subprocess
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
        return _image_thumbnail(file_path, thumb)
    return _video_thumbnail(file_path, thumb)


def _video_thumbnail(file_path: str, thumb: Path) -> Path | None:
    cmd = [
        FFMPEG_BIN, "-y", "-i", file_path,
        "-ss", "00:00:02", "-vframes", "1",
        "-vf", "scale=320:-1",
        "-q:v", "5",
        str(thumb)
    ]
    subprocess.run(cmd, capture_output=True)
    return thumb if thumb.exists() else None


def _image_thumbnail(file_path: str, thumb: Path) -> Path | None:
    from PIL import Image
    img = Image.open(file_path)
    img.thumbnail((320, 320))
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(str(thumb), "JPEG", quality=80)
    img.close()
    return thumb
