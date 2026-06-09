import sys
from pathlib import Path
import shutil

if getattr(sys, "frozen", False):
    # PyInstaller bundle: read-only files (app/static) are unpacked to a temp
    # dir (_MEIPASS); writable data lives next to the .exe so projects, music
    # and YouTube tokens persist across runs (and survive a desktop shortcut).
    APP_DIR = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "app"
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    APP_DIR = Path(__file__).resolve().parent
    BASE_DIR = APP_DIR.parent

DATA_DIR = BASE_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
THUMBNAILS_DIR = DATA_DIR / "thumbnails"
EXPORTS_DIR = DATA_DIR / "exports"
TEMP_DIR = DATA_DIR / "temp"
STATIC_DIR = APP_DIR / "static"
MEDIA_LIBRARY_FILE = DATA_DIR / "media_library.json"

YOUTUBE_DIR = DATA_DIR / "youtube"
MUSIC_DIR = DATA_DIR / "music"
SCENES_CACHE_FILE = DATA_DIR / "scenes_cache.json"

for d in [PROJECTS_DIR, THUMBNAILS_DIR, EXPORTS_DIR, TEMP_DIR, YOUTUBE_DIR, MUSIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

YOUTUBE_CLIENT_SECRETS = YOUTUBE_DIR / "client_secrets.json"
YOUTUBE_TOKEN_FILE = YOUTUBE_DIR / "token.json"

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
