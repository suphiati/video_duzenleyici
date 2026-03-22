import asyncio
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from app.config import EXPORTS_DIR
from app.services.project_service import load_project
from app.services.ffprobe_service import probe_file
from app.services.ffmpeg_service import export_project
from app.services.progress_tracker import ProgressTracker

router = APIRouter()

_active_exports: dict[str, asyncio.Event] = {}


@router.websocket("/ws/{project_id}")
async def export_ws(websocket: WebSocket, project_id: str):
    await websocket.accept()

    project = load_project(project_id)
    if not project:
        await websocket.send_json({"type": "error", "message": "Proje bulunamadi"})
        await websocket.close()
        return

    if not project.clips:
        await websocket.send_json({"type": "error", "message": "Projede klip yok"})
        await websocket.close()
        return

    cancel_event = asyncio.Event()
    _active_exports[project_id] = cancel_event

    # Calculate total duration
    total_duration = 0
    for clip in project.clips:
        try:
            info = await probe_file(clip.media_path)
            clip_dur = info.duration
            if clip.in_point > 0:
                clip_dur -= clip.in_point
            if clip.out_point > 0:
                clip_dur = clip.out_point - clip.in_point
            total_duration += clip_dur
        except Exception:
            pass

    tracker = ProgressTracker(websocket, total_duration)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = str(EXPORTS_DIR / f"{project.name}_{timestamp}.mp4")

    try:
        await websocket.send_json({"type": "started", "output": output_path})

        # Listen for cancel messages in background
        async def listen_cancel():
            try:
                while True:
                    msg = await websocket.receive_json()
                    if msg.get("action") == "cancel":
                        cancel_event.set()
                        break
            except WebSocketDisconnect:
                cancel_event.set()

        cancel_task = asyncio.create_task(listen_cancel())

        await export_project(
            clips=[c.model_dump() for c in project.clips],
            audio_tracks=[a.model_dump() for a in project.audio_tracks],
            subtitles=[s.model_dump() for s in project.subtitles],
            output_path=output_path,
            progress_callback=tracker.update,
            cancel_event=cancel_event,
        )

        cancel_task.cancel()

        file_size = Path(output_path).stat().st_size
        await websocket.send_json({
            "type": "completed",
            "output": output_path,
            "size": file_size,
        })
    except RuntimeError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Beklenmeyen hata: {str(e)}"})
    finally:
        _active_exports.pop(project_id, None)
        try:
            await websocket.close()
        except Exception:
            pass


@router.get("/list")
async def list_exports():
    exports = []
    for f in EXPORTS_DIR.glob("*.mp4"):
        exports.append({
            "name": f.name,
            "path": str(f),
            "size": f.stat().st_size,
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return {"exports": sorted(exports, key=lambda x: x["created"], reverse=True)}
