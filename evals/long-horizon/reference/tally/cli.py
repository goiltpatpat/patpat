"""One file that behaves as the fixture does after each step. The scorer rewrites STEP."""

from __future__ import annotations

import argparse
import calendar
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

STEP = 5
CENT = Decimal("0.01")
SQLITE_MAGIC = b"SQLite format 3\x00"


class Problem(Exception):
    pass


def normalize(doc):
    state = {"entries": doc} if isinstance(doc, list) else doc
    state.setdefault("recurs", [])
    for index, entry in enumerate(state["entries"], start=1):
        entry.setdefault("currency", "USD")
        entry.setdefault("id", index)
    ids = [entry["id"] for entry in state["entries"]]
    state.setdefault("next_id", max(ids, default=0) + 1)
    return state


def read_sqlite(path):
    db = sqlite3.connect(path)
    try:
        return json.loads(db.execute("select doc from state").fetchone()[0])
    finally:
        db.close()


def write_sqlite(path, state):
    db = sqlite3.connect(path)
    try:
        with db:
            db.execute("create table if not exists state (doc text)")
            db.execute("delete from state")
            db.execute("insert into state values (?)", (json.dumps(state),))
    finally:
        db.close()


def load(path):
    if not os.path.exists(path):
        return normalize([])
    with open(path, "rb") as handle:
        raw = handle.read()
    if STEP < 5:
        return normalize(json.loads(raw.decode("utf-8")))
    if raw.startswith(SQLITE_MAGIC):
        return normalize(read_sqlite(path))
    try:
        doc = json.loads(raw.decode("utf-8"))
        if not isinstance(doc, (list, dict)):
            raise ValueError
    except ValueError:
        raise Problem("unrecognized store") from None
    state = normalize(doc)
    shutil.copyfile(path, path + ".bak")
    os.remove(path)
    write_sqlite(path, state)
    return state


def save(path, state):
    if STEP >= 5:
        write_sqlite(path, state)
        return
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)


def parse_amount(text):
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise Problem("invalid amount") from None
    if not value.is_finite() or value <= 0 or value != value.quantize(CENT):
        raise Problem("invalid amount")
    return str(value.quantize(CENT))


def parse_date(text):
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise Problem("invalid date") from None


def parse_month(text):
    if text is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text):
        raise Problem("invalid month")
    return text


def parse_currency(text):
    if not re.fullmatch(r"[A-Z]{3}", text):
        raise Problem("invalid currency")
    return text


def active(state, include_void=False):
    return [e for e in state["entries"] if include_void or not e.get("void")]


def select(entries, category=None, month=None):
    chosen = [
        e
        for e in entries
        if (category is None or e["category"] == category)
        and (month is None or e["date"].startswith(month + "-"))
    ]
    return sorted(chosen, key=lambda e: e["date"])


def in_usd(entry, rates):
    amount = Decimal(entry["amount"])
    if entry["currency"] == "USD":
        return amount
    if entry["currency"] not in rates:
        raise Problem(f"no rate for {entry['currency']}")
    return (amount * Decimal(rates[entry["currency"]])).quantize(CENT, rounding=ROUND_HALF_UP)


def line(entry, args):
    code = "" if entry["currency"] == "USD" else f" {entry['currency']}"
    text = f"{entry['date']}  {entry['category']:<12}{entry['amount']:>10}{code}  {entry['note']}".rstrip()
    if STEP >= 3:
        if getattr(args, "ids", False):
            text = f"#{entry['id']}  {text}"
        if entry.get("void"):
            text += " [void]"
    return text


def sum_usd(entries, rates):
    return sum((in_usd(e, rates) for e in entries), Decimal("0.00"))


def new_entry(state, entry_date, amount, category, note, currency):
    entry = {
        "id": state["next_id"],
        "date": entry_date,
        "amount": amount,
        "category": category,
        "note": note,
        "currency": currency,
    }
    state["next_id"] += 1
    state["entries"].append(entry)


def occurrence(start, index):
    month_index = start.year * 12 + start.month - 1 + index
    year, month = month_index // 12, month_index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def materialize(state, through):
    created = 0
    for rule in state["recurs"]:
        start = date.fromisoformat(rule["start"])
        while occurrence(start, rule["done"]) <= through:
            when = occurrence(start, rule["done"])
            new_entry(state, when.isoformat(), rule["amount"], rule["category"], rule["note"], rule["currency"])
            rule["done"] += 1
            created += 1
    return created


def build_parser():
    parser = argparse.ArgumentParser(prog="tally")
    parser.add_argument("--file", default="tally.json")
    if STEP >= 2:
        parser.add_argument("--rates")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add")
    add.add_argument("--date", required=True)
    add.add_argument("--amount", required=True)
    add.add_argument("--category", required=True)
    add.add_argument("--note", default="")
    if STEP >= 2:
        add.add_argument("--currency", default="USD")

    listing = commands.add_parser("list")
    summing = commands.add_parser("total")
    for command in (listing, summing):
        command.add_argument("--category")
        if STEP >= 1:
            command.add_argument("--month")
    if STEP >= 1:
        commands.add_parser("report").add_argument("--month", required=True)
    if STEP >= 3:
        listing.add_argument("--ids", action="store_true")
        listing.add_argument("--all", action="store_true")
        commands.add_parser("void").add_argument("id", type=int)
    if STEP >= 4:
        recur = commands.add_parser("recur").add_subparsers(dest="recur_command", required=True)
        rule = recur.add_parser("add")
        rule.add_argument("--start", required=True)
        rule.add_argument("--amount", required=True)
        rule.add_argument("--category", required=True)
        rule.add_argument("--note", default="")
        rule.add_argument("--currency", default="USD")
        commands.add_parser("materialize").add_argument("--through", required=True)
    return parser


def run(args):
    state = load(args.file)
    rates = {}
    if getattr(args, "rates", None):
        with open(args.rates, encoding="utf-8") as handle:
            rates = json.load(handle)
    month = parse_month(getattr(args, "month", None))
    if args.command == "add":
        new_entry(
            state,
            parse_date(args.date),
            parse_amount(args.amount),
            args.category,
            args.note,
            parse_currency(getattr(args, "currency", "USD")),
        )
        save(args.file, state)
        print("added")
    elif args.command == "list":
        pool = active(state, include_void=getattr(args, "all", False))
        for entry in select(pool, args.category, month):
            print(line(entry, args))
    elif args.command == "total":
        print(sum_usd(select(active(state), args.category, month), rates))
    elif args.command == "report":
        entries = select(active(state), None, month)
        for category in sorted({e["category"] for e in entries}):
            amount = sum_usd([e for e in entries if e["category"] == category], rates)
            print(f"{category:<12}{amount!s:>10}")
        print(f"{'TOTAL':<12}{sum_usd(entries, rates)!s:>10}")
    elif args.command == "void":
        found = next((e for e in state["entries"] if e["id"] == args.id), None)
        if found is None:
            raise Problem(f"no entry {args.id}")
        if found.get("void"):
            raise Problem(f"entry {args.id} already voided")
        found["void"] = True
        save(args.file, state)
        print(f"voided {args.id}")
    elif args.command == "recur":
        state["recurs"].append(
            {
                "start": parse_date(args.start),
                "amount": parse_amount(args.amount),
                "category": args.category,
                "note": args.note,
                "currency": parse_currency(args.currency),
                "done": 0,
            }
        )
        save(args.file, state)
        print(f"recur {len(state['recurs'])}")
    elif args.command == "materialize":
        created = materialize(state, date.fromisoformat(parse_date(args.through)))
        save(args.file, state)
        print(f"materialized {created}")


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except Problem as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    return 0
