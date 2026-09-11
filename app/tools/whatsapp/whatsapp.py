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