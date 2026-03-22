from fastapi import APIRouter, HTTPException

from app.models.project import Clip, AudioTrack
from app.services.project_service import load_project, save_project

router = APIRouter()


@router.post("/{project_id}/clips/add")
async def add_clip(project_id: str, clip: Clip):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    clip.order = len(p.clips)
    p.clips.append(clip)
    save_project(p)
    return p.model_dump()


@router.put("/{project_id}/clips/{clip_id}")
async def update_clip(project_id: str, clip_id: str, clip: Clip):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    for i, c in enumerate(p.clips):
        if c.id == clip_id:
            clip.id = clip_id
            p.clips[i] = clip
            save_project(p)
            return p.model_dump()
    raise HTTPException(404, "Klip bulunamadi")


@router.delete("/{project_id}/clips/{clip_id}")
async def remove_clip(project_id: str, clip_id: str):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    p.clips = [c for c in p.clips if c.id != clip_id]
    for i, c in enumerate(p.clips):
        c.order = i
    save_project(p)
    return p.model_dump()


@router.put("/{project_id}/clips/reorder")
async def reorder_clips(project_id: str, clip_ids: list[str]):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    clip_map = {c.id: c for c in p.clips}
    p.clips = []
    for i, cid in enumerate(clip_ids):
        if cid in clip_map:
            clip_map[cid].order = i
            p.clips.append(clip_map[cid])
    save_project(p)
    return p.model_dump()


@router.post("/{project_id}/audio/add")
async def add_audio(project_id: str, track: AudioTrack):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    p.audio_tracks.append(track)
    save_project(p)
    return p.model_dump()


@router.put("/{project_id}/audio/{track_id}")
async def update_audio(project_id: str, track_id: str, track: AudioTrack):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    for i, t in enumerate(p.audio_tracks):
        if t.id == track_id:
            track.id = track_id
            p.audio_tracks[i] = track
            save_project(p)
            return p.model_dump()
    raise HTTPException(404, "Ses parcasi bulunamadi")


@router.delete("/{project_id}/audio/{track_id}")
async def remove_audio(project_id: str, track_id: str):
    p = load_project(project_id)
    if not p:
        raise HTTPException(404, "Proje bulunamadi")
    p.audio_tracks = [t for t in p.audio_tracks if t.id != track_id]
    save_project(p)
    return p.model_dump()
