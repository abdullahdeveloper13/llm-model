"""Optional Playwright browser control with verified structured results."""
from __future__ import annotations
import os
import time
from pathlib import Path
from typing import Any
from app.tools.base import Tool, ToolResult
from app.tools.apps.chrome import ChromeManager
from app.tools.apps.chrome_profiles import ChromeProfileManager

class PlaywrightUnavailable(RuntimeError):
    pass

class BrowserController:
    def __init__(self, download_dir: Path | None = None) -> None:
        self.download_dir = (download_dir or Path.home() / "Downloads").expanduser().resolve()
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = None
        self.context = None
        self.page = None

    def _ensure(self, profile: str = ""):
        if self.page is not None:
            return self.page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightUnavailable("Playwright is not installed. Install requirements and run 'playwright install chromium'.") from exc
        executable = ChromeManager().executable()
        if not executable:
            raise PlaywrightUnavailable("Chrome or Chromium is not installed.")
        matches = ChromeProfileManager().select(profile) if profile else []
        if profile and len(matches) != 1:
            raise ValueError("The requested Chrome profile was not found uniquely.")
        user_data = matches[0].user_data_dir if matches else str(Path.home() / ".cache" / "orbital-browser")
        args = [f"--profile-directory={matches[0].directory}"] if matches else []
        self._playwright = sync_playwright().start()
        self.context = self._playwright.chromium.launch_persistent_context(
            user_data, executable_path=executable, headless=False,
            accept_downloads=True, args=args,
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self.page

    @staticmethod
    def _page_state(page) -> dict[str, Any]:
        return {"url": page.url, "title": page.title(), "text": page.locator("body").inner_text(timeout=3000)[:12000]}

    def act(self, action: str, **kwargs: Any) -> ToolResult:
        try:
            page = self._ensure(str(kwargs.get("profile", "")).strip())
            action = action.lower().strip()
            if action == "navigate":
                url = str(kwargs.get("url", "")).strip()
                if not url: return ToolResult.fail("No URL was specified.")
                if not url.startswith(("http://", "https://")):
                    url = "https://" + url.strip().replace(" ", "")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                return ToolResult.ok("Page loaded.", verified=page.url.startswith(("http://", "https://")), state=self._page_state(page))
            if action in {"inspect", "state"}:
                state = self._page_state(page)
                state["links"] = page.get_by_role("link").all_inner_texts()[:100]
                state["buttons"] = page.get_by_role("button").all_inner_texts()[:100]
                state["inputs"] = page.locator("input, textarea, select").evaluate_all("els => els.map(e => ({name:e.getAttribute('name'), placeholder:e.getAttribute('placeholder'), type:e.getAttribute('type')}))")[:100]
                return ToolResult.ok("Page inspected.", verified=True, state=state)
            if action in {"click", "download"}:
                locator = self._locator(page, kwargs)
                try:
                    with page.expect_download(timeout=3000) as download_info:
                        locator.click(timeout=10000)
                    return self._save_download(download_info.value)
                except Exception as exc:
                    if action == "download":
                        return ToolResult.fail(f"No verified download occurred: {exc}", verified=False)
                    locator.click(timeout=10000)
                    return ToolResult.ok("Element clicked.", verified=True, state=self._page_state(page))
            if action == "fill":
                locator = self._locator(page, kwargs)
                locator.fill(str(kwargs.get("value", "")))
                return ToolResult.ok("Field filled.", verified=locator.input_value() == str(kwargs.get("value", "")), state=self._page_state(page))
            if action == "press":
                self._locator(page, kwargs).press(str(kwargs.get("key", "Enter")))
                return ToolResult.ok("Key pressed.", verified=True, state=self._page_state(page))
            if action == "scroll":
                page.mouse.wheel(0, float(kwargs.get("amount", 700)))
                return ToolResult.ok("Page scrolled.", verified=True, state=self._page_state(page))
            if action == "select":
                locator = self._locator(page, kwargs)
                value = str(kwargs.get("value", ""))
                locator.select_option(value)
                return ToolResult.ok("Option selected.", verified=locator.input_value() == value, state=self._page_state(page))
            if action == "screenshot":
                path = Path(str(kwargs.get("path", self.download_dir / "orbital-page.png"))).expanduser().resolve()
                page.screenshot(path=str(path), full_page=True)
                return ToolResult.ok("Screenshot captured.", path=str(path), verified=path.is_file() and path.stat().st_size > 0)
            if action == "tabs":
                tabs = [{"url": p.url, "title": p.title()} for p in self.context.pages]
                return ToolResult.ok("Tabs inspected.", tabs=tabs, verified=True)
            if action == "new_tab":
                self.page = self.context.new_page()
                return ToolResult.ok("New tab opened.", tabs=len(self.context.pages), verified=True)
            if action == "close_tab":
                self.page.close()
                self.page = self.context.pages[-1] if self.context.pages else self.context.new_page()
                return ToolResult.ok("Tab closed.", tabs=len(self.context.pages), verified=True)
            return ToolResult.fail(f"Browser action '{action}' is not supported.")
        except PlaywrightUnavailable as exc:
            return ToolResult.fail(str(exc), capability="playwright")
        except Exception as exc:
            return ToolResult.fail(f"Browser action failed: {exc}", verified=False)

    @staticmethod
    def _locator(page, kwargs):
        role = str(kwargs.get("role", "")).strip()
        name = str(kwargs.get("name", "")).strip()
        label = str(kwargs.get("label", "")).strip()
        text = str(kwargs.get("text", "")).strip()
        placeholder = str(kwargs.get("placeholder", "")).strip()
        selector = str(kwargs.get("selector", "")).strip()
        if role: return page.get_by_role(role, name=name or None)
        if label: return page.get_by_label(label)
        if placeholder: return page.get_by_placeholder(placeholder)
        if text: return page.get_by_text(text, exact=True)
        if selector: return page.locator(selector)
        raise ValueError("A semantic locator is required.")

    def _save_download(self, download) -> ToolResult:
        filename = Path(download.suggested_filename).name
        target = self.download_dir / filename
        download.save_as(str(target))
        verified = target.is_file() and target.stat().st_size > 0
        if not verified: return ToolResult.fail("The download did not produce a non-empty file.", path=str(target), verified=False)
        return ToolResult.ok(f"Downloaded {filename}.", path=str(target), size=target.stat().st_size, verified=True)

    def close(self) -> None:
        if self.context: self.context.close()
        if self._playwright: self._playwright.stop()
        self.context = self.page = self._playwright = None

class BrowserControlTool(Tool):
    name = "browser_control"
    description = "Control a real browser through Playwright using semantic DOM/accessibility locators."
    schema = {"type":"object", "properties": {
        "action":{"type":"string"}, "url":{"type":"string"}, "profile":{"type":"string"}, "role":{"type":"string"}, "name":{"type":"string"}, "label":{"type":"string"}, "text":{"type":"string"}, "placeholder":{"type":"string"}, "selector":{"type":"string"}, "value":{"type":"string"}, "key":{"type":"string"}, "amount":{"type":"number"}, "path":{"type":"string"}
    }, "required":["action"]}
    category = "safe"
    _controller: BrowserController | None = None
    def __init__(self, controller: BrowserController | None = None): self.controller = controller or BrowserController()
    def execute(self, **kwargs): return self.controller.act(str(kwargs.get("action", "")), **kwargs)
