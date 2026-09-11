"""Browser tools: open URLs and web search (standard browser, no automation)."""
from __future__ import annotations

import webbrowser
from urllib.parse import quote_plus

from app.tools.base import Tool, ToolResult
from app.utils.logger import get_logger

log = get_logger(__name__)

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={}",
}

WELL_KNOWN_SITES = {
    "youtube": "https://www.youtube.com",
    "github": "https://www.github.com",
    "gmail": "https://mail.google.com",
    "google": "https://www.google.com",
    "twitter": "https://www.twitter.com",
    "linkedin": "https://www.linkedin.com",
    "netflix": "https://www.netflix.com",
    "amazon": "https://www.amazon.com",
    "stackoverflow": "https://www.stackoverflow.com",
    "chatgpt": "https://www.chatgpt.com",
}


class OpenWebsite(Tool):
    name = "open_website"
    description = "Open a website in the default browser. Use for well-known sites by name, or with a full URL."
    schema = {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "Site name like 'youtube' or a full URL"}},
        "required": ["url"],
    }
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        raw = str(kwargs.get("url", "")).strip()
        if not raw:
            return ToolResult.fail("No website was specified.")
        target = raw
        if not raw.startswith(("http://", "https://")):
            key = raw.lower().replace(" ", "").replace(".com", "")
            target = WELL_KNOWN_SITES.get(key, f"https://{raw.replace(' ', '')}.com")
        try:
            webbrowser.open(target)
            log.info("Opened website: %s", target)
            return ToolResult.ok(f"Opening {raw}.", url=target)
        except Exception as exc:
            log.error("Failed to open %s: %s", target, exc)
            return ToolResult.fail(f"I couldn't open {raw}. ({exc})")


class GoogleSearch(Tool):
    name = "google_search"
    description = "Search the web (Google) for a query and show results in the browser."
    schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search query"}},
        "required": ["query"],
    }
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()
        if not query:
            return ToolResult.fail("No search query was provided.")
        url = SEARCH_ENGINES["google"].format(quote_plus(query))
        try:
            webbrowser.open(url)
            log.info("Web search: %s", query)
            return ToolResult.ok(f"Searching the web for '{query}'.", url=url)
        except Exception as exc:
            log.error("Search failed: %s", exc)
            return ToolResult.fail(f"I couldn't run the search. ({exc})")

class YouTubeSearch(Tool):
    name = "youtube_search"
    description = "Search YouTube for a query and show the results in the browser."
    schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find on YouTube"
            }
        },
        "required": ["query"],
    }
    category = "safe"

    def execute(self, **kwargs) -> ToolResult:
        query = str(kwargs.get("query", "")).strip()

        if not query:
            return ToolResult.fail("No YouTube search query was provided.")

        url = (
            "https://www.youtube.com/results?search_query="
            + quote_plus(query)
        )

        try:
            webbrowser.open(url)
            log.info("YouTube search: %s", query)

            return ToolResult.ok(
                f"Searching YouTube for '{query}'.",
                url=url
            )

        except Exception as exc:
            log.error("YouTube search failed: %s", exc)
            return ToolResult.fail(
                f"I couldn't search YouTube. ({exc})"
            )