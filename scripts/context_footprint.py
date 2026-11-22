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
# Tiered depth-1 closure token ceilings (~tokens = closure bytes // 4):
# - orchestrators (patpat-loop, patpat-run): <= 20,000 ~tokens
# - domain-contract specialists (ship, diagram, statechart, formal-verify, game-builder): <= 16,000 ~tokens
# - leaf skills (all other skills): <= 10,000 ~tokens
ORCHESTRATOR_SKILLS = frozenset({"patpat-loop", "patpat-run"})
HEAVY_SPECIALIST_SKILLS = frozenset(
    {
        "patpat-formal-verify",
        "patpat-game-builder",
        "patpat-repository-diagram",
        "patpat-ship",
        "patpat-statechart",
    }
)
ORCHESTRATOR_MAX_TOKENS = 20000
HEAVY_SPECIALIST_MAX_TOKENS = 16000
LEAF_MAX_TOKENS = 10000
DEFAULT_MAX_TOKENS = ORCHESTRATOR_MAX_TOKENS


def skill_name_from_entry(entry: str) -> str:
    parts = Path(entry).parts
    if len(parts) >= 2 and parts[-1] == "SKILL.md":
        return parts[-2]
    return Path(entry).stem


def tier_max_tokens(entry: str) -> tuple[str, int]:
    name = skill_name_from_entry(entry)
    if name in ORCHESTRATOR_SKILLS:
        return ("orchestrator", ORCHESTRATOR_MAX_TOKENS)
    if name in HEAVY_SPECIALIST_SKILLS:
        return ("specialist", HEAVY_SPECIALIST_MAX_TOKENS)
    return ("leaf", LEAF_MAX_TOKENS)


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


def check_budget(
    rows: list[dict],
    *,
    max_bytes: int | None = None,
    max_tokens: int | None = None,
    use_tiers: bool = False,
) -> list[str]:
    """Return budget violation lines for rows exceeding byte, flat token, or tiered token limits."""
    violations: list[str] = []
    if max_bytes is not None:
        for r in rows:
            if r["bytes"] > max_bytes:
                violations.append(f"over budget: {r['entry']} {r['bytes']} > {max_bytes} bytes")
    if max_tokens is not None:
        for r in rows:
            if r["approx_tokens"] > max_tokens:
                violations.append(
                    f"over token budget: {r['entry']} {r['approx_tokens']} > {max_tokens} ~tokens"
                )
    elif use_tiers:
        for r in rows:
            tier, limit = tier_max_tokens(r["entry"])
            if r["approx_tokens"] > limit:
                violations.append(
                    f"over {tier} token budget: {r['entry']} {r['approx_tokens']} > {limit} ~tokens"
                )
    return violations


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
        check(
            check_budget(rows, max_tokens=rows[0]["approx_tokens"]) == [],
            "check_budget passes when approx_tokens == max_tokens",
        )
        over_tokens = check_budget(rows, max_tokens=max(0, rows[0]["approx_tokens"] - 1))
        check(
            len(over_tokens) == 1 and "over token budget:" in over_tokens[0],
            "check_budget flags rows exceeding max_tokens",
        )
        check(
            main(["--root", str(root), "--check-budget"]) == 0,
            "--check-budget passes on fixture under tiered token ceiling",
        )
        check(
            main(["--root", str(root), "--max-tokens", "1"]) == 1,
            "--max-tokens exits 1 when closure exceeds ceiling",
        )
        # Tiered budget checks: orchestrator <= 20k, specialist <= 16k, leaf <= 10k
        check(
            tier_max_tokens("skills/patpat-loop/SKILL.md") == ("orchestrator", ORCHESTRATOR_MAX_TOKENS),
            "patpat-loop maps to orchestrator tier",
        )
        check(
            tier_max_tokens("skills/patpat-ship/SKILL.md") == ("specialist", HEAVY_SPECIALIST_MAX_TOKENS),
            "patpat-ship maps to specialist tier",
        )
        check(
            tier_max_tokens("skills/demo/SKILL.md") == ("leaf", LEAF_MAX_TOKENS),
            "unlisted skill maps to leaf tier",
        )
        synthetic = [
            {"entry": "skills/patpat-loop/SKILL.md", "bytes": 0, "approx_tokens": ORCHESTRATOR_MAX_TOKENS},
            {"entry": "skills/patpat-ship/SKILL.md", "bytes": 0, "approx_tokens": HEAVY_SPECIALIST_MAX_TOKENS},
            {"entry": "skills/demo/SKILL.md", "bytes": 0, "approx_tokens": LEAF_MAX_TOKENS},
        ]
        check(check_budget(synthetic, use_tiers=True) == [], "exact tier ceilings pass")
        over_leaf = [{"entry": "skills/demo/SKILL.md", "bytes": 0, "approx_tokens": LEAF_MAX_TOKENS + 1}]
        leaf_violations = check_budget(over_leaf, use_tiers=True)
        check(
            len(leaf_violations) == 1 and "over leaf token budget:" in leaf_violations[0],
            "leaf skill exceeding LEAF_MAX_TOKENS is flagged even when under ORCHESTRATOR_MAX_TOKENS",
        )
        over_spec = [{"entry": "skills/patpat-ship/SKILL.md", "bytes": 0, "approx_tokens": HEAVY_SPECIALIST_MAX_TOKENS + 1}]
        spec_violations = check_budget(over_spec, use_tiers=True)
        check(
            len(spec_violations) == 1 and "over specialist token budget:" in spec_violations[0],
            "specialist skill exceeding HEAVY_SPECIALIST_MAX_TOKENS is flagged",
        )
        over_orch = [{"entry": "skills/patpat-loop/SKILL.md", "bytes": 0, "approx_tokens": ORCHESTRATOR_MAX_TOKENS + 1}]
        orch_violations = check_budget(over_orch, use_tiers=True)
        check(
            len(orch_violations) == 1 and "over orchestrator token budget:" in orch_violations[0],
            "orchestrator skill exceeding ORCHESTRATOR_MAX_TOKENS is flagged",
        )
    print("context_footprint self-test: ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--entry", type=Path, help="measure one Markdown entry instead of every skill")
    parser.add_argument("--depth", type=int, default=1, help="relative-link depth to follow (default 1)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-bytes", type=int, help="exit 1 when the measured closure exceeds this many bytes")
    parser.add_argument(
        "--max-tokens",
        type=int,
        help="exit 1 when the measured closure exceeds this many approximate tokens",
    )
    parser.add_argument(
        "--check-budget",
        action="store_true",
        help=(
            f"enforce tiered CI token-budget ceilings "
            f"(orchestrator <= {ORCHESTRATOR_MAX_TOKENS}, specialist <= {HEAVY_SPECIALIST_MAX_TOKENS}, "
            f"leaf <= {LEAF_MAX_TOKENS} ~tokens unless --max-tokens is set)"
        ),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if args.depth < 0:
        parser.error("--depth must be >= 0")
    if args.max_bytes is not None and args.max_bytes < 0:
        parser.error("--max-bytes must be >= 0")
    if args.max_tokens is not None and args.max_tokens < 0:
        parser.error("--max-tokens must be >= 0")

    root = args.root.resolve()
    if args.entry:
        rows = [footprint(args.entry.resolve(), args.depth)]
        rows[0]["entry"] = args.entry.as_posix()
        rows[0]["entry_bytes"] = args.entry.stat().st_size
    else:
        rows = report(root, args.depth)

    print(json.dumps(rows, indent=2) if args.json else render(rows))
    violations = check_budget(
        rows,
        max_bytes=args.max_bytes,
        max_tokens=args.max_tokens,
        use_tiers=args.check_budget and args.max_tokens is None,
    )
    for line in violations:
        print(line, file=sys.stderr)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
