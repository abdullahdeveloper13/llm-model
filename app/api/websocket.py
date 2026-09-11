"""WebSocket broadcast hub for UI clients."""
from __future__ import annotations

import asyncio

from fastapi import WebSocket

from app.utils.logger import get_logger

log = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)
        log.info("UI client connected (%d total)", len(self.active))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)
            log.info("UI client disconnected")

    async def broadcast(self, event: str, **payload) -> None:
        message = {"event": event, **payload}
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(ws)

    def broadcast_threadsafe(self, event: str, **payload) -> None:
        """Safe to call from the voice loop / non-async threads."""
        if not self.loop or not self.active:
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(event, **payload), self.loop)


manager = ConnectionManager()
