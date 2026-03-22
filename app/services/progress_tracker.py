import asyncio
import json
from fastapi import WebSocket


class ProgressTracker:
    def __init__(self, websocket: WebSocket, total_duration: float):
        self.websocket = websocket
        self.total_duration = total_duration

    async def update(self, current_seconds: float):
        if self.total_duration > 0:
            percent = min(100, (current_seconds / self.total_duration) * 100)
        else:
            percent = 0
        try:
            await self.websocket.send_json({
                "type": "progress",
                "percent": round(percent, 1),
                "current": round(current_seconds, 1),
                "total": round(self.total_duration, 1),
            })
        except Exception:
            pass
