"""Local FastAPI server. Optional — the assistant works fully without it."""
from __future__ import annotations

import threading
import uvicorn
from fastapi import FastAPI

from app.api.routes import register_routes
from app.api.websocket import manager
from app.config.settings import settings
from app.core.orchestrator import Orchestrator
from app.utils.logger import get_logger

log = get_logger(__name__)


def create_app(orchestrator: Orchestrator | None = None) -> FastAPI:
    orch = orchestrator or Orchestrator()

    def emit(event: str, data: dict) -> None:
        manager.broadcast_threadsafe(event, **data)

    orch.on_event = emit

    app = FastAPI(title="AI Assistant Agent", version="1.0.0")
    app.state.settings = settings
    app.state.orchestrator = orch
    register_routes(app, orch)
    return app


def start_api(orchestrator: Orchestrator | None = None) -> FastAPI:
    """Create the app and serve it in a daemon thread (used by run.py --api)."""
    app = create_app(orchestrator)

    def capture_loop(loop: "asyncio.AbstractEventLoop") -> None:
        import asyncio

        manager.loop = loop

    @app.on_event("startup")
    async def _startup() -> None:
        import asyncio

        manager.loop = asyncio.get_running_loop()
        log.info("API ready on http://%s:%d", settings.agent_host, settings.agent_port)

    thread = threading.Thread(
        target=uvicorn.run,
        args=(app,),
        kwargs={"host": settings.agent_host, "port": settings.agent_port, "log_level": "info"},
        daemon=True,
        name="assistant-api",
    )
    thread.start()
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host=settings.agent_host, port=settings.agent_port)
