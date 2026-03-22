from fastapi import APIRouter, HTTPException

from app.models.project import SubtitleEntry
from app.services.project_service import load_project, save_project

router = APIRouter()


@router.post("/{project_id}/add")
async def add_subtitle(project_id: str, entry: SubtitleEntry):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    p.subtitles.append(entry)
    p.subtitles.sort(key=lambda s: s.start_time)
    save_project(p)
    return p.model_dump()


@router.put("/{project_id}/{subtitle_id}")
async def update_subtitle(project_id: str, subtitle_id: str, entry: SubtitleEntry):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    for i, s in enumerate(p.subtitles):
        if s.id == subtitle_id:
            entry.id = subtitle_id
            p.subtitles[i] = entry
            p.subtitles.sort(key=lambda s: s.start_time)
            save_project(p)
            return p.model_dump()
    raise HTTPException(404, "Altyazi bulunamadi")


@router.delete("/{project_id}/{subtitle_id}")
async def remove_subtitle(project_id: str, subtitle_id: str):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    p.subtitles = [s for s in p.subtitles if s.id != subtitle_id]
    save_project(p)
    return p.model_dump()
