"""Chrome profile-aware launching with post-launch process verification."""
from __future__ import annotations
import shutil, subprocess, time
from app.tools.base import Tool, ToolResult
from app.tools.apps.chrome_profiles import ChromeProfileManager
class ChromeManager:
    def __init__(self, profiles: ChromeProfileManager | None = None) -> None: self.profiles = profiles or ChromeProfileManager()
    def executable(self) -> str | None:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
            hit = shutil.which(name)
            if hit: return hit
        return None
    def launch(self, profile: str = "", url: str = "") -> ToolResult:
        executable = self.executable()
        if not executable: return ToolResult.fail("I couldn't find Chrome or Chromium on this computer.")
        matches = self.profiles.select(profile) if profile else []
        if profile and len(matches) != 1:
            if len(matches) > 1: return ToolResult.fail("I found multiple matching Chrome profiles. Please say the full profile name.", profiles=[p.as_dict() for p in matches])
            return ToolResult.fail(f"I couldn't find a Chrome profile named {profile}.", profiles=[p.as_dict() for p in self.profiles.discover()])
        args = [executable]
        if matches: args += [f"--profile-directory={matches[0].directory}"]
        if url: args.append(url)
        try:
            process = subprocess.Popen(args, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.5)
            if process.poll() is not None:
                # Chrome commonly hands a new request to an already-running
                # browser process and exits its launcher immediately.
                try:
                    running = subprocess.run(["pgrep", "-f", "chrome"], check=False, stdout=subprocess.DEVNULL).returncode == 0
                except OSError:
                    running = False
                if not running:
                    return ToolResult.fail("Chrome exited before it could open.", executable=executable)
            verified = True
            if shutil.which("wmctrl"):
                try:
                    windows = subprocess.check_output(["wmctrl", "-l"], text=True, stderr=subprocess.DEVNULL)
                    verified = "chrome" in windows.lower() or "chromium" in windows.lower()
                except (OSError, subprocess.SubprocessError):
                    verified = False
            if not verified:
                return ToolResult.fail("Chrome started, but I couldn't verify a visible Chrome window.", executable=executable)
            return ToolResult.ok(f"Chrome is open{f' with {matches[0].name}' if matches else ''}.", executable=executable, profile=matches[0].as_dict() if matches else {}, verified=True)
        except OSError as exc: return ToolResult.fail(f"I couldn't open Chrome. ({exc})")
class OpenChromeTool(Tool):
    name="open_chrome"; description="Open Chrome, optionally selecting a discovered profile and URL."; category="safe"
    schema={"type":"object","properties":{"profile":{"type":"string"},"url":{"type":"string"}}}
    def __init__(self, manager: ChromeManager | None = None): self.manager=manager or ChromeManager()
    def execute(self, **kwargs): return self.manager.launch(str(kwargs.get("profile", "")).strip(), str(kwargs.get("url", "")).strip())
