"""Bounded, explicit file operations. Natural language never supplies a command."""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.tools.base import Tool, ToolResult


def _roots() -> list[Path]:
    profile = Path(os.environ.get("USERPROFILE", "."))
    return [profile / name for name in ("Documents", "Desktop", "Downloads", "Pictures")]


def _user_path(raw: str, *, must_exist: bool = False) -> Path:
    path = Path(raw.strip().strip('"')).expanduser().resolve()
    if not any(root.resolve() in path.parents or path == root.resolve() for root in _roots()):
        raise ValueError("For safety, file operations are limited to your user folders.")
    if must_exist and not path.exists():
        raise ValueError("That path does not exist.")
    return path


class FileOperationTool(Tool):
    name = "file_operation"
    description = "Open, create, rename, move, or copy a file in the user's folders."
    schema = {"type": "object", "properties": {"action": {"type": "string"}, "path": {"type": "string"}, "destination": {"type": "string"}}, "required": ["action", "path"]}
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        action = str(kwargs.get("action", "")).lower().strip()
        try:
            path = _user_path(str(kwargs.get("path", "")), must_exist=action != "create")
            if action == "open":
                os.startfile(str(path))
            elif action == "create":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(exist_ok=False)
            elif action == "rename":
                destination = _user_path(str(kwargs.get("destination", "")))
                path.rename(destination)
            elif action == "move":
                destination = _user_path(str(kwargs.get("destination", "")))
                shutil.move(str(path), str(destination))
            elif action == "copy":
                destination = _user_path(str(kwargs.get("destination", "")))
                shutil.copy2(path, destination)
            else:
                return ToolResult.fail("That file action is not supported.")
            return ToolResult.ok(f"File {action} complete.")
        except FileExistsError:
            return ToolResult.fail("A file already exists at that destination.")
        except Exception as exc:
            return ToolResult.fail(f"File operation failed. ({exc})")
