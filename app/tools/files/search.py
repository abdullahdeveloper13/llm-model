"""File search tool — safe filename search under common user folders."""
from __future__ import annotations

import os
from pathlib import Path

from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

SEARCH_ROOTS = [
    Path(os.environ.get("USERPROFILE", ".")) / "Documents",
    Path(os.environ.get("USERPROFILE", ".")) / "Desktop",
    Path(os.environ.get("USERPROFILE", ".")) / "Downloads",
    Path(os.environ.get("USERPROFILE", ".")) / "Pictures",
]


class SearchFilesTool(Tool):
    name = "search_files"
    description = "Find files by name fragment in the user's Documents/Desktop/Downloads/Pictures folders."
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "File name fragment to search for"}},
        "required": ["query"],
    }
    category = "safe"

    def __init__(self, max_results: int = 10) -> None:
        self.max_results = max_results

    def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query", "")).strip().lower()
        if not query:
            return ToolResult.fail("No file name was provided.")
        hits: list[str] = []
        try:
            for root in SEARCH_ROOTS:
                if not root.exists():
                    continue
                for dirpath, _dirs, files in os.walk(root):
                    for f in files:
                        if query in f.lower():
                            hits.append(str(Path(dirpath) / f))
                            if len(hits) >= self.max_results:
                                break
                    if len(hits) >= self.max_results:
                        break
                if len(hits) >= self.max_results:
                    break
        except Exception as exc:
            log.error("File search failed: %s", exc)
            return ToolResult.fail(f"The file search failed. ({exc})")

        if not hits:
            return ToolResult.ok(f"I couldn't find any files matching '{query}'.", files=[])
        listing = "\n".join(hits[: self.max_results])
        return ToolResult.ok(f"I found {len(hits)} file(s):\n{listing}", files=hits)
