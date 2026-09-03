#!/usr/bin/env python3
"""Dry-run Patpat Loop routing, ship, fan-out, and issue-loop gates. No git writes."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks" / "scripts" / "patpat_loop_state.py"
EXPLICIT_MERGE = re.compile(
    r"(?:^|\s)(?:land|merge)(?:\s+(?:this|it|the\s+(?:pr|pull request|stack)|pr\s*#?\d+))?(?=$|[.!?])",
    re.IGNORECASE,
)
MERGE_DENIAL = re.compile(
    r"(?:do\s+not|don't|dont|never|not|no|without|avoid(?:ing)?)\b"
    r"[^.!?;\n]*\b(?:land|merge)\b",
    re.IGNORECASE,
)
DISABLE_MODE = re.compile(
    r"^\s*(?:disable\s+(?:/|\$)?patpat(?:-loop)?|opt\s+out(?:\s+of)?\s+patpat(?:-loop)?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)


def load_hook():
    spec = importlib.util.spec_from_file_location("patpat_loop_state", HOOK)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing hook script: {HOOK}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def route(prompt: str) -> str:
    text = prompt.lower()
    if DISABLE_MODE.fullmatch(prompt):
        return "disable"
    if "issue-loop" in text or "triage github issues" in text or "benny" in text:
        return "issue-loop"
    if "arena" in text or "competing" in text or "two layouts" in text:
        return "arena"
    if "swarm" in text or "each package" in text or "coverage matrix" in text:
        return "swarm"
    if "autopilot" in text or "this queue" in text:
        return "autopilot"
    if (
        "how does" in text
        or "why does" in text
        or "why was" in text
        or "why is" in text
        or "do not change" in text
        or "read-only" in text
        or "which skill owns" in text
        or "where should this live" in text
        or "where should" in text
    ):
        return "inspect"
    if "pause safely" in text or "go offline" in text:
        return "pause"
    if "babysit" in text or "get it green" in text or "watch ci" in text:
        return "pr-babysit"
    if "worktree" in text and ("clean" in text or "prune" in text):
        return "worktree-cleanup"
    if "timeout" in text or "bug" in text or "repro" in text or "fix" in text:
        return "debug"
    if explicit_merge_intent(prompt) or "open the pr" in text:
        return "ship"
    return "loop"


def ship_plan(
    *,
    path: str,
    verified: bool,
    reviewed: bool,
    patpat_activated: bool,
    explicit_delivery: bool,
    repo_allows_delivery: bool,
    opt_out: bool,
    explicit_merge: bool,
    continuation: bool,
    ci: str,
    existing_pr: bool = False,
    existing_pr_is_draft: bool = False,
    explicit_ready_pr: bool = False,
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
    if not repo_allows_delivery:
        return "stop-repository-policy"
    if not (patpat_activated or explicit_delivery or explicit_merge):
        return "local-only-no-authority"
    if explicit_merge:
        if ci == "green":
            if existing_pr and existing_pr_is_draft:
                return "mark-ready-then-merge"
            return "merge"
        if ci == "flake":
            if existing_pr and existing_pr_is_draft:
                return "retry-then-mark-ready-and-merge-if-flake"
            return "retry-then-merge-if-flake"
        return "no-land-real-fail"
    if existing_pr and existing_pr_is_draft and not (patpat_activated or explicit_ready_pr):
        return "update-draft"
    if continuation:
        return "drive-existing-pr-to-merge-ready" if existing_pr else "commit-pr-then-drive-to-merge-ready"
    if existing_pr:
        if existing_pr_is_draft:
            return "mark-ready-and-recheck"
        return "update-existing-pr"
    return "commit-and-pr"


def fan_out(*, kind: str, worktree_or_sandbox: bool, shared_worktree: bool, read_only: bool) -> str:
    if kind not in {"arena", "swarm", "autopilot"}:
        return "serial"
    if read_only and kind == "swarm":
        return "parallel-readonly"
    return "serial-fallback"


def issue_loop(
    *,
    provider: str,
    enabled: bool,
    sandbox: bool,
    canary: bool,
    requested_write: str = "",
    allowed_writes: tuple[str, ...] = (),
    fresh_authority: bool = False,
    existing_fix: bool = False,
    interactive_delivery_authority: bool = False,
) -> str:
    if not provider or not sandbox:
        return "fail-closed"
    if not canary or not enabled:
        return "paused"
    if existing_fix:
        return "verify-existing-fix"
    if not requested_write:
        return "triage-readonly"
    if requested_write == "ready-pr" and not interactive_delivery_authority:
        return "ready-pr-denied"
    if requested_write in allowed_writes and fresh_authority:
        return "coordinator-write-authorized"
    return "triage-readonly-write-denied"


def explicit_merge_intent(prompt: str) -> bool:
    if MERGE_DENIAL.search(prompt):
        return False
    return EXPLICIT_MERGE.search(prompt) is not None


def continuation_intent(prompt: str) -> bool:
    text = prompt.casefold()
    return any(phrase in text for phrase in ("overnight", "going to bed", "don't stop", "do not stop"))


def base_ship_args() -> dict[str, object]:
    return {
        "path": "mutating",
        "verified": True,
        "reviewed": True,
        "patpat_activated": True,
        "explicit_delivery": False,
        "repo_allows_delivery": True,
        "opt_out": False,
        "explicit_merge": False,
        "continuation": False,
        "ci": "unknown",
    }


def run_self_test() -> None:
    hook = load_hook()
    assert hook.classify_prompt("/patpat fix the timeout") == "activate"
    assert hook.classify_prompt("$patpat-loop land this") == "activate"
    assert hook.classify_prompt("Use patpat to inspect this repository") == "activate"
    assert hook.classify_prompt("use $patpat-setup on this host") == "inactive"
    assert hook.classify_prompt("Do not activate /patpat for this task.") == "inactive"
    assert hook.classify_prompt("Explain what /patpat does without enabling it.") == "inactive"
    assert hook.classify_prompt("`/patpat fix the bug`") == "inactive"
    assert hook.classify_prompt("Example: /patpat fix the bug") == "inactive"
    assert hook.classify_prompt("disable /patpat") == "disable"

    cases = {
        "How does auth reach this handler? Do not change files.": "inspect",
        "/patpat reproduce this timeout and fix the root cause": "debug",
        "which skill owns investigation vs rationale-forensics?": "inspect",
        "where should this live?": "inspect",
        "Why does dry_run_loop.ship_plan require explicit land/merge?": "inspect",
        "how does routing work?": "inspect",
        "/patpat arena two layouts for this page": "arena",
        "/patpat swarm each package against its check script": "swarm",
        "/patpat autopilot this queue; do not merge": "autopilot",
        "/patpat design an issue-loop for GitHub issues; keep it paused": "issue-loop",
        "/patpat pause safely, I am going offline": "pause",
        "/patpat babysit this PR and get it green": "pr-babysit",
        "/patpat prune abandoned worktrees": "worktree-cleanup",
        "/patpat merge this": "ship",
        "do not merge; keep the work local": "loop",
        "make this merge-ready without landing": "loop",
        "/patpat fix settings when users disable alerts": "debug",
        "/patpat do not disable the safety gate": "loop",
        "disable /patpat": "disable",
        "opt out of patpat": "disable",
    }
    for prompt, expected in cases.items():
        got = route(prompt)
        if got != expected:
            raise AssertionError(f"route({prompt!r})={got!r} expected {expected!r}")

    base_ship = base_ship_args()
    assert ship_plan(**base_ship) == "commit-and-pr"
    assert ship_plan(**{**base_ship, "opt_out": True}) == "local-only"
    assert ship_plan(**{**base_ship, "path": "read-only"}) == "no-ship"
    assert ship_plan(**{**base_ship, "verified": False}) == "stop-missing-proof"
    assert ship_plan(**{**base_ship, "reviewed": False}) == "stop-missing-proof"
    assert ship_plan(**{**base_ship, "patpat_activated": False}) == "local-only-no-authority"
    assert ship_plan(
        **{**base_ship, "patpat_activated": False, "explicit_delivery": True}
    ) == "commit-and-pr"
    assert ship_plan(**{**base_ship, "repo_allows_delivery": False}) == "stop-repository-policy"
    assert ship_plan(**{**base_ship, "existing_pr": True}) == "update-existing-pr"
    assert ship_plan(**{**base_ship, "existing_pr": True, "existing_pr_is_draft": True}) == "mark-ready-and-recheck"
    draft_ship = {
        **base_ship,
        "patpat_activated": False,
        "explicit_delivery": True,
        "existing_pr": True,
        "existing_pr_is_draft": True,
    }
    assert ship_plan(**draft_ship) == "update-draft"
    assert ship_plan(**{**draft_ship, "continuation": True}) == "update-draft"
    assert ship_plan(**{**draft_ship, "explicit_ready_pr": True}) == "mark-ready-and-recheck"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "green"}) == "merge"
    draft_merge = {**base_ship, "explicit_merge": True, "existing_pr": True, "existing_pr_is_draft": True}
    assert ship_plan(**{**draft_merge, "ci": "green"}) == "mark-ready-then-merge"
    assert ship_plan(**{**draft_merge, "ci": "flake"}) == "retry-then-mark-ready-and-merge-if-flake"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "red"}) == "no-land-real-fail"
    assert ship_plan(**{**base_ship, "explicit_merge": True, "ci": "flake"}) == "retry-then-merge-if-flake"
    assert ship_plan(**{**base_ship, "continuation": True, "ci": "green"}) == "commit-pr-then-drive-to-merge-ready"
    assert ship_plan(**{**base_ship, "continuation": True, "ci": "green", "existing_pr": True}) == "drive-existing-pr-to-merge-ready"
    assert ship_plan(**{**base_ship, "action": "deploy"}) == "pause"
    assert ship_plan(**{**base_ship, "action": "force-push"}) == "pause"

    assert explicit_merge_intent("/patpat merge this") is True
    assert explicit_merge_intent("land the PR") is True
    assert explicit_merge_intent("work overnight") is False
    assert explicit_merge_intent("don't stop until merge-ready") is False
    assert explicit_merge_intent("do not merge") is False
    assert explicit_merge_intent("don't ever merge") is False
    assert explicit_merge_intent("never automatically merge") is False
    assert explicit_merge_intent("do not under any circumstances merge") is False
    assert explicit_merge_intent("never, ever merge") is False
    assert explicit_merge_intent("continue without merge") is False
    assert explicit_merge_intent("ship it") is False
    assert continuation_intent("work overnight") is True
    assert continuation_intent("merge this") is False

    assert fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=False, read_only=False) == "serial-fallback"
    assert fan_out(kind="arena", worktree_or_sandbox=False, shared_worktree=True, read_only=False) == "serial-fallback"
    assert fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=True, read_only=False) == "serial-fallback"
    assert fan_out(kind="swarm", worktree_or_sandbox=False, shared_worktree=True, read_only=True) == "parallel-readonly"
    assert fan_out(kind="autopilot", worktree_or_sandbox=False, shared_worktree=True, read_only=False) == "serial-fallback"

    assert issue_loop(provider="", enabled=False, sandbox=False, canary=False) == "fail-closed"
    assert issue_loop(provider="github", enabled=False, sandbox=True, canary=True) == "paused"
    active_issue = {"provider": "github", "enabled": True, "sandbox": True, "canary": True}
    assert issue_loop(**active_issue) == "triage-readonly"
    assert issue_loop(**active_issue, existing_fix=True) == "verify-existing-fix"
    assert issue_loop(**active_issue, requested_write="comment") == "triage-readonly-write-denied"
    ready_write = {**active_issue, "requested_write": "ready-pr", "allowed_writes": ("ready-pr",), "fresh_authority": True}
    assert issue_loop(**ready_write) == "ready-pr-denied"
    assert issue_loop(**ready_write, interactive_delivery_authority=True) == "coordinator-write-authorized"
    assert issue_loop(**active_issue, requested_write="comment", allowed_writes=("comment",), fresh_authority=True) == "coordinator-write-authorized"

    print("Patpat loop dry-run self-test passed.")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        print()
        print("Dry-run scenarios")
        base_ship = base_ship_args()
        rows = [
            ("inspect", route("How does this work? Do not change files."), ship_plan(**{**base_ship, "path": "read-only"})),
            ("placement", route("which skill owns investigation vs rationale-forensics?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("why-ship_plan", route("Why does dry_run_loop.ship_plan require explicit land/merge?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("how-routing", route("how does routing work?"), ship_plan(**{**base_ship, "path": "read-only"})),
            ("fix", route("/patpat fix the timeout"), ship_plan(**base_ship)),
            ("fix local only", "debug", ship_plan(**{**base_ship, "opt_out": True})),
            ("overnight", "debug", ship_plan(**{**base_ship, "continuation": True, "ci": "green"})),
            ("land green", "debug", ship_plan(**{**base_ship, "explicit_merge": True, "ci": "green"})),
            ("land red", "debug", ship_plan(**{**base_ship, "explicit_merge": True, "ci": "red"})),
            ("deploy", "ship", ship_plan(**{**base_ship, "ci": "green", "action": "deploy"})),
            ("arena isolated", "arena", fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=False, read_only=False)),
            ("arena shared worktree", "arena", fan_out(kind="arena", worktree_or_sandbox=True, shared_worktree=True, read_only=False)),
            ("issue-loop unnamed", "issue-loop", issue_loop(provider="", enabled=False, sandbox=False, canary=False)),
            ("issue-loop competing fix", "issue-loop", issue_loop(provider="github", enabled=True, sandbox=True, canary=True, existing_fix=True)),
            ("issue-loop ready PR without interactive authority", "issue-loop", issue_loop(provider="github", enabled=True, sandbox=True, canary=True, requested_write="ready-pr", allowed_writes=("ready-pr",), fresh_authority=True)),
        ]
        for name, routed, decision in rows:
            print(f"- {name}: route={routed} decision={decision}")
        return 0
    print("Usage: python3 scripts/dry_run_loop.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
