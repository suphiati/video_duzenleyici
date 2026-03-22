import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, FileResponse

from app.config import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS, AUDIO_EXTENSIONS
from app.models.media import BrowseRequest, ImportRequest, MediaInfo
from app.services.ffprobe_service import probe_file
from app.services.thumbnail_service import get_thumbnail

router = APIRouter()

# In-memory media library for the session
_media_library: dict[str, MediaInfo] = {}


@router.post("/browse")
async def browse_files(req: BrowseRequest):
    p = Path(req.path)
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
        p = Path(file_path)
        if not p.exists():
            continue
        try:
            info = await probe_file(file_path)
            _media_library[file_path] = info
            results.append(info.model_dump())
        except Exception as e:
            results.append({"path": file_path, "error": str(e)})
    return {"imported": results}


@router.get("/list")
async def list_media():
    return {"media": [m.model_dump() for m in _media_library.values()]}


@router.delete("/remove")
async def remove_media(path: str):
    if path in _media_library:
        del _media_library[path]
        return {"ok": True}
    raise HTTPException(404, "Medya bulunamadi")


@router.get("/info")
async def get_info(path: str):
    try:
        info = await probe_file(path)
        return info.model_dump()
    except Exception as e:
        raise HTTPException(400, str(e))


@router.get("/thumbnail")
async def get_thumb(path: str):
    thumb = await get_thumbnail(path)
    if thumb and thumb.exists():
        return FileResponse(str(thumb), media_type="image/jpeg")
    raise HTTPException(404, "Kucuk resim olusturulamadi")


@router.get("/stream")
async def stream_media(request: Request, path: str):
    p = Path(path)
    if not p.exists():
        raise HTTPException(404, "Dosya bulunamadi")

    file_size = p.stat().st_size
    range_header = request.headers.get("range")

    content_type = "video/mp4"
    ext = p.suffix.lower()
    ct_map = {
        ".mp4": "video/mp4", ".webm": "video/webm", ".mkv": "video/x-matroska",
        ".avi": "video/x-msvideo", ".mov": "video/quicktime",
        ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
        ".aac": "audio/aac", ".m4a": "audio/mp4", ".flac": "audio/flac",
    }
    content_type = ct_map.get(ext, "application/octet-stream")

    if range_header:
        range_val = range_header.replace("bytes=", "")
        parts = range_val.split("-")
        start = int(parts[0])
        end = int(parts[1]) if parts[1] else min(start + 5 * 1024 * 1024, file_size - 1)
        end = min(end, file_size - 1)
        length = end - start + 1

        with open(p, "rb") as f:
            f.seek(start)
            data = f.read(length)

        return Response(
            content=data,
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Content-Type": content_type,
            },
        )

    return FileResponse(str(p), media_type=content_type, headers={"Accept-Ranges": "bytes"})


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
