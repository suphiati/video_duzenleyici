from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime

from app.config import EXPORTS_DIR
from app.services.ffmpeg_service import create_slideshow

router = APIRouter()


class SlideshowRequest(BaseModel):
    images: list[str]
    duration_per_image: float = 5.0
    transition: str = "fade"
    transition_duration: float = 1.0
    output_name: str = ""


@router.post("/create")
async def create_slideshow_endpoint(req: SlideshowRequest):
    if not req.images:
        raise HTTPException(400, "En az 1 resim gerekli")

    name = req.output_name or f"slayt_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_path = str(EXPORTS_DIR / f"{name}.mp4")

    try:
        create_slideshow(
            images=req.images,
            output_path=output_path,
            duration_per_image=req.duration_per_image,
            transition=req.transition,
            transition_duration=req.transition_duration,
        )
        return {"output": output_path, "message": "Slayt gosterisi olusturuldu"}
    except Exception as e:
        raise HTTPException(500, str(e))
