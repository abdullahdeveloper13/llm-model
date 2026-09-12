from __future__ import annotations

import numpy as np

from app.core.brain import RuleBasedBrain
from app.voice.speech_to_text import NullSTT, WhisperSTT


def test_multilingual_rule_commands() -> None:
    brain = RuleBasedBrain()
    assert brain.decide("Open Chrome").arguments == {"application": "Chrome"}
    assert brain.decide("Chrome kholo").arguments == {"application": "Chrome"}
    assert brain.decide("Chrome کھولو").arguments == {"application": "Chrome"}
    assert brain.decide("Chrome band karo").tool == "close_app"
    assert brain.decide("Python tutorials search karo").arguments == {"query": "python tutorials"}
    assert brain.decide("volume barhao").arguments == {"action": "volume_up"}


def test_multistep_and_whatsapp_message_are_local() -> None:
    brain = RuleBasedBrain()
    decision = brain.decide("WhatsApp kholo aur Mama ko message bhejo ke main ghar aa raha hoon")
    assert [s["tool"] for s in decision.steps] == ["open_whatsapp", "whatsapp_message_auto"]
    assert decision.steps[1]["arguments"]["contact"] == "Mama"
    assert "ghar aa raha hoon" in decision.steps[1]["arguments"]["message"]


def test_sensitive_dictation_is_local_and_redaction_safe() -> None:
    brain = RuleBasedBrain()
    start = brain.decide("Enter PIN")
    value = brain.decide("one two three four")
    enter = brain.decide("Enter")
    assert start.sensitive
    assert value.sensitive and value.tool == "type_text" and value.arguments == {"text": "1234"}
    assert enter.sensitive and enter.arguments == {"keys": ["enter"]}


def test_empty_stt_audio_does_not_load_whisper() -> None:
    assert NullSTT("ignored").transcribe(np.zeros(0, dtype=np.float32)) == "ignored"
    assert WhisperSTT().transcribe(np.zeros(0, dtype=np.float32)) == ""
