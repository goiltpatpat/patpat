"""Entries and the arithmetic over them."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

CENT = Decimal("0.01")


class LedgerError(Exception):
    """A problem to report to the user."""


@dataclass
class Entry:
    date: str
    amount: str
    category: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def parse_amount(text: str) -> str:
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise LedgerError("invalid amount") from None
    if not value.is_finite() or value <= 0 or value != value.quantize(CENT):
        raise LedgerError("invalid amount")
    return str(value.quantize(CENT))


def parse_date(text: str) -> str:
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise LedgerError("invalid date") from None


def select(entries: list[Entry], category: str | None = None) -> list[Entry]:
    chosen = [e for e in entries if category is None or e.category == category]
    return sorted(chosen, key=lambda e: e.date)


def total(entries: list[Entry]) -> Decimal:
    return sum((Decimal(e.amount) for e in entries), Decimal("0.00"))


def format_entry(entry: Entry) -> str:
    return f"{entry.date}  {entry.category:<12}{entry.amount:>10}  {entry.note}".rstrip()
