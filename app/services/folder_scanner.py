import os
from pathlib import Path

from app.config import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from app.services.ffprobe_service import probe_file_sync


def scan_folder(folder_path: str) -> dict:
    """
    Scan a folder for video and photo files.

    Returns:
        {
            "folder_name": str,
            "videos": [{"path": str, "duration": float, "width": int, "height": int}],
            "photos": [{"path": str, "width": int, "height": int}],
            "total_video_duration": float,
            "video_count": int,
            "photo_count": int,
        }
    """
    folder = Path(os.path.normpath(folder_path))
    if not folder.exists():
        raise FileNotFoundError(f"Klasor bulunamadi: {folder_path}")
    if not folder.is_dir():
        raise ValueError(f"Bu bir klasor degil: {folder_path}")

    videos = []
    photos = []

    # Scan all files (recursive)
    all_files = sorted(folder.rglob("*"), key=lambda p: p.name.lower())

    for file_path in all_files:
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()

        if ext in VIDEO_EXTENSIONS:
            try:
                info = probe_file_sync(str(file_path))
                if info.duration > 0:
                    videos.append({
                        "path": str(file_path),
                        "duration": info.duration,
                        "width": info.width,
                        "height": info.height,
                    })
            except Exception:
                # Skip files that can't be probed
                pass

        elif ext in IMAGE_EXTENSIONS:
            try:
                info = probe_file_sync(str(file_path))
                photos.append({
                    "path": str(file_path),
                    "width": info.width,
                    "height": info.height,
                })
            except Exception:
                pass

    total_duration = sum(v["duration"] for v in videos)

    return {
        "folder_name": folder.name,
        "videos": videos,
        "photos": photos,
        "total_video_duration": round(total_duration, 1),
        "video_count": len(videos),
        "photo_count": len(photos),
    }
