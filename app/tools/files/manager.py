"""File manager tools. Deletion always requires confirmation and stays in user dirs."""
from __future__ import annotations

from pathlib import Path

from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

USER_DIRS = [
    Path(__import__("os").environ.get("USERPROFILE", ".")) / "Documents",
    Path(__import__("os").environ.get("USERPROFILE", ".")) / "Desktop",
    Path(__import__("os").environ.get("USERPROFILE", ".")) / "Downloads",
]

# Where this project lives — never allow deleting project/system files
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class DeleteFileTool(Tool):
    name = "delete_file"
    description = "Move a file to the Recycle Bin (recoverable). Requires the exact file path, e.g. from search_files."
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Full path of the file to delete"}},
        "required": ["path"],
    }
    category = "confirmation"
    destructive = True

    def execute(self, **kwargs) -> ToolResult:
        import os

        import send2trash

        raw = str(kwargs.get("path", "")).strip().strip('"')
        path = Path(raw)
        if not raw or not path.is_file():
            return ToolResult.fail("That file doesn't exist. Use the file search first.")
        resolved = path.resolve()
        if _PROJECT_ROOT in resolved.parents or resolved.drive.lower() == "c:" and resolved.parent == Path("C:\\"):
            return ToolResult.fail("For safety I won't delete files from system or project folders.")
        if not any(ud in resolved.parents for ud in USER_DIRS):
            return ToolResult.fail(
                "For safety I only delete files inside your Documents, Desktop or Downloads folders."
            )
        try:
            send2trash.send2trash(str(resolved))
            log.info("Sent to recycle bin: %s", resolved)
            return ToolResult.ok(f"Moved {path.name} to the Recycle Bin.")
        except Exception as exc:
            log.error("Delete failed for %s: %s", resolved, exc)
            return ToolResult.fail(f"I couldn't delete that file. ({exc})")
