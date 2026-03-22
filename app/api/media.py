import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from starlette.responses import FileResponse

from app.config import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, AUDIO_EXTENSIONS, MEDIA_LIBRARY_FILE
from app.models.media import BrowseRequest, ImportRequest, MediaInfo
from app.services.ffprobe_service import probe_file
from app.services.thumbnail_service import get_thumbnail

router = APIRouter()

# ---------------------------------------------------------------------------
# Persistent media library (JSON on disk)
# ---------------------------------------------------------------------------
_media_library: dict[str, MediaInfo] = {}


def _load_library():
    """Load media library from disk."""
    global _media_library
    if MEDIA_LIBRARY_FILE.exists():
        try:
            raw = json.loads(MEDIA_LIBRARY_FILE.read_text(encoding="utf-8"))
            for key, val in raw.items():
                norm_key = os.path.normpath(key)
                _media_library[norm_key] = MediaInfo(**val)
        except Exception:
            _media_library = {}


def _save_library():
    """Persist media library to disk."""
    MEDIA_LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v.model_dump() for k, v in _media_library.items()}
    MEDIA_LIBRARY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Load on module import
_load_library()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/browse")
async def browse_files(req: BrowseRequest):
    p = Path(os.path.normpath(req.path))
    if not p.exists():
        raise HTTPException(404, "Klasor bulunamadi")
    if not p.is_dir():
        raise HTTPException(400, "Bu bir klasor degil")

    all_ext = VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS
    items = []
    try:
        for entry in sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                items.append({"name": entry.name, "path": str(entry), "type": "folder"})
            elif entry.suffix.lower() in all_ext:
                ext = entry.suffix.lower()
                if ext in VIDEO_EXTENSIONS:
                    ftype = "video"
                elif ext in IMAGE_EXTENSIONS:
                    ftype = "image"
                else:
                    ftype = "audio"
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "type": ftype,
                    "size": entry.stat().st_size,
                })
    except PermissionError:
        raise HTTPException(403, "Erisim izni yok")
    return {"path": str(p), "parent": str(p.parent), "items": items}


@router.post("/import")
async def import_media(req: ImportRequest):
    results = []
    for file_path in req.paths:
        norm_path = os.path.normpath(file_path)
        p = Path(norm_path)
        if not p.exists():
            results.append({"path": norm_path, "error": "Dosya bulunamadi"})
            continue
        if not p.is_file():
            results.append({"path": norm_path, "error": "Bu bir dosya degil"})
            continue
        try:
            info = await probe_file(norm_path)
            _media_library[norm_path] = info
            results.append(info.model_dump())
        except Exception as e:
            results.append({"path": norm_path, "error": f"{type(e).__name__}: {e}"})
    _save_library()
    return {"imported": results}


@router.get("/list")
async def list_media():
    return {"media": [m.model_dump() for m in _media_library.values()]}


@router.delete("/remove")
async def remove_media(path: str):
    norm_path = os.path.normpath(path)
    if norm_path in _media_library:
        del _media_library[norm_path]
        _save_library()
        return {"ok": True}
    raise HTTPException(404, "Medya bulunamadi")


@router.get("/info")
async def get_info(path: str):
    norm_path = os.path.normpath(path)
    p = Path(norm_path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "Dosya bulunamadi")
    try:
        info = await probe_file(norm_path)
        return info.model_dump()
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/thumbnail")
async def get_thumb(path: str):
    norm_path = os.path.normpath(path)
    thumb = await get_thumbnail(norm_path)
    if thumb and thumb.exists():
        return FileResponse(str(thumb), media_type="image/jpeg")
    raise HTTPException(404, "Kucuk resim olusturulamadi")


@router.get("/stream")
async def stream_media(path: str):
    norm_path = os.path.normpath(path)
    p = Path(norm_path)
    if not p.exists():
        raise HTTPException(404, "Dosya bulunamadi")
    if not p.is_file():
        raise HTTPException(400, "Bu bir dosya degil")

    ext = p.suffix.lower()
    ct_map = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".aac": "audio/aac", ".m4a": "audio/mp4", ".flac": "audio/flac",
    }
    content_type = ct_map.get(ext, "application/octet-stream")
    return FileResponse(str(p), media_type=content_type)


@router.get("/drives")
async def list_drives():
    """List available drives on Windows."""
    drives = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
    else:
        drives = ["/"]
    return {"drives": drives}
