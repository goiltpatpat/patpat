#!/usr/bin/env python3
"""Read-only git worktree audit for cleanup and status classification."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any


CommandRunner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


def default_runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with UTF-8 decoding across POSIX and Windows hosts."""
    return subprocess.run(
        args,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )


def parse_worktree_porcelain(output: str) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain` output into structured records."""
    worktrees: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            if current is not None:
                worktrees.append(current)
                current = None
            continue

        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            path_str = line[len("worktree ") :]
            current = {
                "path": str(Path(path_str)),
                "head": None,
                "branch_ref": None,
                "branch": None,
                "detached": False,
                "bare": False,
                "locked": False,
                "lock_reason": None,
                "prunable": False,
                "prunable_reason": None,
            }
            continue

        if current is None:
            continue

        if line.startswith("HEAD "):
            current["head"] = line[len("HEAD ") :].strip()
        elif line.startswith("branch "):
            ref = line[len("branch ") :].strip()
            current["branch_ref"] = ref
            prefix = "refs/heads/"
            current["branch"] = ref[len(prefix) :] if ref.startswith(prefix) else ref
        elif line == "detached":
            current["detached"] = True
        elif line == "bare":
            current["bare"] = True
        elif line == "locked" or line.startswith("locked "):
            current["locked"] = True
            reason = line[len("locked") :].strip()
            current["lock_reason"] = reason or None
        elif line == "prunable" or line.startswith("prunable "):
            current["prunable"] = True
            reason = line[len("prunable") :].strip()
            current["prunable_reason"] = reason or None

    if current is not None:
        worktrees.append(current)

    return worktrees


def parse_status_porcelain(output: str) -> dict[str, Any]:
    """Classify `git status --porcelain` output into dirty and untracked counts."""
    dirty_count = 0
    untracked_count = 0

    for line in output.splitlines():
        if not line.strip():
            continue
        if line.startswith("??"):
            untracked_count += 1
        else:
            dirty_count += 1

    return {
        "clean": dirty_count == 0 and untracked_count == 0,
        "dirty": dirty_count > 0,
        "untracked": untracked_count > 0,
        "dirty_count": dirty_count,
        "untracked_count": untracked_count,
    }


def check_merge_state(
    root: Path,
    head_sha: str | None,
    base_sha: str | None,
    runner: CommandRunner = default_runner,
) -> str:
    """Return 'merged', 'unmerged', or 'unknown' for head_sha relative to base_sha."""
    if not head_sha or not base_sha or set(head_sha) == {"0"}:
        return "unknown"

    completed = runner(["git", "merge-base", "--is-ancestor", head_sha, base_sha], root)
    if completed.returncode == 0:
        return "merged"
    if completed.returncode == 1:
        return "unmerged"
    return "unknown"


def lookup_pr_state(
    root: Path,
    branch: str | None,
    runner: CommandRunner = default_runner,
) -> dict[str, Any] | None:
    """Best-effort PR lookup via `gh`; returns None if unavailable or no PR matches."""
    if not branch:
        return None
    try:
        completed = runner(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number,state,url,isDraft",
                "--limit",
                "1",
            ],
            root,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    try:
        items = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None

    if not isinstance(items, list) or not items:
        return None

    item = items[0]
    if not isinstance(item, dict):
        return None

    return {
        "number": item.get("number"),
        "state": item.get("state"),
        "url": item.get("url"),
        "is_draft": bool(item.get("isDraft", False)),
    }


def audit_worktrees(
    root: Path,
    base_ref: str = "HEAD",
    use_gh: bool = True,
    runner: CommandRunner = default_runner,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, Any]:
    """Audit all git worktrees for a repository without modifying anything."""
    resolved_root = root.resolve()
    wt_proc = runner(["git", "worktree", "list", "--porcelain"], resolved_root)
    if wt_proc.returncode != 0:
        detail = wt_proc.stderr.strip() or "git worktree list failed"
        raise RuntimeError(detail)

    base_proc = runner(["git", "rev-parse", "--verify", "--quiet", base_ref], resolved_root)
    base_sha = base_proc.stdout.strip() if base_proc.returncode == 0 else None

    gh_available = use_gh and (which("gh") is not None)
    records: list[dict[str, Any]] = []

    for wt in parse_worktree_porcelain(wt_proc.stdout):
        wt_path = Path(wt["path"])
        exists = wt_path.exists()
        status_info: dict[str, Any] = {
            "clean": None,
            "dirty": None,
            "untracked": None,
            "dirty_count": 0,
            "untracked_count": 0,
        }

        if exists and not wt["bare"] and not wt["prunable"]:
            status_proc = runner(["git", "status", "--porcelain"], wt_path)
            if status_proc.returncode == 0:
                status_info = parse_status_porcelain(status_proc.stdout)

        merge_state = check_merge_state(resolved_root, wt["head"], base_sha, runner=runner)
        pr_info = (
            lookup_pr_state(resolved_root, wt["branch"], runner=runner)
            if gh_available and wt["branch"] and not wt["detached"] and not wt["bare"]
            else None
        )

        record = {
            **wt,
            "exists": exists,
            **status_info,
            "merge_state": merge_state,
            "pr": pr_info,
        }
        records.append(record)

    return {
        "root": str(resolved_root),
        "base_ref": base_ref,
        "base_sha": base_sha,
        "gh_available": gh_available,
        "worktrees": records,
    }


def format_report(report: dict[str, Any]) -> str:
    """Format an audit report as concise human-readable text."""
    lines = [
        f"Worktree audit (read-only) for {report['root']} (base: {report['base_ref']})",
    ]
    for wt in report["worktrees"]:
        ref_label = "detached" if wt["detached"] else (wt["branch"] or ("bare" if wt["bare"] else "unknown"))
        if not wt["exists"]:
            work_state = "missing"
        elif wt["bare"]:
            work_state = "bare"
        elif wt["clean"] is True:
            work_state = "clean"
        elif wt["clean"] is False:
            parts = []
            if wt["dirty_count"]:
                parts.append(f"{wt['dirty_count']} dirty")
            if wt["untracked_count"]:
                parts.append(f"{wt['untracked_count']} untracked")
            work_state = ", ".join(parts)
        else:
            work_state = "status-unknown"

        flags = []
        if wt["locked"]:
            flags.append("locked")
        if wt["prunable"]:
            flags.append("prunable")
        if wt["pr"] is not None:
            pr = wt["pr"]
            flags.append(f"PR #{pr['number']} {pr['state']}")
        flag_suffix = f" [{', '.join(flags)}]" if flags else ""
        lines.append(f"- {wt['path']} | {ref_label} | {work_state} | {wt['merge_state']}{flag_suffix}")
    return "\n".join(lines)


def self_test() -> int:
    """Run deterministic unit and local git-worktree integration tests."""
    sample_porcelain = (
        "worktree /tmp/repo\n"
        "HEAD 1111111111111111111111111111111111111111\n"
        "branch refs/heads/main\n"
        "\n"
        "worktree /tmp/repo-detached\n"
        "HEAD 2222222222222222222222222222222222222222\n"
        "detached\n"
        "locked reason here\n"
        "\n"
        "worktree /tmp/repo-gone\n"
        "HEAD 3333333333333333333333333333333333333333\n"
        "branch refs/heads/old\n"
        "prunable gitdir file points to non-existent location\n"
    )
    parsed = parse_worktree_porcelain(sample_porcelain)
    assert len(parsed) == 3
    assert parsed[0]["branch"] == "main" and not parsed[0]["detached"]
    assert parsed[1]["detached"] and parsed[1]["locked"] and parsed[1]["lock_reason"] == "reason here"
    assert parsed[2]["prunable"] and parsed[2]["prunable_reason"] is not None

    dirty_status = parse_status_porcelain(" M tracked.py\n?? scratch.txt\nA  staged.py\n")
    assert dirty_status == {
        "clean": False,
        "dirty": True,
        "untracked": True,
        "dirty_count": 2,
        "untracked_count": 1,
    }
    clean_status = parse_status_porcelain("")
    assert clean_status["clean"] is True

    def mock_gh_runner(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        if args[0] == "gh":
            payload = [{"number": 42, "state": "OPEN", "url": "https://example.invalid/pr/42", "isDraft": False}]
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(payload), stderr="")
        return default_runner(args, cwd)

    with tempfile.TemporaryDirectory() as temp:
        base_dir = Path(temp)
        main_repo = base_dir / "main"
        main_repo.mkdir()

        def git(cwd: Path, *args: str) -> None:
            completed = default_runner(["git", *args], cwd)
            if completed.returncode != 0:
                raise AssertionError(f"git {' '.join(args)} failed: {completed.stderr}")

        git(main_repo, "init", "-q", "-b", "main")
        git(main_repo, "config", "user.email", "self-test@example.invalid")
        git(main_repo, "config", "user.name", "self-test")
        (main_repo / "README.md").write_text("hello\n", encoding="utf-8")
        git(main_repo, "add", "README.md")
        git(main_repo, "commit", "-q", "-m", "init")

        wt_merged = base_dir / "wt-merged"
        git(main_repo, "worktree", "add", "-q", "-b", "feat/merged", str(wt_merged), "main")

        wt_unmerged = base_dir / "wt-unmerged"
        git(main_repo, "worktree", "add", "-q", "-b", "feat/unmerged", str(wt_unmerged), "main")
        (wt_unmerged / "README.md").write_text("changed\n", encoding="utf-8")
        git(wt_unmerged, "commit", "-q", "-am", "unmerged commit")
        (wt_unmerged / "README.md").write_text("dirty\n", encoding="utf-8")
        (wt_unmerged / "untracked.txt").write_text("scratch\n", encoding="utf-8")

        wt_detached = base_dir / "wt-detached"
        git(main_repo, "worktree", "add", "-q", "--detach", str(wt_detached), "main")

        report = audit_worktrees(
            main_repo,
            base_ref="main",
            use_gh=True,
            runner=mock_gh_runner,
            which=lambda cmd: "/usr/bin/gh" if cmd == "gh" else None,
        )
        by_branch = {w["branch"] or ("detached" if w["detached"] else "other"): w for w in report["worktrees"]}

        assert report["gh_available"] is True
        assert by_branch["main"]["clean"] is True
        assert by_branch["main"]["merge_state"] == "merged"
        assert by_branch["feat/merged"]["clean"] is True
        assert by_branch["feat/merged"]["merge_state"] == "merged"
        assert by_branch["feat/merged"]["pr"]["number"] == 42
        assert by_branch["feat/unmerged"]["clean"] is False
        assert by_branch["feat/unmerged"]["dirty"] is True
        assert by_branch["feat/unmerged"]["untracked"] is True
        assert by_branch["feat/unmerged"]["merge_state"] == "unmerged"
        assert by_branch["detached"]["detached"] is True
        assert by_branch["detached"]["pr"] is None

        no_gh_report = audit_worktrees(
            main_repo,
            base_ref="main",
            use_gh=True,
            runner=default_runner,
            which=lambda _cmd: None,
        )
        assert no_gh_report["gh_available"] is False
        assert all(w["pr"] is None for w in no_gh_report["worktrees"])
        assert "Worktree audit (read-only)" in format_report(no_gh_report)

        # Clean up worktrees before TemporaryDirectory exits (required on Windows).
        for wt_path in (wt_merged, wt_unmerged, wt_detached):
            git(main_repo, "worktree", "remove", "--force", str(wt_path))

    print("worktree_audit self-test ok: 7 cases")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="git repository root (default: cwd)")
    parser.add_argument("--base", default="HEAD", help="base ref for merge-state classification (default: HEAD)")
    parser.add_argument("--json", action="store_true", help="emit JSON output")
    parser.add_argument("--no-gh", action="store_true", help="skip optional GitHub PR lookup")
    parser.add_argument("--self-test", action="store_true", help="run deterministic self-tests")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    try:
        report = audit_worktrees(args.root, base_ref=args.base, use_gh=not args.no_gh)
    except RuntimeError as exc:
        print(f"worktree_audit error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
