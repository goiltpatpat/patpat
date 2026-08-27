#!/usr/bin/env python3
"""Dry-run Patpat Loop routing, ship, fan-out, and issue-loop gates. No git writes."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "scripts" / "patpat_loop_state.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("patpat_loop_state", HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing hook script: {HOOK}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route(prompt: str) -> str:
    text = prompt.lower()
    if "disable" in text or "opt out" in text:
        return "disable"
    if "issue-loop" in text or "triage github issues" in text or "benny" in text:
        return "issue-loop"
    if "arena" in text or "competing" in text or "two layouts" in text:
        return "arena"
    if "swarm" in text or "each package" in text or "coverage matrix" in text:
        return "swarm"
    if "autopilot" in text or "this queue" in text:
        return "autopilot"
    if "how does" in text or "do not change" in text or "read-only" in text:
        return "inspect"
    if "timeout" in text or "bug" in text or "repro" in text or "fix" in text:
        return "debug"
    if "land" in text or "open the pr" in text or "merge" in text:
        return "ship"
    return "loop"


def ship_plan(
    *,
    path: str,
    verified: bool,
    reviewed: bool,
    opt_out: bool,
    land: bool,
    ci: str,
    action: str = "edit",
) -> str:
    if path == "read-only" or action == "inspect":
        return "no-ship"
    if not verified or not reviewed:
        return "stop-missing-proof"
    if opt_out:
        return "local-only"
    if action in {"deploy", "publish", "force-push"}:
        return "pause"
    if land:
        if ci == "green":
            return "merge"
        if ci == "flake":
            return "retry-then-merge-if-flake"
        return "no-land-real-fail"
    return "commit-and-pr"


def fan_out(*, kind: str, isolated: bool, read_only: bool) -> str:
    if kind not in {"arena", "swarm", "autopilot"}:
        return "serial"
    if read_only and kind == "swarm":
        return "parallel-readonly"
    if isolated:
        return "parallel"
    return "serial-fallback"


def issue_loop(*, provider: str, enabled: bool, sandbox: bool, canary: bool) -> str:
    if not provider or not sandbox:
        return "fail-closed"
    if not canary or not enabled:
        return "paused"
    return "triage-readonly-until-confirmed"


def run_self_test() -> None:
    hook = load_hook()
    assert hook.classify_prompt("/patpat fix the timeout") == "activate"
    assert hook.classify_prompt("$patpat-loop land this") == "activate"
    assert hook.classify_prompt("use $patpat-setup on this host") == "inactive"
    assert hook.classify_prompt("disable /patpat") == "disable"

    cases = {
        "How does auth reach this handler? Do not change files.": "inspect",
        "/patpat reproduce this timeout and fix the root cause": "debug",
        "/patpat arena two layouts for this page": "arena",
        "/patpat swarm each package against its check script": "swarm",
        "/patpat autopilot this queue; do not merge": "autopilot",
        "/patpat design an issue-loop for GitHub issues; keep it paused": "issue-loop",
        "disable /patpat": "disable",
    }
    for prompt, expected in cases.items():
        got = route(prompt)
        if got != expected:
            raise AssertionError(f"route({prompt!r})={got!r} expected {expected!r}")

    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=False, ci="unknown") == "commit-and-pr"
    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=True, land=False, ci="unknown") == "local-only"
    assert ship_plan(path="read-only", verified=True, reviewed=True, opt_out=False, land=False, ci="unknown") == "no-ship"
    assert ship_plan(path="mutating", verified=False, reviewed=True, opt_out=False, land=False, ci="unknown") == "stop-missing-proof"
    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=True, ci="green") == "merge"
    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=True, ci="red") == "no-land-real-fail"
    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=True, ci="flake") == "retry-then-merge-if-flake"
    assert ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=False, ci="green", action="deploy") == "pause"

    assert fan_out(kind="arena", isolated=True, read_only=False) == "parallel"
    assert fan_out(kind="arena", isolated=False, read_only=False) == "serial-fallback"
    assert fan_out(kind="swarm", isolated=False, read_only=True) == "parallel-readonly"
    assert fan_out(kind="autopilot", isolated=False, read_only=False) == "serial-fallback"

    assert issue_loop(provider="", enabled=False, sandbox=False, canary=False) == "fail-closed"
    assert issue_loop(provider="github", enabled=False, sandbox=True, canary=True) == "paused"
    assert issue_loop(provider="github", enabled=True, sandbox=True, canary=True) == "triage-readonly-until-confirmed"

    print("Patpat loop dry-run self-test passed.")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        print()
        print("Dry-run scenarios")
        rows = [
            ("inspect", route("How does this work? Do not change files."), ship_plan(path="read-only", verified=True, reviewed=True, opt_out=False, land=False, ci="unknown")),
            ("fix", route("/patpat fix the timeout"), ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=False, ci="unknown")),
            ("fix local only", "debug", ship_plan(path="mutating", verified=True, reviewed=True, opt_out=True, land=False, ci="unknown")),
            ("land green", "debug", ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=True, ci="green")),
            ("land red", "debug", ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=True, ci="red")),
            ("deploy", "ship", ship_plan(path="mutating", verified=True, reviewed=True, opt_out=False, land=False, ci="green", action="deploy")),
            ("arena isolated", "arena", fan_out(kind="arena", isolated=True, read_only=False)),
            ("arena no isolation", "arena", fan_out(kind="arena", isolated=False, read_only=False)),
            ("issue-loop unnamed", "issue-loop", issue_loop(provider="", enabled=False, sandbox=False, canary=False)),
        ]
        for name, routed, decision in rows:
            print(f"- {name}: route={routed} decision={decision}")
        return 0
    print("Usage: python3 scripts/dry_run_loop.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
