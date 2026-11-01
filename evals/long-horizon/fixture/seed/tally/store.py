"""Ledger persistence: a JSON list of entries at one path."""

from __future__ import annotations

import json
import os

from tally.ledger import Entry


def load(path: str) -> list[Entry]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [Entry(**row) for row in json.load(handle)]


def save(path: str, entries: list[Entry]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump([e.to_dict() for e in entries], handle, indent=2)
