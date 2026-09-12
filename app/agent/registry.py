"""Central tool registry.

The ONLY place tools are registered. The LLM can request a tool by name; if
the name is not in this registry, the request is rejected. No dynamic code
execution, ever.
"""
from __future__ import annotations

from app.tools.base import Tool
from app.utils.logger import get_logger

log = get_logger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate tool name: {tool.name}")
        if not tool.name:
            raise ValueError("Tool must define a name")
        self._tools[tool.name] = tool
        log.info("Registered tool: %s (%s)", tool.name, tool.category)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def all(self) -> dict[str, Tool]:
        return dict(self._tools)

    def schemas(self) -> list[dict]:
        """OpenAI-style function definitions for the LLM."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.schema,
                },
            }
            for t in self._tools.values()
        ]


def build_default_registry() -> ToolRegistry:
    """Create a registry with all version-1 tools."""
    from app.tools.apps.launcher import AppLauncher, CloseAppTool
    from app.tools.apps.windows import WindowControlTool
    from app.tools.browser.browser import GoogleSearch, OpenWebsite, YouTubeSearch
    from app.tools.browser.navigation import BrowserNavigationTool
    from app.tools.files.manager import DeleteFileTool
    from app.tools.files.operations import FileOperationTool
    from app.tools.files.search import SearchFilesTool
    from app.tools.media.player import MediaControlTool
    from app.tools.system.shutdown import (
        CancelShutdownTool,
        RestartTool,
        ShutdownTool,
    )
    from app.tools.system.system_info import SystemInfoTool
    from app.tools.system.keyboard import PressKeysTool, TypeTextTool
    from app.tools.whatsapp.whatsapp import WhatsAppCallTool, WhatsAppOpenTool, WhatsAppOpenChatTool, WhatsAppCallAutoTool, WhatsAppMessageAutoTool

    registry = ToolRegistry()
    for tool in (
        AppLauncher(),
        CloseAppTool(),
        WindowControlTool(),
        OpenWebsite(),
        GoogleSearch(),
        YouTubeSearch(),
        BrowserNavigationTool(),
        WhatsAppOpenTool(),
        WhatsAppOpenChatTool(),
        WhatsAppCallTool(),
        WhatsAppCallAutoTool(),
        WhatsAppMessageAutoTool(),
        ShutdownTool(),
        RestartTool(),
        CancelShutdownTool(),
        SystemInfoTool(),
        SearchFilesTool(),
        DeleteFileTool(),
        FileOperationTool(),
        MediaControlTool(),
        TypeTextTool(),
        PressKeysTool(),
    ):
        registry.register(tool)
    return registry
