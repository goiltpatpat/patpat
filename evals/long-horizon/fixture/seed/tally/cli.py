"""Command-line interface."""

from __future__ import annotations

import argparse
import sys

from tally import ledger, store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tally")
    parser.add_argument("--file", default="tally.json")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add")
    add.add_argument("--date", required=True)
    add.add_argument("--amount", required=True)
    add.add_argument("--category", required=True)
    add.add_argument("--note", default="")

    listing = commands.add_parser("list")
    listing.add_argument("--category")

    summing = commands.add_parser("total")
    summing.add_argument("--category")
    return parser


def run(args: argparse.Namespace) -> None:
    entries = store.load(args.file)
    if args.command == "add":
        entries.append(
            ledger.Entry(
                date=ledger.parse_date(args.date),
                amount=ledger.parse_amount(args.amount),
                category=args.category,
                note=args.note,
            )
        )
        store.save(args.file, entries)
        print("added")
    elif args.command == "list":
        for entry in ledger.select(entries, args.category):
            print(ledger.format_entry(entry))
    elif args.command == "total":
        print(ledger.total(ledger.select(entries, args.category)))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run(args)
    except ledger.LedgerError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0
