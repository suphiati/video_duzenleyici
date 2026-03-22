from pathlib import Path
import shutil

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
EXPORTS_DIR = DATA_DIR / "exports"
TEMP_DIR = DATA_DIR / "temp"
STATIC_DIR = Path(__file__).resolve().parent / "static"
MEDIA_LIBRARY_FILE = DATA_DIR / "media_library.json"

for d in [PROJECTS_DIR, THUMBNAILS_DIR, EXPORTS_DIR, TEMP_DIR]:
    d.mkdir(parents=True, exist_ok=True)

FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "ffprobe"

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mts"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4a", ".wma", ".opus"}

YOUTUBE_EXPORT_SETTINGS = {
    "video_codec": "libx264",
    "audio_codec": "aac",
    "video_bitrate": "10M",
    "audio_bitrate": "384k",
    "resolution": "1920x1080",
    "pixel_format": "yuv420p",
    "preset": "medium",
    "profile": "high",
    "level": "4.1",
    "keyint": 48,
    "audio_sample_rate": 48000,
}
