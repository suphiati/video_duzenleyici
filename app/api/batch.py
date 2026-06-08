import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse

from app.models.batch import BatchRequest, ScanRequest
from app.services.folder_scanner import scan_folder
from app.services import youtube_service, ai_service, beat_analyzer, music_library
from app.services.batch_service import run_batch
from app.services.pro_planner import STYLE_PROFILES

router = APIRouter()


# ---------------------------------------------------------------------------
# YouTube OAuth
# ---------------------------------------------------------------------------

@router.get("/youtube/status")
async def youtube_status():
    try:
        return {"authenticated": youtube_service.is_authenticated()}
    except Exception:
        return {"authenticated": False}


@router.get("/youtube/auth-url")
async def youtube_auth_url():
    try:
        url = youtube_service.get_auth_url()
        return {"url": url}
    except FileNotFoundError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"OAuth URL olusturulamadi: {e}")


@router.get("/youtube/callback")
async def youtube_callback(code: str):
    try:
        youtube_service.handle_callback(code)
        return HTMLResponse("""
        <html><body>
        <h2>YouTube baglantisi basarili!</h2>
        <p>Bu pencereyi kapatabilirsiniz.</p>
        <script>
            if (window.opener) {
                window.opener.postMessage({type: 'youtube_auth_success'}, '*');
            }
            setTimeout(() => window.close(), 2000);
        </script>
        </body></html>
        """)
    except Exception as e:
        return HTMLResponse(
            f"<html><body><h2>Hata!</h2><p>{str(e)}</p></body></html>",
            status_code=400,
        )


# ---------------------------------------------------------------------------
# AI (Ollama)
# ---------------------------------------------------------------------------

@router.get("/ai/status")
async def ai_status():
    """Report whether a local Ollama instance is reachable."""
    available = await ai_service.is_available()
    models: list[str] = []
    if available:
        models = await ai_service.list_models()
    return {
        "available": available,
        "host": ai_service.OLLAMA_HOST,
        "default_model": ai_service.DEFAULT_MODEL,
        "models": models,
    }


# ---------------------------------------------------------------------------
# Pro-mode status & music library
# ---------------------------------------------------------------------------

@router.get("/pro/status")
async def pro_status():
    """Report pro-mode capabilities and available style presets."""
    return {
        "beat_sync_available": beat_analyzer.is_available(),
        "styles": [
            {
                "id": sid,
                "clip_range": profile["clip_length"],
                "transition": profile["transition"],
                "prefer_mood": profile["prefer_mood"],
                "beat_sync": profile["beat_sync"],
            }
            for sid, profile in STYLE_PROFILES.items()
        ],
    }


@router.get("/music/list")
async def list_music():
    """Return every audio file under data/music/ grouped by mood."""
    tracks = music_library.list_tracks()
    moods: dict[str, list[dict]] = {}
    for t in tracks:
        moods.setdefault(t["mood"], []).append(t)
    return {"count": len(tracks), "tracks": tracks, "moods": moods}


# ---------------------------------------------------------------------------
# Folder scan & batch pipeline
# ---------------------------------------------------------------------------

@router.post("/scan")
async def scan_folder_endpoint(req: ScanRequest):
    folder = os.path.normpath(req.folder_path)
    if not Path(folder).exists():
        raise HTTPException(404, f"Klasor bulunamadi: {req.folder_path}")
    if not Path(folder).is_dir():
        raise HTTPException(400, f"Bu bir klasor degil: {req.folder_path}")

    try:
        return await asyncio.to_thread(scan_folder, folder)
    except Exception as e:
        raise HTTPException(500, f"Klasor tarama hatasi: {e}")


@router.websocket("/ws")
async def batch_ws(websocket: WebSocket):
    await websocket.accept()
    cancel_event = asyncio.Event()

    try:
        data = await websocket.receive_json()
        req = BatchRequest(**data)

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

        async def send_message(msg: dict):
            try:
                await websocket.send_json(msg)
            except Exception:
                pass

        await run_batch(
            folder_path=os.path.normpath(req.folder_path),
            num_videos=req.num_videos,
            target_duration=req.target_duration,
            clip_duration=req.clip_duration,
            photo_duration=req.photo_duration,
            transition=req.transition,
            transition_duration=req.transition_duration,
            shuffle=req.shuffle,
            upload_to_youtube=req.upload_to_youtube,
            youtube_settings=req.youtube_settings.model_dump(),
            ai_settings=req.ai_settings.model_dump(),
            pro_settings=req.pro_settings.model_dump(),
            send_message=send_message,
            cancel_event=cancel_event,
        )

        cancel_task.cancel()

    except RuntimeError as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": f"Beklenmeyen hata: {str(e)}"})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
