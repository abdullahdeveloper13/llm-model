"""System power tools. Destructive: production mode requires confirmation."""
from __future__ import annotations

from app.tools.base import Tool, ToolResult
from app.config.settings import settings
from app.utils.logger import get_logger
from app.utils.security import run_allowed

log = get_logger(__name__)


class ShutdownTool(Tool):
    name = "shutdown"
    description = "Shut down the Windows computer (scheduled after 30s so it can be cancelled)."
    schema = {"type": "object", "properties": {}}
    category = "confirmation"
    destructive = True

    def execute(self, **kwargs) -> ToolResult:
        if not settings.is_production:
            msg = "[SIMULATION] Shutdown command would execute: shutdown /s /t 30"
            log.info(msg)
            return ToolResult.ok(msg, simulated=True)
        try:
            run_allowed("shutdown.exe", ["/s", "/t", "30"])
            log.info("Shutdown scheduled in 30s")
            return ToolResult.ok("Shutting down in 30 seconds. Say 'cancel shutdown' to abort.")
        except Exception as exc:
            log.error("Shutdown failed: %s", exc)
            return ToolResult.fail(f"I couldn't shut down the computer. ({exc})")


class RestartTool(Tool):
    name = "restart"
    description = "Restart the Windows computer (scheduled after 30s so it can be cancelled)."
    schema = {"type": "object", "properties": {}}
    category = "confirmation"
    destructive = True

    def execute(self, **kwargs) -> ToolResult:
        if not settings.is_production:
            msg = "[SIMULATION] Restart command would execute: shutdown /r /t 30"
            log.info(msg)
            return ToolResult.ok(msg, simulated=True)
        try:
            run_allowed("shutdown.exe", ["/r", "/t", "30"])
            log.info("Restart scheduled in 30s")
            return ToolResult.ok("Restarting in 30 seconds. Say 'cancel shutdown' to abort.")
        except Exception as exc:
            log.error("Restart failed: %s", exc)
            return ToolResult.fail(f"I couldn't restart the computer. ({exc})")


class CancelShutdownTool(Tool):
    name = "cancel_shutdown"
    description = "Cancel a scheduled shutdown or restart."
    schema = {"type": "object", "properties": {}}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        if not settings.is_production:
            return ToolResult.ok("[SIMULATION] Cancel-shutdown would execute: shutdown /a")
        try:
            out = run_allowed("shutdown.exe", ["/a"])
            return ToolResult.ok("Cancelled the pending shutdown/restart.", output=out)
        except Exception as exc:
            return ToolResult.fail(f"There was no shutdown to cancel, or it failed. ({exc})")
