"""Local contact book used for WhatsApp contact resolution.

Contacts live in data/contacts.json as:
  {"Ahmed Raza": {"phone": "+923001234567", "aliases": ["ahmed"]}, ...}
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from app.config.settings import settings
from app.utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Contact:
    name: str
    phone: str
    aliases: list[str] = field(default_factory=list)

    def matches(self, query: str) -> bool:
        q = query.lower().strip()
        candidates = [self.name.lower()] + [a.lower() for a in self.aliases]
        return any(q == c or q in c for c in candidates)


class ContactBook:
    def __init__(self, path: str | None = None) -> None:
        self.path = path or str(settings.data_dir / "contacts.json")
        self._contacts: list[Contact] | None = None

    @property
    def contacts(self) -> list[Contact]:
        if self._contacts is None:
            self._load()
        return self._contacts

    def _load(self) -> None:
        self._contacts = []
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
            for name, info in raw.items():
                self._contacts.append(
                    Contact(
                        name=name,
                        phone=info.get("phone", ""),
                        aliases=info.get("aliases", []),
                    )
                )
            log.info("Loaded %d contacts", len(self._contacts))
        except FileNotFoundError:
            log.warning("No contacts file at %s — add data/contacts.json to enable calling", self.path)
        except Exception as exc:
            log.error("Failed to read contacts: %s", exc)

    def find(self, query: str) -> list[Contact]:
        return [c for c in self.contacts if c.matches(query)]
