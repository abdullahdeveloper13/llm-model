"""System information tools (CPU / RAM / OS) via psutil."""
from __future__ import annotations

import platform

from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)


class SystemInfoTool(Tool):
    name = "system_info"
    description = "Report system stats: CPU usage, RAM usage, OS. Set 'detail' to cpu, ram, or all."
    schema = {
        "type": "object",
        "properties": {"detail": {"type": "string", "description": "cpu | ram | all"}},
        "required": [],
    }
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        detail = str(kwargs.get("detail", "all") or "all").lower()
        try:
            import psutil

            parts: list[str] = []
            data: dict[str, object] = {}
            if detail in ("cpu", "all"):
                cpu = psutil.cpu_percent(interval=0.3)
                data["cpu_percent"] = cpu
                parts.append(f"CPU usage is {cpu:.0f}%")
            if detail in ("ram", "all"):
                mem = psutil.virtual_memory()
                data["ram_percent"] = mem.percent
                data["ram_used_gb"] = round(mem.used / 1e9, 1)
                data["ram_total_gb"] = round(mem.total / 1e9, 1)
                parts.append(
                    f"RAM usage is {mem.percent:.0f}% "
                    f"({mem.used / 1e9:.1f} GB of {mem.total / 1e9:.1f} GB)"
                )
            if detail == "all":
                data["os"] = f"{platform.system()} {platform.release()}"
                parts.append(f"Running {platform.system()} {platform.release()}")
            log.info("system_info: %s", data)
            return ToolResult.ok(". ".join(parts) + ".", **data)  # type: ignore[arg-type]
        except Exception as exc:
            log.error("system_info failed: %s", exc)
            return ToolResult.fail(f"I couldn't read system information. ({exc})")
