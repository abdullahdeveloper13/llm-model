from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from app.core.context import SessionContext
from app.core.task_engine import TaskEngine, TaskStatus
from app.tools.apps.chrome_profiles import ChromeProfileManager
from app.tools.browser.playwright_controller import BrowserController


def test_download_is_verified_and_sanitized(tmp_path: Path) -> None:
    controller = BrowserController(tmp_path)
    download = Mock(suggested_filename="../../report.pdf")
    download.save_as.side_effect = lambda path: Path(path).write_bytes(b"pdf")
    result = controller._save_download(download)
    assert result.success and result.data["verified"]
    assert result.data["path"] == str(tmp_path / "report.pdf")


def test_browser_locator_prefers_accessible_semantics() -> None:
    page = Mock()
    locator = BrowserController._locator(page, {"role": "button", "name": "Download"})
    page.get_by_role.assert_called_once_with("button", name="Download")
    assert locator is page.get_by_role.return_value


def test_profile_discovery_and_selection_are_dynamic(tmp_path: Path) -> None:
    root = tmp_path / ".config" / "google-chrome"
    (root / "Default").mkdir(parents=True)
    (root / "Profile 3").mkdir()
    (root / "Local State").write_text('{"profile":{"last_used":"Profile 3","info_cache":{"Default":{"name":"Abdullah"},"Profile 3":{"name":"Rafay"}}}}')
    profiles = ChromeProfileManager(tmp_path).discover()
    assert [p.name for p in profiles] == ["Abdullah", "Rafay"]
    assert ChromeProfileManager(tmp_path).select("Rafay")[0].directory == "Profile 3"


def test_task_engine_recovers_after_verification_failure() -> None:
    attempts = []
    def execute(step):
        attempts.append(step)
        return Mock(success=True, message="ok")
    def verify(step, outcome):
        return len(attempts) > 1
    task = TaskEngine(execute, verify, max_retries=1).run("goal", [{"action": "inspect"}])
    assert task.status == TaskStatus.COMPLETED
    assert len(attempts) == 2


def test_context_resolves_download_and_project_references() -> None:
    context = SessionContext(last_downloaded_file="/home/test/Downloads/report.pdf", active_project="/home/test/project")
    assert context.resolve("open the downloaded file") == "/home/test/Downloads/report.pdf"
    assert context.resolve("the downloaded file") == "/home/test/Downloads/report.pdf"
    assert context.resolve("this project") == "/home/test/project"
