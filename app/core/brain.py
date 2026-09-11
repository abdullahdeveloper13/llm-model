"""The AI Brain.

Turns a user transcript into a structured decision:
    {"type": "tool_call", "tool": "open_app", "arguments": {...}}
or  {"type": "conversation", "response": "..."}

Two strategies:
  * LLMBrain  — OpenAI-compatible tool calling (no arbitrary code from the
    model: it may only *request* registered tools; the executor runs them).
  * RuleBasedBrain — dependency-free fallback so the assistant still parses
    common commands offline / without an API key / in tests.

The Planner tries the LLM first and falls back to rules on any failure.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.agent.registry import ToolRegistry
from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)

SYSTEM_PROMPT = """You are a local Windows voice assistant. Classify the user's request.

Reply ONLY with JSON, one of:
{"type": "tool_call", "tool": "<tool name>", "arguments": {...}}
{"type": "conversation", "response": "<short spoken reply>"}

Rules:
- You may ONLY use tools from the provided list. Never invent tools.
- Never generate shell commands, code, or file paths — only tool calls.
- For destructive requests (shutdown, restart, delete, whatsapp calls) still
  emit the tool call; the assistant will ask the user to confirm.
- For greetings, small talk, or capability questions, reply with "conversation".
- Keep spoken replies under 30 words."""


class BrainDecision(BaseModel):
    type: str = Field(pattern="^(tool_call|conversation)$")
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    response: str = ""


class Brain(ABC):
    @abstractmethod
    def decide(self, user_text: str, history: list[dict[str, str]] | None = None) -> BrainDecision: ...


class LLMBrain(Brain):
    """Uses an OpenAI-compatible chat-completions endpoint with tool calling."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def decide(self, user_text: str, history: list[dict[str, str]] | None = None) -> BrainDecision:
        from openai import OpenAI

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += (history or [])[-10:]
        messages.append({"role": "user", "content": user_text})

        log.info("LLM thinking (%s)...", settings.openai_model)
        try:
            resp = client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,  # type: ignore[arg-type]
                tools=self.registry.schemas(),  # type: ignore[arg-type]
                tool_choice="auto",
                temperature=0.2,
                timeout=30,
            )
        except Exception as exc:
            log.error("LLM call failed: %s", exc)
            raise

        choice = resp.choices[0]
        call = choice.message.tool_calls[0] if choice.message.tool_calls else None
        if call:
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            log.info("LLM tool request: %s(%s)", call.function.name, args)
            return BrainDecision(type="tool_call", tool=call.function.name, arguments=args)

        text = (choice.message.content or "").strip()
        return self._parse_text_json(text) if text.startswith("{") else BrainDecision(type="conversation", response=text)

    def _parse_text_json(self, text: str) -> BrainDecision:
        try:
            return BrainDecision.model_validate(json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            return BrainDecision(type="conversation", response=text)


class RuleBasedBrain(Brain):
    """Offline keyword parser — covers common assistant commands."""

    APP_WORDS = ("open", "launch", "start", "run", "bring up")

    SITES = {
        "youtube": "youtube",
        "github": "github",
        "gmail": "gmail",
        "netflix": "netflix",
        "linkedin": "linkedin",
        "twitter": "twitter",
        "amazon": "amazon",
        "stackoverflow": "stackoverflow",
        "chatgpt": "chatgpt",
    }

    MEDIA = {
        "play": "play",
        "pause": "pause",
        "next": "next",
        "previous": "previous",
        "mute": "mute",
        "volume up": "volume_up",
        "louder": "volume_up",
        "quieter": "volume_down",
    }

    def decide(self, user_text: str, history=None) -> BrainDecision:
        t = user_text.lower().strip()

        # ---------------------------------------------------------
        # Small talk
        # ---------------------------------------------------------
        if t in ("hello", "hi", "hey") or t.startswith("hello "):
            return BrainDecision(
                type="conversation",
                response="Hello! How can I help you?"
            )

        if "how are you" in t:
            return BrainDecision(
                type="conversation",
                response="I'm running well, thank you! What can I do for you?"
            )

        if "what can you do" in t or "explain what you can control" in t:
            return BrainDecision(
                type="conversation",
                response=(
                    "I can open apps and websites, search the web, control media, "
                    "report CPU and RAM usage, search files, start WhatsApp calls "
                    "pending your confirmation, and shut down or restart this "
                    "computer after confirmation."
                ),
            )

        if "thank" in t:
            return BrainDecision(
                type="conversation",
                response="You're welcome!"
            )

        # ---------------------------------------------------------
        # System power
        # ---------------------------------------------------------
        if "cancel" in t and (
            "shutdown" in t
            or "shut down" in t
            or "restart" in t
            or "reboot" in t
        ):
            return BrainDecision(
                type="tool_call",
                tool="cancel_shutdown",
                arguments={}
            )

        if "shut down" in t or "shutdown" in t:
            return BrainDecision(
                type="tool_call",
                tool="shutdown",
                arguments={}
            )

        if "restart" in t or "reboot" in t:
            return BrainDecision(
                type="tool_call",
                tool="restart",
                arguments={}
            )

        # ---------------------------------------------------------
        # System information
        # ---------------------------------------------------------
        system_info_phrases = (
            "system information",
            "system info",
            "system status",
            "computer information",
            "computer info",
            "computer status",
            "pc information",
            "pc info",
            "pc status",
            "show system",
            "show computer",
            "check system",
            "check computer",
            "system specs",
            "computer specs",
            "pc specs",
        )

        if any(phrase in t for phrase in system_info_phrases):
            return BrainDecision(
                type="tool_call",
                tool="system_info",
                arguments={}
            )

        if "cpu" in t:
            return BrainDecision(
                type="tool_call",
                tool="system_info",
                arguments={"detail": "cpu"}
            )

        if "ram" in t or "memory" in t:
            return BrainDecision(
                type="tool_call",
                tool="system_info",
                arguments={"detail": "ram"}
            )

        # ---------------------------------------------------------
        # WhatsApp
        # ---------------------------------------------------------
        if t.startswith("call ") or t.startswith("phone "):
            contact = (
                t.split()[1].capitalize()
                if len(t.split()) > 1
                else ""
            )

            return BrainDecision(
                type="tool_call",
                tool="whatsapp_call",
                arguments={"contact": contact}
            )

        if "whatsapp" in t:
            if (
                "call" in t
                or "phone" in t
                or "message" in t
            ):
                contact = self._after_word(
                    t,
                    ("call", "phone", "message")
                )

                return BrainDecision(
                    type="tool_call",
                    tool="whatsapp_call",
                    arguments={"contact": contact}
                )

            return BrainDecision(
                type="tool_call",
                tool="open_whatsapp",
                arguments={}
            )

        # ---------------------------------------------------------
        # YouTube search
        #
        # IMPORTANT:
        # "search Python tutorials on YouTube"
        # should search YouTube rather than Google.
        # ---------------------------------------------------------
        youtube_search_phrases = (
            "search youtube for",
            "search youtube",
            "search on youtube for",
            "search on youtube",
            "youtube search for",
            "youtube search",
            "find on youtube",
            "find in youtube",
            "look up on youtube",
            "look for on youtube",
        )

        for prefix in youtube_search_phrases:
            if t.startswith(prefix):
                query = t[len(prefix):].strip(" ,.?!")

                if query:
                    return BrainDecision(
                        type="tool_call",
                        tool="youtube_search",
                        arguments={"query": query}
                    )

        # Also handle:
        # "search Python tutorials on YouTube"
        # "find Python tutorials on YouTube"
        # "look for Python tutorials on YouTube"
        youtube_markers = (
            " on youtube",
            " in youtube",
        )

        if any(marker in t for marker in youtube_markers):
            query = t

            for prefix in (
                "search for ",
                "search ",
                "find ",
                "look for ",
                "look up ",
            ):
                if query.startswith(prefix):
                    query = query[len(prefix):]
                    break

            for marker in youtube_markers:
                if marker in query:
                    query = query.split(marker, 1)[0]
                    break

            query = query.strip(" ,.?!")

            if query:
                return BrainDecision(
                    type="tool_call",
                    tool="youtube_search",
                    arguments={"query": query}
                )

        # ---------------------------------------------------------
        # Google / general web search
        # ---------------------------------------------------------
        search_prefixes = (
            "search google for",
            "search the web for",
            "google",
            "search for",
            "search",
        )

        for prefix in search_prefixes:
            if t.startswith(prefix):
                query = t[len(prefix):].strip(" ,.?!")

                if query:
                    return BrainDecision(
                        type="tool_call",
                        tool="google_search",
                        arguments={"query": query}
                    )

        # ---------------------------------------------------------
        # Open website
        # ---------------------------------------------------------
        if any(w in t for w in ("open", "go to", "visit")):
            site = next(
                (k for k in self.SITES if k in t),
                None
            )

            if site:
                return BrainDecision(
                    type="tool_call",
                    tool="open_website",
                    arguments={"url": site}
                )

        # ---------------------------------------------------------
        # Media
        # ---------------------------------------------------------
        for phrase, action in self.MEDIA.items():
            if phrase in t:
                return BrainDecision(
                    type="tool_call",
                    tool="media_control",
                    arguments={"action": action}
                )

        # ---------------------------------------------------------
        # Open application
        # ---------------------------------------------------------
        if any(w in t for w in self.APP_WORDS):
            app = self._extract_app(t)

            if app:
                return BrainDecision(
                    type="tool_call",
                    tool="open_app",
                    arguments={"application": app}
                )

        # ---------------------------------------------------------
        # Files
        # ---------------------------------------------------------
        if "find" in t or "search my files" in t:
            frag = self._after_word(
                t,
                ("find", "look for")
            )

            if frag:
                return BrainDecision(
                    type="tool_call",
                    tool="search_files",
                    arguments={"query": frag}
                )

        # ---------------------------------------------------------
        # Unknown command
        # ---------------------------------------------------------
        return BrainDecision(
            type="conversation",
            response=(
                "I'm not sure how to help with that. "
                "You can ask me to open apps, search the web, "
                "or check system status."
            )
        )

    def _extract_app(self, t: str) -> str:
        for w in self.APP_WORDS:
            if w in t:
                after = t.split(w, 1)[1].strip(" ,.?!")

                words = after.split()

                words = [
                    x for x in words
                    if x not in (
                        "my",
                        "the",
                        "for",
                        "me",
                        "please",
                        "app",
                        "application",
                    )
                ]

                if words:
                    return (
                        " ".join(words[:3])
                        .replace("visual studio code", "code")
                        .replace("vs code", "code")
                    )

        return ""

    def _after_word(
        self,
        t: str,
        words: tuple[str, ...]
    ) -> str:
        for w in words:
            if w in t:
                after = t.split(w, 1)[1].strip(" ,.?!")

                if after:
                    return after.split()[0].capitalize()

        return ""
