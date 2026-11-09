#!/usr/bin/env python3
"""Measure how much Markdown a skill entry pulls into an agent's context.

The footprint of an entry is its own bytes plus the bytes of every local
Markdown file reachable through relative links, up to a link depth. Token
counts are an approximation (bytes / 4) and are labelled as such.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

LINK = re.compile(r"\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")
BYTES_PER_TOKEN = 4


def linked_markdown(path: Path) -> list[Path]:
    text = path.read_text(encoding="utf-8", errors="replace")
    found = []
    for target in LINK.findall(text):
        if "://" in target:
            continue
        resolved = (path.parent / target).resolve()
        if resolved.is_file():
            found.append(resolved)
    return found


def closure(entry: Path, depth: int) -> list[Path]:
    seen = {entry.resolve()}
    frontier = [entry.resolve()]
    for _ in range(depth):
        nxt = []
        for current in frontier:
            for child in linked_markdown(current):
                if child not in seen:
                    seen.add(child)
                    nxt.append(child)
        frontier = nxt
    return sorted(seen)


def footprint(entry: Path, depth: int) -> dict:
    files = closure(entry, depth)
    total = sum(f.stat().st_size for f in files)
    return {
        "entry": entry.as_posix(),
        "depth": depth,
        "files": len(files),
        "bytes": total,
        "approx_tokens": total // BYTES_PER_TOKEN,
    }


def skill_entries(root: Path) -> list[Path]:
    return sorted((root / "skills").glob("*/SKILL.md"))


def report(root: Path, depth: int) -> list[dict]:
    rows = []
    for entry in skill_entries(root):
        row = footprint(entry, depth)
        row["entry"] = entry.relative_to(root).as_posix()
        row["entry_bytes"] = entry.stat().st_size
        rows.append(row)
    return sorted(rows, key=lambda r: r["bytes"], reverse=True)


def render(rows: list[dict]) -> str:
    lines = [
        f"{'skill entry':<48} {'entry B':>8} {'closure B':>10} {'files':>5} {'~tokens':>8}"
    ]
    for r in rows:
        lines.append(
            f"{r['entry']:<48} {r['entry_bytes']:>8} {r['bytes']:>10} {r['files']:>5} {r['approx_tokens']:>8}"
        )
    return "\n".join(lines)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"context_footprint self-test failed: {message}")


def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        skill = root / "skills" / "demo"
        (skill / "refs").mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "See [a](refs/a.md#part), [web](https://x.test/b.md), [gone](missing.md).\n",
            encoding="utf-8",
        )
        (skill / "refs" / "a.md").write_text("Back to [entry](../SKILL.md) and [b](b.md).\n", encoding="utf-8")
        (skill / "refs" / "b.md").write_text("x" * 40, encoding="utf-8")
        entry = skill / "SKILL.md"

        check(footprint(entry, 0)["files"] == 1, "depth 0 counts only the entry")
        check(footprint(entry, 1)["files"] == 2, "depth 1 follows local links, skips URLs and missing files")
        deep = footprint(entry, 5)
        check(deep["files"] == 3, "cycles are visited once")
        expected = sum(p.stat().st_size for p in (entry, skill / "refs" / "a.md", skill / "refs" / "b.md"))
        check(deep["bytes"] == expected, "closure bytes sum every reached file")
        check(deep["approx_tokens"] == expected // BYTES_PER_TOKEN, "tokens are bytes / 4")
        rows = report(root, 1)
        check([r["entry"] for r in rows] == ["skills/demo/SKILL.md"], "entries are repo-relative POSIX paths")
    print("context_footprint self-test: ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--entry", type=Path, help="measure one Markdown entry instead of every skill")
    parser.add_argument("--depth", type=int, default=1, help="relative-link depth to follow (default 1)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-bytes", type=int, help="exit 1 when the measured closure exceeds this many bytes")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.depth < 0:
        parser.error("--depth must be >= 0")

    root = args.root.resolve()
    if args.entry:
        rows = [footprint(args.entry.resolve(), args.depth)]
        rows[0]["entry"] = args.entry.as_posix()
        rows[0]["entry_bytes"] = args.entry.stat().st_size
    else:
        rows = report(root, args.depth)

    print(json.dumps(rows, indent=2) if args.json else render(rows))
    if args.max_bytes is not None:
        over = [r for r in rows if r["bytes"] > args.max_bytes]
        for r in over:
            print(f"over budget: {r['entry']} {r['bytes']} > {args.max_bytes}", file=sys.stderr)
        return 1 if over else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
