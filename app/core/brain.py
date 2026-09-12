"""Local-first command understanding with an optional OpenAI tool-calling brain."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agent.registry import ToolRegistry
from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You are a local Windows voice assistant. Reply only with JSON:
{\"type\":\"tool_call\",\"tool\":\"registered_name\",\"arguments\":{}}
or {\"type\":\"conversation\",\"response\":\"short reply\"}. Never emit shell, code, or unregistered tools."""


class BrainDecision(BaseModel):
    type: str = Field(pattern="^(tool_call|conversation)$")
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    response: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    sensitive: bool = False


class Brain(ABC):
    @abstractmethod
    def decide(self, user_text: str, history: list[dict[str, str]] | None = None) -> BrainDecision: ...


class LLMBrain(Brain):
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def decide(self, user_text: str, history=None) -> BrainDecision:
        from openai import OpenAI
        client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += (history or [])[-10:]
        messages.append({"role": "user", "content": user_text})
        try:
            resp = client.chat.completions.create(model=settings.openai_model, messages=messages,
                tools=self.registry.schemas(), tool_choice="auto", temperature=0.2, timeout=30)
            choice = resp.choices[0]
            call = choice.message.tool_calls[0] if choice.message.tool_calls else None
            if call:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                return BrainDecision(type="tool_call", tool=call.function.name, arguments=args)
            text = (choice.message.content or "").strip()
            return self._parse_text_json(text) if text.startswith("{") else BrainDecision(type="conversation", response=text)
        except Exception:
            log.warning("LLM unavailable; using local command parser", exc_info=True)
            raise

    def _parse_text_json(self, text: str) -> BrainDecision:
        try:
            return BrainDecision.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            return BrainDecision(type="conversation", response=text)


class RuleBasedBrain(Brain):
    """Deterministic multilingual fallback for common computer commands."""

    SITES = {"youtube", "github", "gmail", "netflix", "linkedin", "twitter", "amazon", "stackoverflow", "chatgpt"}
    OPEN_WORDS = ("open", "launch", "start", "run", "kholo", "کھولو", "khol", "open karo", "اوپن کرو")
    APP_ALIASES = {
        "کروم": "chrome", "نوٹ پیڈ": "notepad", "واٹس ایپ": "whatsapp",
        "یوٹیوب": "youtube", "سیٹنگز": "settings", "کیلکولیٹر": "calculator",
    }
    NUMBER_WORDS = {"zero":"0", "one":"1", "two":"2", "three":"3", "four":"4", "five":"5", "six":"6", "seven":"7", "eight":"8", "nine":"9", "oh":"0", "sifar":"0", "ایک":"1", "دو":"2", "تین":"3", "چار":"4", "پانچ":"5"}

    def __init__(self) -> None:
        self.sensitive_mode = False
        self.last_contact = ""
        self.current_application = ""

    def reset(self) -> None:
        self.sensitive_mode = False
        self.last_contact = ""
        self.current_application = ""

    def decide(self, user_text: str, history=None) -> BrainDecision:
        raw = user_text.strip()
        t = raw.lower()
        if self.sensitive_mode:
            return self._sensitive(raw)
        if re.search(r"\b(enter|type|dictate)\s+(pin|password|passcode|otp|code)\b", t):
            self.sensitive_mode = True
            return BrainDecision(type="conversation", response="Sensitive dictation mode enabled. Please dictate the value.", sensitive=True)
        if t in {"hello", "hi", "hey"} or t.startswith("hello "):
            return BrainDecision(type="conversation", response="Hello. How can I help?")
        if "how are you" in t:
            return BrainDecision(type="conversation", response="I'm ready.")
        if "thank" in t:
            return BrainDecision(type="conversation", response="You're welcome.")
        if t.startswith("call ") or t.startswith("phone "):
            contact = t.split(None, 1)[1].strip().title()
            tool = "whatsapp_call_auto" if self.current_application == "whatsapp" else "whatsapp_call"
            return self._call(tool, contact=contact)
        if self.last_contact and re.search(r"\b(tell her|send her|message her)\b", t):
            message = re.split(r"\b(?:tell her|send her|message her)\b", raw, maxsplit=1, flags=re.I)[-1].strip()
            if message.lower().startswith("a message"):
                message = message[9:].strip()
            if message:
                return self._call("whatsapp_message_auto", contact=self.last_contact, message=message)
            return BrainDecision(type="conversation", response="What should I tell her?")
        message_match = re.match(r"^message\s+(.+?)\s+(.+)$", raw, flags=re.I)
        if message_match:
            contact, message = message_match.groups()
            self.last_contact = contact.strip().title()
            return self._call("whatsapp_message_auto", contact=self.last_contact, message=message.strip())
        steps = self._split_steps(raw)
        if len(steps) > 1:
            decisions = [self._single(s) for s in steps]
            calls = [d for d in decisions if d.type == "tool_call"]
            if len(calls) == len(decisions):
                return BrainDecision(type="tool_call", steps=[{"tool": d.tool, "arguments": d.arguments} for d in calls])
        return self._single(raw)

    def _single(self, raw: str) -> BrainDecision:
        t = raw.lower().strip()
        if "cancel" in t and ("shutdown" in t or "restart" in t):
            return self._call("cancel_shutdown")
        if t.startswith("delete file ") or t.startswith("delete "):
            path = re.sub(r"^delete(?:\s+file)?\s+", "", raw, flags=re.I).strip()
            return self._call("delete_file", path=path) if path else self._conversation()
        if "shut down" in t or "shutdown" in t:
            return self._call("shutdown")
        if "restart" in t or "reboot" in t:
            return self._call("restart")
        if any(x in t for x in ("system info", "system information", "computer status", "cpu", "ram", "memory")):
            detail = "cpu" if "cpu" in t else "ram" if "ram" in t or "memory" in t else "all"
            return self._call("system_info", detail=detail)
        if any(x in t for x in ("volume up", "volume barhao", "louder", "awaaz barhao", "والیوم بڑھاؤ", "آواز بڑھاؤ")):
            return self._call("media_control", action="volume_up")
        if any(x in t for x in ("volume down", "volume kam", "quieter", "awaaz kam", "والیوم کم", "آواز کم")):
            return self._call("media_control", action="volume_down")
        if "mute" in t or "آواز بند" in t:
            return self._call("media_control", action="mute")
        if "list running" in t or "open windows" in t:
            return self._call("window_control", action="list")
        window_match = re.search(r"^(minimize|maximize|switch to|focus)\s+(.+)$", t)
        if window_match:
            action = window_match.group(1).replace("switch to", "switch")
            return self._call("window_control", action=action, application=window_match.group(2).strip())
        if t in {"go back", "back", "browser back", "go forward", "forward", "new tab", "close tab"}:
            action = "back" if "back" in t else "forward" if "forward" in t else "new_tab" if "new" in t else "close_tab"
            return self._call("browser_navigation", action=action)
        if "band karo" in t or "بند کرو" in t or t.startswith("close "):
            target = re.sub(r"^(close\s+)|\s+(band karo|بند کرو)$", "", raw, flags=re.I).strip()
            return self._call("close_app", application=target)
        if "whatsapp" in t or "واٹس ایپ" in t or "ko call" in t or "ko message" in t:
            return self._whatsapp(t)
        if any(t.startswith(p) for p in ("search ", "search for ", "google ")) or "dhoondo" in t or "ڈھونڈو" in t or t.endswith("search karo"):
            q = re.sub(r"^(search( for)?|google)\s+", "", t).strip()
            q = re.sub(r"\s+(search karo|dhoondo|ڈھونڈو)$", "", q).strip()
            return self._call("google_search", query=q) if q else self._conversation()
        if "youtube" in t and "search" in t:
            q = re.sub(r".*?search\s+", "", t).strip()
            return self._call("youtube_search", query=q)
        if re.search(r"\b(press|dabao|hotkey)\b", t) or t in {"enter", "tab", "escape", "backspace", "space"} or re.match(r"^(ctrl|alt|shift)\s*\+?\s*\w+$", t):
            return self._call("press_keys", keys=self._keys(raw))
        if t.startswith("type ") or " likho" in t:
            text = raw[5:].strip() if t.startswith("type ") else re.sub(r"\s+likho.*$", "", raw, flags=re.I)
            return self._call("type_text", text=text)
        if any(w in t for w in self.OPEN_WORDS):
            target = self._target(raw)
            target = self.APP_ALIASES.get(target.lower(), target)
            if target.lower() == "whatsapp":
                self.current_application = "whatsapp"
                return self._call("open_whatsapp")
            if self.current_application == "whatsapp" and target:
                self.last_contact = target.title()
                return self._call("whatsapp_open_chat", contact=self.last_contact)
            if target.lower() == "notepad":
                self.current_application = "notepad"
            if target.lower() in self.SITES:
                self.current_application = target.lower()
                return self._call("open_website", url=target)
            if target:
                return self._call("open_app", application=target)
        if "find" in t or "search my files" in t:
            return self._call("search_files", query=re.sub(r".*?(find|search my files)\s+", "", t))
        return self._conversation()

    def _whatsapp(self, t: str) -> BrainDecision:
        contact_match = re.search(r"(?:whatsapp\s+)?(?:open\s+)?(.+?)\s+ko\s+(?:call|message)", t)
        contact = contact_match.group(1).strip() if contact_match else ""
        if not contact:
            contact_match = re.search(r"(?:call|message)\s+(.+?)(?:\s+(?:ko|ke|that|saying)\b|$)", t)
            contact = contact_match.group(1).strip() if contact_match else self.last_contact
        contact = re.sub(r"^(whatsapp|open)\s+", "", contact).strip()
        if contact:
            self.last_contact = contact.title()
        if "whatsapp" in t or "واٹس ایپ" in t:
            self.current_application = "whatsapp"
        if "message" in t:
            message = re.split(r"\b(?:ke|that|saying)\b", t, maxsplit=1)[-1].strip() if re.search(r"\b(?:ke|that|saying)\b", t) else ""
            if not message and "tell her" in t:
                message = t.split("tell her", 1)[1].strip()
            return self._call("whatsapp_message_auto", contact=self.last_contact, message=message)
        if "call" in t:
            return self._call("whatsapp_call_auto", contact=self.last_contact)
        return self._call("open_whatsapp")

    def _sensitive(self, raw: str) -> BrainDecision:
        t = raw.lower().strip()
        controls = {"enter":"enter", "tab":"tab", "escape":"esc", "backspace":"backspace", "space":"space"}
        if t in controls:
            self.sensitive_mode = False if t in {"escape", "enter"} else True
            return self._call("press_keys", keys=[controls[t]], sensitive=True)
        digits = "".join(self.NUMBER_WORDS.get(w, w if w.isdigit() else "") for w in re.findall(r"[\w\u0600-\u06ff]+", t))
        if digits:
            return self._call("type_text", text=digits, sensitive=True)
        return self._call("type_text", text=raw, sensitive=True)

    def _split_steps(self, raw: str) -> list[str]:
        return [x.strip(" ,") for x in re.split(r"\s+(?:and|aur|اور)\s+|,", raw, flags=re.I) if x.strip()]

    def _target(self, raw: str) -> str:
        t = raw
        t = re.sub(r"^(please\s+)?(open|launch|start|run|kholo|کھولو|khol|اوپن)\s+", "", t, flags=re.I)
        t = re.sub(r"\s+(open\s+karo|kholo|khol|کھولو|اوپن\s+کرو)$", "", t, flags=re.I)
        return re.sub(r"\s+(my|the|app|application)$", "", t.strip(), flags=re.I)

    def _keys(self, raw: str) -> list[str]:
        text = re.sub(r"^(press|dabao|hotkey)\s+", "", raw, flags=re.I).replace("+", " ")
        text = re.sub(r"\s+(dabao|press)$", "", text, flags=re.I)
        return [x.lower() for x in text.split()]

    def _call(self, tool: str, sensitive: bool = False, **arguments: Any) -> BrainDecision:
        return BrainDecision(type="tool_call", tool=tool, arguments=arguments, sensitive=sensitive)

    def _conversation(self) -> BrainDecision:
        return BrainDecision(type="conversation", response="I'm not sure how to help with that.")
