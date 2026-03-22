import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import EXPORTS_DIR
from app.services.ffmpeg_service import create_video_mix
from app.services.ffprobe_service import probe_file_sync

router = APIRouter()


class VideoMixRequest(BaseModel):
    videos: list[str]
    target_duration: float = 60.0  # seconds
    output_name: str = ""
    clip_duration: float = 5.0  # seconds per clip segment
    transition: str = "fade"
    transition_duration: float = 0.5
    shuffle: bool = True  # randomize clip order
    resolution: str = "1920x1080"


@router.post("/create")
async def create_video_mix_endpoint(req: VideoMixRequest):
    if len(req.videos) < 2:
        raise HTTPException(400, "En az 2 video gerekli")

    # Validate all video files exist
    for vp in req.videos:
        p = Path(os.path.normpath(vp))
        if not p.exists():
            raise HTTPException(404, f"Video bulunamadi: {vp}")
        if not p.is_file():
            raise HTTPException(400, f"Bu bir dosya degil: {vp}")

    # Get durations for all videos
    video_infos = []
    for vp in req.videos:
        norm = os.path.normpath(vp)
        try:
            info = probe_file_sync(norm)
            if info.duration <= 0:
                raise HTTPException(400, f"Video suresi alinamadi: {vp}")
            video_infos.append({"path": norm, "duration": info.duration})
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Video analiz hatasi ({vp}): {e}")

    name = req.output_name or f"mix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = str(EXPORTS_DIR / f"{name}.mp4")

    try:
        result = create_video_mix(
            video_infos=video_infos,
            target_duration=req.target_duration,
            clip_duration=req.clip_duration,
            transition=req.transition,
            transition_duration=req.transition_duration,
            shuffle=req.shuffle,
            resolution=req.resolution,
            output_path=output_path,
        )
        size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
        return {
            "output": output_path,
            "message": f"Video mix olusturuldu ({len(result['segments'])} segment)",
            "segments": result["segments"],
            "total_duration": result["total_duration"],
            "size": size,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
