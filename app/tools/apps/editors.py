"""Safe CLI-based integration for Cursor and VS Code."""
from __future__ import annotations
import os, shutil, subprocess, sys
from pathlib import Path
from app.tools.base import Tool, ToolResult

class EditorManager:
    COMMANDS = {"cursor": ("cursor", "Cursor"), "code": ("code", "VS Code"), "vscode": ("code", "VS Code")}
    def find(self, editor: str) -> tuple[str, str] | None:
        command, label = self.COMMANDS.get(editor.lower().strip(), (editor, editor.title()))
        path = shutil.which(command)
        return (path, label) if path else None
    def open(self, editor: str, project: str = "") -> ToolResult:
        found = self.find(editor)
        if not found: return ToolResult.fail(f"I couldn't find {editor.title()} on this computer.", editor=editor, verified=False)
        command, label = found
        args = [command]
        if project: args.append(str(Path(project).expanduser().resolve()))
        try:
            process = subprocess.Popen(args, close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if process.poll() is not None:
                running = subprocess.run(["pgrep", "-f", Path(command).name], check=False, stdout=subprocess.DEVNULL).returncode == 0
                if not running: return ToolResult.fail(f"{label} exited before opening.", editor=label, verified=False)
            return ToolResult.ok(f"{label} is open.", editor=label, command=command, project=project, verified=True)
        except OSError as exc: return ToolResult.fail(f"I couldn't open {label}: {exc}", editor=label, verified=False)

class OpenEditorTool(Tool):
    name = "open_editor"
    description = "Open a project in Cursor or VS Code using its supported CLI when installed."
    schema = {"type":"object", "properties":{"editor":{"type":"string"},"project":{"type":"string"}},"required":["editor"]}
    category = "safe"
    def __init__(self, manager=None): self.manager=manager or EditorManager()
    def execute(self, **kwargs): return self.manager.open(str(kwargs.get("editor", "")), str(kwargs.get("project", "")))

class RunProjectTestsTool(Tool):
    name = "run_project_tests"
    description = "Run the configured project test command in the current project, with bounded output."
    schema = {"type":"object", "properties":{"project":{"type":"string"}}, "required":[]}
    category = "safe"
    def execute(self, **kwargs):
        root = Path(str(kwargs.get("project", Path.cwd()))).expanduser().resolve()
        if not root.is_dir(): return ToolResult.fail("The project folder does not exist.")
        commands = [("pytest", ["python", "-m", "pytest", "-q"]), ("node", ["npm", "test"])]
        if any(root.glob("test_*.py")) or (root / "tests").is_dir(): command = [os.environ.get("PYTHON", sys.executable), "-m", "pytest", "-q"]
        elif (root / "package.json").is_file(): command = ["npm", "test"]
        else: return ToolResult.fail("I couldn't identify a configured test command for this project.")
        try:
            completed = subprocess.run(command, cwd=root, capture_output=True, text=True, timeout=300, check=False)
            output = (completed.stdout + "\n" + completed.stderr)[-12000:]
            passed = completed.returncode == 0
            return (ToolResult.ok("Project tests passed.", project=str(root), command=command, output=output, verified=True)
                    if passed else ToolResult.fail("Project tests failed.", project=str(root), command=command, output=output, verified=True, returncode=completed.returncode))
        except (OSError, subprocess.TimeoutExpired) as exc: return ToolResult.fail(f"Test execution failed: {exc}", verified=False)
