"""WhatsApp integration.

WhatsApp Desktop does not provide a supported public API for third-party
applications to automatically place calls.

This integration supports:
    * Opening WhatsApp Desktop using its Windows AppID.
    * Resolving contacts from the local contact book.
    * Opening the WhatsApp web deep link for a resolved contact.
    * Requiring the user to manually complete the call.

No screen-coordinate automation or unofficial WhatsApp APIs are used.
"""

from __future__ import annotations

import re
import subprocess
import time
import webbrowser

from app.tools.base import Tool, ToolResult
from app.tools.apps.detector import AppDetector
from app.tools.whatsapp.contacts import ContactBook
from app.utils.logger import get_logger


log = get_logger(__name__)


# Windows AppID for WhatsApp Desktop.
WHATSAPP_APP_ID = "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"


def normalize_e164(phone: str) -> str:
    """Convert a phone number to digits-only WhatsApp wa.me format.

    Example:
        +92 300-1234567 -> 923001234567
    """
    return re.sub(r"\D", "", phone)


class WhatsAppProvider:
    """Abstraction over supported WhatsApp mechanisms."""

    def __init__(
        self,
        contact_book: ContactBook | None = None,
        detector: AppDetector | None = None,
    ):
        self.contacts = contact_book or ContactBook()
        self.detector = detector or AppDetector()

    def open_app(self) -> ToolResult:
        """Launch WhatsApp Desktop on Windows."""

        try:
            subprocess.Popen(
                [
                    "explorer.exe",
                    f"shell:AppsFolder\\{WHATSAPP_APP_ID}",
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            log.info(
                "Launched WhatsApp using Windows AppID: %s",
                WHATSAPP_APP_ID,
            )

            return ToolResult.ok("Opening WhatsApp.")

        except Exception as exc:
            log.error("Failed to open WhatsApp: %s", exc)
            return ToolResult.fail(
                f"I couldn't open WhatsApp. ({exc})"
            )

    def call_contact(self, name: str) -> ToolResult:
        """Open the WhatsApp flow for a resolved contact."""

        name = name.strip()

        if not name:
            return ToolResult.fail(
                "Please provide the name of the WhatsApp contact."
            )

        matches = self.contacts.find(name)

        if not matches:
            return ToolResult.fail(
                f"I couldn't find a contact named '{name}'. "
                "Add them to data/contacts.json first.",
                matches=[],
            )

        # Do not guess when multiple contacts match.
        if len(matches) > 1:
            names = ", ".join(c.name for c in matches)

            return ToolResult.fail(
                f"I found {len(matches)} contacts named '{name}': "
                f"{names}. Which one do you mean?",
                matches=[c.name for c in matches],
                ambiguous=True,
            )

        contact = matches[0]

        if not contact.phone:
            return ToolResult.fail(
                f"{contact.name} has no phone number in the contact book."
            )

        phone = normalize_e164(contact.phone)

        if not phone:
            return ToolResult.fail(
                f"{contact.name} has an invalid phone number."
            )

        url = f"https://wa.me/{phone}"

        try:
            webbrowser.open(url)

            log.info(
                "WhatsApp contact flow opened for %s",
                contact.name,
            )

            return ToolResult.ok(
                f"Opening WhatsApp for {contact.name}. "
                "Press the call button to place the call. "
                "WhatsApp does not allow third-party applications "
                "to place calls automatically.",
                contact=contact.name,
                phone=contact.phone,
            )

        except Exception as exc:
            log.error(
                "WhatsApp deep link failed: %s",
                exc,
            )

            return ToolResult.fail(
                f"I couldn't open WhatsApp for "
                f"{contact.name}. ({exc})"
            )

    def _window(self):
        """Return a UIA window when pywinauto is installed; never use coordinates."""
        try:
            from pywinauto import Desktop
            windows = Desktop(backend="uia").windows(title_re=".*WhatsApp.*")
            return windows[0] if windows else None
        except Exception as exc:
            log.warning("WhatsApp UI Automation unavailable: %s", exc)
            return None

    def _find_named(self, window, names: tuple[str, ...]):
        for name in names:
            try:
                controls = window.descendants(title_re=f"(?i).*{re.escape(name)}.*")
                if controls:
                    return controls[0]
            except Exception:
                continue
        return None

    def _open_chat(self, window, name: str) -> ToolResult | object:
        search = self._find_named(window, ("Search", "search"))
        if search is None:
            return ToolResult.fail("I couldn't locate WhatsApp's chat search control.")
        search.click_input()
        search.type_keys(name, with_spaces=True)
        chat = self._find_named(window, (name,))
        if chat is None:
            return ToolResult.fail(f"I couldn't find the WhatsApp chat for {name}.")
        chat.click_input()
        return chat

    def _verify_message_sent(self, window, box, message: str) -> bool:
        """Require an observable UI change before reporting success."""
        try:
            if hasattr(box, "get_value"):
                return not bool(box.get_value())
        except Exception:
            pass
        try:
            return bool(window.descendants(title=message))
        except Exception:
            return False

    def message_contact(self, name: str, message: str) -> ToolResult:
        if not name or not message:
            return ToolResult.fail("A WhatsApp contact and message are required.")
        window = self._window()
        if window is None:
            launched = self.open_app()
            if not launched.success:
                return launched
            for _ in range(15):
                time.sleep(0.2)
                window = self._window()
                if window is not None:
                    break
        if window is None:
            return ToolResult.fail("I couldn't locate the WhatsApp window through Windows UI Automation.")
        try:
            opened = self._open_chat(window, name)
            if isinstance(opened, ToolResult):
                return opened
            box = self._find_named(window, ("Type a message", "Message", "Write a message"))
            if box is None:
                return ToolResult.fail("I couldn't locate WhatsApp's message input.")
            box.click_input()
            box.type_keys(message, with_spaces=True)
            box.type_keys("{ENTER}")
            if not self._verify_message_sent(window, box, message):
                return ToolResult.fail("WhatsApp did not provide evidence that the message was sent.")
            return ToolResult.ok("Message sent.", contact=name)
        except Exception as exc:
            return ToolResult.fail(f"WhatsApp message automation failed. ({exc})")

    def call_contact_auto(self, name: str) -> ToolResult:
        if not name:
            return ToolResult.fail("A WhatsApp contact is required.")
        window = self._window()
        if window is None:
            launched = self.open_app()
            if not launched.success:
                return launched
            for _ in range(15):
                time.sleep(0.2)
                window = self._window()
                if window is not None:
                    break
        if window is None:
            return ToolResult.fail("I couldn't locate the WhatsApp window through Windows UI Automation.")
        try:
            opened = self._open_chat(window, name)
            if isinstance(opened, ToolResult):
                return opened
            call = self._find_named(window, ("Voice call", "Audio call", "Call"))
            if call is None:
                return ToolResult.fail("I couldn't locate WhatsApp's voice-call control.")
            call.click_input()
            verified = None
            for _ in range(15):
                time.sleep(0.2)
                verified = self._find_named(window, ("End call", "Calling", "Ringing", "Connected"))
                if verified is not None:
                    break
            if verified is None:
                return ToolResult.fail("WhatsApp's call control was activated, but I couldn't verify that the call started.")
            return ToolResult.ok("Call started.", contact=name)
        except Exception as exc:
            return ToolResult.fail(f"WhatsApp call automation failed. ({exc})")


class WhatsAppOpenTool(Tool):
    name = "open_whatsapp"
    description = "Open the WhatsApp desktop application."
    schema = {
        "type": "object",
        "properties": {},
    }
    category = "safe"

    def __init__(
        self,
        provider: WhatsAppProvider | None = None,
    ) -> None:
        self.provider = provider or WhatsAppProvider()

    def execute(self, **kwargs) -> ToolResult:
        return self.provider.open_app()


class WhatsAppOpenChatTool(Tool):
    name = "whatsapp_open_chat"
    description = "Find and open a WhatsApp chat through Windows UI Automation."
    schema = {"type": "object", "properties": {"contact": {"type": "string"}}, "required": ["contact"]}
    category = "safe"

    def __init__(self, provider: WhatsAppProvider | None = None) -> None:
        self.provider = provider or WhatsAppProvider()

    def execute(self, **kwargs) -> ToolResult:
        name = str(kwargs.get("contact", "")).strip()
        window = self.provider._window()
        if window is None:
            return ToolResult.fail("I couldn't locate the WhatsApp window through Windows UI Automation.")
        try:
            opened = self.provider._open_chat(window, name)
            return opened if isinstance(opened, ToolResult) else ToolResult.ok(f"Opened the chat for {name}.", contact=name)
        except Exception as exc:
            return ToolResult.fail(f"I couldn't open the WhatsApp chat. ({exc})")


class WhatsAppCallTool(Tool):
    name = "whatsapp_call"
    description = (
        "Start a WhatsApp call/contact flow for a contact by name. "
        "Requires the contact in the local contact book "
        "(data/contacts.json). "
        "The user completes the call manually."
    )

    schema = {
        "type": "object",
        "properties": {
            "contact": {
                "type": "string",
                "description": "Contact name, e.g. 'Ahmed'",
            }
        },
        "required": ["contact"],
    }

    category = "confirmation"

    def __init__(
        self,
        provider: WhatsAppProvider | None = None,
    ) -> None:
        self.provider = provider or WhatsAppProvider()

    def execute(self, **kwargs) -> ToolResult:
        return self.provider.call_contact(
            str(kwargs.get("contact", ""))
        )


class WhatsAppMessageAutoTool(Tool):
    name = "whatsapp_message_auto"
    description = "Find a WhatsApp chat through UI Automation and send a message without confirmation."
    schema = {"type": "object", "properties": {"contact": {"type": "string"}, "message": {"type": "string"}}, "required": ["contact", "message"]}
    category = "safe"

    def __init__(self, provider: WhatsAppProvider | None = None) -> None:
        self.provider = provider or WhatsAppProvider()

    def execute(self, **kwargs) -> ToolResult:
        return self.provider.message_contact(str(kwargs.get("contact", "")), str(kwargs.get("message", "")))


class WhatsAppCallAutoTool(Tool):
    name = "whatsapp_call_auto"
    description = "Find a WhatsApp chat and activate its voice-call control through UI Automation."
    schema = {"type": "object", "properties": {"contact": {"type": "string"}}, "required": ["contact"]}
    category = "safe"

    def __init__(self, provider: WhatsAppProvider | None = None) -> None:
        self.provider = provider or WhatsAppProvider()

    def execute(self, **kwargs) -> ToolResult:
        return self.provider.call_contact_auto(str(kwargs.get("contact", "")))
