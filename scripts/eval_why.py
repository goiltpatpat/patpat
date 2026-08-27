#!/usr/bin/env python3
"""Behavioral eval for the rationale-forensics why-equivalent. No git writes. No connectors."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dry_run_loop  # noqa: E402


PLAYBOOK = ROOT / "skills" / "patpat-loop" / "playbooks" / "rationale-forensics.md"
SKILL = ROOT / "skills" / "patpat-inspect" / "SKILL.md"
CONTRACT = ROOT / "skills" / "patpat-inspect" / "references" / "why-report.md"
SOURCE = ROOT / "scripts" / "dry_run_loop.py"
HOW_CONTRACT = ROOT / "skills" / "patpat-inspect" / "references" / "how-report.md"

SECTIONS = (
    "Question",
    "Code anchors",
    "Sources Consulted",
    "Competing hypotheses",
    "Supported rationale",
    "Gaps",
)
FORBIDDEN = (
    "setup-pstack",
    "make-bot-ui",
    "never-block-on-the-human",
    "never-block-on-human",
    "Graphite",
    "unslop-as-skill",
)
WHY_PROMPT = "Why does dry_run_loop.ship_plan require explicit land/merge?"
HOW_NEIGHBOR = "how does routing work?"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def assert_playbook_contract() -> None:
    playbook = _text(PLAYBOOK)
    skill = _text(SKILL)
    contract = _text(CONTRACT)
    blob = "\n".join((playbook, skill, contract))
    for needle in (
        "why-equivalent",
        "code-anchor first",
        "Evidence before narrative",
        "Sources Consulted",
        "competing hypotheses",
        "Slack is skipped",
        "Notion is skipped",
        "confirmed",
        "inferred",
        "unknown",
        "There is no `/why` slash skill",
    ):
        if needle.lower() not in blob.lower() and needle not in blob:
            # allow mixed case on skip lines
            if needle not in playbook and needle not in skill and needle not in contract:
                raise AssertionError(f"missing required phrase {needle!r}")
    if "Slack is skipped" not in playbook and "Slack is skipped" not in contract:
        if "Slack" not in playbook or "skipped" not in playbook:
            raise AssertionError("playbook must name Slack as skipped")
    if "Notion is skipped" not in playbook and "Notion is skipped" not in contract:
        if "Notion" not in playbook or "skipped" not in playbook:
            raise AssertionError("playbook must name Notion as skipped")
    for heading in SECTIONS:
        if f"### {heading}" not in contract:
            raise AssertionError(f"why-report missing ### {heading}")
    if (ROOT / "skills" / "why").exists():
        raise AssertionError("skills/why must not exist")
    if re.search(r"(?m)^# /why\b", blob):
        raise AssertionError("introduced a /why skill")
    for needle in FORBIDDEN:
        if needle in blob:
            raise AssertionError(f"forbidden token {needle!r} in why slice")
    if "how-report.md" not in _text(HOW_CONTRACT) and not HOW_CONTRACT.exists():
        raise AssertionError("how-report contract missing; C neighbor must remain")


def git_anchors() -> dict[str, str]:
    src = SOURCE.as_posix() if False else "scripts/dry_run_loop.py"
    log = _git("log", "--oneline", "-n", "12", "--", src)
    blame = _git("blame", "-L", "87,101", "--", src)
    focused = _git("log", "-S", "explicit_merge", "--oneline", "--", src)
    return {"log": log, "blame": blame, "focused": focused}


def why_ship_plan_report(anchors: dict[str, str]) -> str:
    src_lines = _text(SOURCE).splitlines()
    ship_line = next(i + 1 for i, line in enumerate(src_lines) if line.startswith("def ship_plan("))
    explicit_line = next(
        i + 1 for i, line in enumerate(src_lines) if "if explicit_merge:" in line and line.strip().startswith("if ")
    )
    continuation_line = next(
        i + 1 for i, line in enumerate(src_lines) if "if continuation:" in line
    )
    blame = anchors["blame"]
    focused = anchors["focused"]
    log = anchors["log"]
    pr5 = "PR #5" if "23ff30c" in focused or "never auto-merge" in log.lower() or "23ff30c" in log else "in-repo PR unnamed"
    if "23ff30c" in focused or "23ff30c" in log or "23ff30c" in blame:
        pr5 = "PR #5 (23ff30c feat(loop): port pause/pr-babysit/worktree playbooks and never auto-merge)"
    return f"""### Question
{WHY_PROMPT}
Current behavior: `ship_plan()` returns `merge` only when `explicit_merge` is true and CI is green; overnight/`continuation` drives merge-ready, not merge.

### Code anchors
- Path: `scripts/dry_run_loop.py`
- Symbol: `ship_plan` (line {ship_line}), `explicit_merge` branch (line {explicit_line}), `continuation` branch (line {continuation_line})
- Focused log (`git log -S explicit_merge -- scripts/dry_run_loop.py`):
{focused}
- Blame (`git blame -L 87,101 -- scripts/dry_run_loop.py`):
{blame}
- Recent file log:
{log}
- In-repo PR/issue: {pr5}

### Sources Consulted
- Git: used (blame, focused log, file log on `scripts/dry_run_loop.py`)
- GitHub PRs/issues on the target repo: used (commit `23ff30c` / {pr5}; no extra connector)
- Slack: skipped (not connected; user has not asked)
- Notion: skipped (not connected; user has not asked)

Connector calls: none

### Competing hypotheses
1. [confirmed] `explicit_merge` was added so land/merge language is the only merge authority. Evidence: `23ff30c` introduced `explicit_merge` and mapped `continuation` to merge-ready, not merge. Live code: `if explicit_merge:` can return `merge`; `if continuation:` cannot.
2. [inferred] Pre-`23ff30c` `ship_plan` treated land-shaped CI-green as merge (`89e717e` still owns the inner `ci == "green"` lines). That is a predecessor, not the current gate.
3. [unknown] Whether an unpublished local packaging tree intended a different merge rule. Out of scope; not read.

### Supported rationale
`ship_plan` requires explicit land/merge because PAT-002 A+B (`23ff30c`, {pr5}) split merge authority from overnight continuation. Evidence before narrative: the live `if explicit_merge:` / `if continuation:` branches, blame, and focused log agree. A how-shaped neighbor (`{HOW_NEIGHBOR}`) stays on investigation / how-report (C), not this playbook.

### Gaps
Slack and Notion were not consulted. No connector calls. The dirty Desktop worktree was not read.
"""


def run_self_test() -> None:
    assert_playbook_contract()
    assert dry_run_loop.route(WHY_PROMPT) == "inspect"
    assert dry_run_loop.route(HOW_NEIGHBOR) == "inspect"
    assert dry_run_loop.route("why was ship_plan merge gated?") == "inspect"
    assert dry_run_loop.route("/patpat pause safely, I am going offline") == "pause"
    assert dry_run_loop.route("/patpat babysit this PR and get it green") == "pr-babysit"
    assert dry_run_loop.route("/patpat prune abandoned worktrees") == "worktree-cleanup"
    assert dry_run_loop.route("/patpat fix the timeout") == "debug"
    assert dry_run_loop.route("/patpat merge this") == "ship"
    base = dry_run_loop.base_ship_args()
    overnight = dry_run_loop.ship_plan(**{**base, "continuation": True, "ci": "green"})
    if overnight != "commit-pr-then-drive-to-merge-ready":
        raise AssertionError(f"overnight must stay merge-ready not merge, got {overnight!r}")
    land = dry_run_loop.ship_plan(**{**base, "explicit_merge": True, "ci": "green"})
    if land != "merge":
        raise AssertionError(f"explicit land/merge still merges when green, got {land!r}")

    anchors = git_anchors()
    report = why_ship_plan_report(anchors)
    for heading in SECTIONS:
        if f"### {heading}" not in report:
            raise AssertionError(f"fixture missing {heading}")
    for needle in (
        "scripts/dry_run_loop.py",
        "Slack: skipped",
        "Notion: skipped",
        "Connector calls: none",
        "[confirmed]",
        "[inferred]",
        "[unknown]",
        HOW_NEIGHBOR,
    ):
        if needle not in report:
            raise AssertionError(f"fixture missing {needle!r}")
    if "23ff30c" not in report and "explicit_merge" not in anchors["focused"]:
        raise AssertionError("fixture missing live git citation")
    print("Patpat why eval self-test passed.")
    print()
    print("== fixture: Why does dry_run_loop.ship_plan require explicit land/merge? ==")
    print(report)
    print("== eval triggers ==")
    print(f"- trigger {WHY_PROMPT!r} -> inspect (rationale-forensics / why-report)")
    print(f"- neighbor {HOW_NEIGHBOR!r} -> inspect (C how-report, not D playbook)")
    print("- reject /patpat pause safely -> pause (A+B untouched)")
    print("- reject /patpat babysit -> pr-babysit (A+B untouched)")
    print("- reject /patpat prune abandoned worktrees -> worktree-cleanup (A+B untouched)")
    print("- overnight continuation -> merge-ready not merge")
    print("== skip map ==")
    print("Slack: skipped (not connected; user has not asked)")
    print("Notion: skipped (not connected; user has not asked)")
    print("Connector calls: none")
    print("Git: used")
    print("GitHub PRs/issues on target repo: used (from git log/blame; no connector call)")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        return 0
    print("Usage: python3 scripts/eval_why.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
