from __future__ import annotations

from unittest.mock import Mock

import numpy as np

from app.agent.registry import build_default_registry
from app.core.orchestrator import Orchestrator
from app.storage.database import Database
from app.core.memory import Memory
from app.tools.base import ToolResult
from app.voice.microphone import Microphone
from app.voice.speech_to_text import SpeechToText, WhisperSTT


class FakeWhatsApp:
    def __init__(self, *, message_ok: bool = True, call_ok: bool = True) -> None:
        self.message_ok = message_ok
        self.call_ok = call_ok
        self.calls: list[tuple[str, str]] = []

    def open_app(self):
        self.calls.append(("open", ""))
        return ToolResult.ok("Opening WhatsApp.")

    def _window(self):
        return object()

    def _open_chat(self, _window, name):
        self.calls.append(("chat", name))
        return object()

    def message_contact(self, name, message):
        self.calls.append((name, message))
        return ToolResult.ok("Message sent.") if self.message_ok else ToolResult.fail("Message UI failed.")

    def call_contact_auto(self, name):
        self.calls.append(("call", name))
        return ToolResult.ok("Call started.") if self.call_ok else ToolResult.fail("Call UI failed.")


def _orchestrator() -> Orchestrator:
    return Orchestrator(registry=build_default_registry())


def _patch_whatsapp(orch: Orchestrator, fake: FakeWhatsApp) -> None:
    for name in ("open_whatsapp", "whatsapp_open_chat", "whatsapp_message_auto", "whatsapp_call_auto"):
        tool = orch.registry.get(name)
        if tool is not None:
            tool.provider = fake


def test_production_path_english_roman_urdu_and_urdu(monkeypatch) -> None:
    orch = _orchestrator()
    opened: list[str] = []
    monkeypatch.setattr(orch.registry.get("open_app"), "execute", lambda **kw: (opened.append(kw["application"]) or ToolResult.ok("opened")))
    assert orch.handle("Open Chrome").tool == "open_app"
    assert orch.handle("Chrome kholo").tool == "open_app"
    assert orch.handle("کروم کھولو").tool == "open_app"
    assert opened == ["Chrome", "Chrome", "chrome"]


def test_production_path_multistep_stops_after_failure(monkeypatch) -> None:
    orch = _orchestrator()
    calls: list[str] = []
    monkeypatch.setattr(orch.registry.get("open_app"), "execute", lambda **kw: (calls.append("open") or ToolResult.fail("open failed")))
    monkeypatch.setattr(orch.registry.get("type_text"), "execute", lambda **kw: (calls.append("type") or ToolResult.ok("typed")))
    result = orch.handle("Notepad kholo aur Hello World likho")
    assert not result.success and "Step 1 failed" in result.response
    assert calls == ["open"]


def test_production_path_multistep_runs_in_order(monkeypatch) -> None:
    orch = _orchestrator()
    calls: list[tuple[str, dict]] = []
    monkeypatch.setattr(orch.registry.get("open_app"), "execute", lambda **kw: (calls.append(("open_app", kw)) or ToolResult.ok("opened")))
    monkeypatch.setattr(orch.registry.get("open_website"), "execute", lambda **kw: (calls.append(("open_website", kw)) or ToolResult.ok("website")))
    monkeypatch.setattr(orch.registry.get("google_search"), "execute", lambda **kw: (calls.append(("google_search", kw)) or ToolResult.ok("searched")))
    result = orch.handle("Chrome kholo, YouTube open karo aur Python tutorials search karo")
    assert result.success
    assert [name for name, _ in calls] == ["open_app", "open_website", "google_search"]


def test_llm_failure_cannot_block_deterministic_command(monkeypatch) -> None:
    orch = _orchestrator()
    llm = Mock()
    llm.decide.side_effect = TimeoutError("quota/timeout")
    orch.planner.llm_brain = llm
    monkeypatch.setattr(orch.registry.get("open_app"), "execute", lambda **kw: ToolResult.ok("opened"))
    result = orch.handle("Open Chrome")
    assert result.success and result.tool == "open_app"
    llm.decide.assert_not_called()


def test_malformed_llm_response_falls_back_to_local_parser(monkeypatch) -> None:
    orch = _orchestrator()
    llm = Mock()
    from app.core.brain import BrainDecision
    llm.decide.return_value = BrainDecision(type="conversation", response="{not valid command json")
    orch.planner.llm_brain = llm
    monkeypatch.setattr(orch.registry.get("open_app"), "execute", lambda **kw: ToolResult.ok("opened"))
    result = orch.handle("What is the weather in Lahore")
    assert result.success and result.response == "I'm not sure how to help with that."


def test_whatsapp_auto_paths_do_not_confirm_and_fail_honestly() -> None:
    orch = _orchestrator()
    fake = FakeWhatsApp(message_ok=False, call_ok=False)
    _patch_whatsapp(orch, fake)
    message = orch.handle("WhatsApp kholo aur Mama ko message bhejo ke hello")
    assert not message.awaiting_confirmation and not message.success
    call = orch.handle("WhatsApp kholo aur Mama ko call karo")
    assert not call.awaiting_confirmation and not call.success


def test_context_followup_stays_session_local() -> None:
    orch = _orchestrator()
    fake = FakeWhatsApp()
    _patch_whatsapp(orch, fake)
    assert orch.handle("Open WhatsApp").success
    assert orch.handle("Open Mama").tool == "whatsapp_open_chat"
    assert "What should" in orch.handle("Send her a message").response
    result = orch.handle("Tell her I'm coming home")
    assert result.tool == "whatsapp_message_auto"
    orch.reset_session()
    assert orch.handle("Tell her I'm coming home").tool == ""


def test_destructive_actions_still_confirm() -> None:
    orch = _orchestrator()
    assert orch.handle("shutdown").awaiting_confirmation
    assert orch.handle("restart").awaiting_confirmation
    assert orch.handle("delete file C:/Users/test/old.txt").awaiting_confirmation


def test_sensitive_path_does_not_enter_memory(tmp_path) -> None:
    memory = Memory(Database(path=str(tmp_path / "commands.db")))
    orch = Orchestrator(registry=build_default_registry(), memory=memory)
    llm = Mock()
    orch.planner.llm_brain = llm
    assert orch.handle("Enter PIN").success
    orch.handle("one two three four")
    orch.handle("Enter")
    llm.decide.assert_not_called()
    assert all("1234" not in str(row.model_dump()) for row in memory.db.recent(20))


class _RecoveringMic:
    def __init__(self):
        self.count = 0

    def record(self):
        self.count += 1
        if self.count == 1:
            from app.voice.microphone import MicrophoneError
            raise MicrophoneError("temporary")
        return np.zeros(0, dtype=np.float32)


class _EmptySTT(SpeechToText):
    def transcribe(self, audio):
        return ""


def test_voice_round_recovers_from_temporary_mic_failure() -> None:
    from app.core.assistant import Assistant
    orch = _orchestrator()
    mic = _RecoveringMic()
    assistant = Assistant(orch, mic=mic, stt=_EmptySTT(), tts=Mock())
    assistant.retry_delay = 0
    assert assistant.listen_once()[0] == ""
    assert assistant.listen_once()[0] == ""
    assert mic.count == 2


def test_microphone_vad_uses_preroll_and_returns_on_queue_starvation(monkeypatch) -> None:
    import app.voice.microphone as microphone_module

    frame_count = 16000 * 30 // 1000
    silence = np.full(frame_count, 0.001, dtype=np.float32)
    speech = np.full(frame_count, 0.05, dtype=np.float32)

    class Stream:
        def __enter__(self):
            for frame in [silence] * 10 + [speech] * 8 + [silence] * 4:
                callback(frame, len(frame), None, None)
            return self

        def __exit__(self, *_):
            return False

    def make_stream(**kwargs):
        nonlocal callback
        callback = kwargs["callback"]
        return Stream()

    callback = None
    monkeypatch.setattr(microphone_module.sd, "InputStream", make_stream)
    mic = Microphone(silence_limit_ms=90, min_speech_ms=120, pre_roll_ms=90, queue_timeout=0.001, max_queue_timeouts=1)
    audio = mic.record()
    assert audio.size >= frame_count * 8
    assert audio.size > frame_count * 8  # includes pre-roll and trailing silence

    class EmptyStream:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(microphone_module.sd, "InputStream", lambda **_: EmptyStream())
    assert mic.record().size == 0


def test_whisper_is_multilingual_and_does_not_reuse_previous_text() -> None:
    class Segment:
        text = "hello"

    class Model:
        def __init__(self):
            self.kwargs = {}

        def transcribe(self, audio, **kwargs):
            self.kwargs = kwargs
            return [Segment()], object()

    stt = WhisperSTT()
    model = Model()
    stt._model = model
    assert stt.transcribe(np.ones(1600, dtype=np.float32)) == "hello"
    assert model.kwargs["language"] is None
    assert model.kwargs["task"] == "transcribe"
    assert model.kwargs["condition_on_previous_text"] is False
