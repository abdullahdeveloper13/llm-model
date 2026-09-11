"""HTTP + WebSocket routes."""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.websocket import manager
from app.core.orchestrator import TurnResult
from app.utils.logger import get_logger

log = get_logger(__name__)
router = APIRouter()


def register_routes(app, orchestrator) -> None:
    """Bind routes to a shared orchestrator instance."""

    @app.get("/health")
    def health() -> dict:
        s = app.state.settings
        return {
            "status": "ok",
            "mode": "production" if s.is_production else "development",
            "llm": s.openai_model if s.llm_enabled else "rule-based",
            "tools": orchestrator.registry.names(),
        }

    @app.post("/assistant/command")
    def command(body: dict) -> dict:
        text = str(body.get("text", "")).strip()
        if not text:
            return {"error": "Field 'text' is required"}
        result: TurnResult = orchestrator.handle(text)
        return _turn_to_dict(result)

    @app.post("/assistant/confirm")
    def confirm(body: dict) -> dict:
        answer = str(body.get("answer", "")).strip().lower()
        if answer not in ("yes", "no"):
            return {"error": "Field 'answer' must be 'yes' or 'no'"}
        result = orchestrator.handle(answer)
        return _turn_to_dict(result)

    @app.get("/commands")
    def commands(limit: int = 50) -> list[dict]:
        if not orchestrator.memory:
            return []
        return [r.model_dump() for r in orchestrator.memory.db.recent(limit)]

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await manager.connect(websocket)
        try:
            while True:
                data = await websocket.receive_json()
                if data.get("action") == "command":
                    result = orchestrator.handle(str(data.get("text", "")))
                    await manager.broadcast("response", **_turn_to_dict(result))
                elif data.get("action") == "ping":
                    await websocket.send_json({"event": "pong"})
        except WebSocketDisconnect:
            manager.disconnect(websocket)


def _turn_to_dict(result: TurnResult) -> dict:
    return {
        "response": result.response,
        "tool": result.tool,
        "tool_args": result.tool_args,
        "success": result.success,
        "awaiting_confirmation": result.awaiting_confirmation,
    }
