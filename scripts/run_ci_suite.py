#!/usr/bin/env python3
"""Run Patpat CI test suites in parallel with per-check timing telemetry."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from typing import Sequence

SUITES: dict[str, tuple[tuple[str, ...], ...]] = {
    # Longest-job-first within each suite keeps the critical-path tail balanced across workers.
    "contracts": (
        ("scripts/validate.py", "--self-test", "--skip-subtests", "--shard", "1/4"),
        ("scripts/validate.py", "--self-test", "--skip-subtests", "--shard", "2/4"),
        ("scripts/validate.py", "--self-test", "--skip-subtests", "--shard", "3/4"),
        ("scripts/validate.py", "--self-test", "--skip-subtests", "--shard", "4/4"),
        ("tests/test_general_task_ontology.py",),
        ("scripts/install_skills.py", "--self-test"),
        ("skills/patpat-run/scripts/run_state.py", "--self-test", "--self-test-part", "core"),
        ("skills/patpat-run/scripts/run_state.py", "--self-test", "--self-test-part", "delivery"),
        ("scripts/stage_agent_plugin.py", "--self-test"),
        ("scripts/stage_plugin.py", "--self-test"),
        ("skills/patpat-run/scripts/program_state.py", "--self-test"),
        ("skills/patpat-repository-diagram/scripts/render.py", "self-test"),
        ("tests/test_ontology_verifiers.py",),
        ("scripts/context_footprint.py", "--check-budget"),
        ("scripts/smoke_grok_plugin.py", "--commands-only"),
        ("scripts/verify_ready.py", "--self-test"),
        ("skills/patpat-learn/scripts/verify_corrections.py", "--root", "."),
        ("tests/test_workspace_mapper.py",),
        ("skills/patpat-verify/scripts/eval_proof_contract.py", "--self-test"),
        ("tests/test_assignment_generation_replay.py",),
        ("skills/patpat-repository-diagram/scripts/import_graph.py", "--self-test"),
        ("tests/test_assignment_model_pure_python.py",),
        ("scripts/eval_parallel.py", "--self-test"),
        ("scripts/eval_why.py", "--self-test"),
        ("skills/patpat-run/scripts/verify_assignment_fence.py", "--self-test"),
        ("scripts/publish_codex_attestation.py", "--self-test"),
        ("skills/patpat-review/scripts/verify_review.py", "--self-test"),
        ("scripts/update_skills.py", "--self-test"),
        ("scripts/eval_routing.py", "--self-test"),
        ("skills/patpat-run/scripts/check_assignment_model.py", "--self-test"),
        ("skills/patpat-learn/scripts/verify_corrections.py", "--self-test"),
        ("tests/test_adversarial_controls.py",),
        ("skills/patpat-ship/scripts/github_observe.py", "--self-test"),
        ("scripts/probe_codex_behavior.py", "--self-test"),
        ("scripts/worktree_audit.py", "--self-test"),
        ("hooks/scripts/patpat_loop_state.py", "--self-test"),
        ("tests/test_patpat_loop_state.py",),
        ("skills/patpat-unslop/scripts/unslop_ast_check.py", "--self-test"),
        ("skills/patpat-ship/scripts/watch_pr.py", "--self-test"),
        ("skills/patpat-ship/scripts/verify_cicd.py", "--self-test"),
        ("skills/patpat-ship/scripts/discover_pr_stack.py", "--self-test"),
        ("hooks/scripts/patpat_safety_guard.py", "--self-test"),
        ("scripts/eval_inspect.py", "--self-test"),
        ("tests/test_sanitize_logs.py",),
        ("skills/patpat-run/scripts/team_shape.py", "--self-test"),
        ("scripts/eval_representation.py", "--self-test"),
        ("scripts/dry_run_loop.py", "--self-test"),
        ("skills/patpat-ship/scripts/pr_watch.py", "--self-test"),
        ("skills/patpat-ship/scripts/watch_pr_stack.py", "--self-test"),
        ("scripts/eval_adversarial_controls.py", "--self-test"),
        ("scripts/check_attribution.py", "--self-test"),
        ("skills/patpat-run/scripts/validate_plan.py", "--self-test"),
        ("skills/patpat-run/scripts/decisions.py", "--self-test"),
        ("scripts/context_footprint.py", "--self-test"),
        ("skills/patpat-eval/scripts/eval_stats.py", "--self-test"),
        ("scripts/sanitize_logs.py", "--self-test"),
        ("scripts/run_ci_suite.py", "--self-test"),
    ),
    "windows-paths": (
        ("skills/patpat-run/scripts/run_state.py", "--self-test", "--self-test-part", "core"),
        ("skills/patpat-run/scripts/run_state.py", "--self-test", "--self-test-part", "delivery"),
        ("skills/patpat-run/scripts/program_state.py", "--self-test"),
        ("skills/patpat-repository-diagram/scripts/render.py", "self-test"),
        ("scripts/stage_agent_plugin.py", "--self-test"),
        ("tests/test_general_task_ontology.py",),
        ("scripts/install_skills.py", "--self-test"),
        ("scripts/stage_plugin.py", "--self-test"),
        ("tests/test_workspace_mapper.py",),
        ("tests/test_statechart_receipts.py",),
        ("skills/patpat-verify/scripts/eval_proof_contract.py", "--self-test"),
        ("skills/patpat-review/scripts/verify_review.py", "--self-test"),
        ("scripts/update_skills.py", "--self-test"),
        ("skills/patpat-repository-diagram/scripts/import_graph.py", "--self-test"),
        ("tests/test_patpat_loop_state.py",),
        ("hooks/scripts/patpat_loop_state.py", "--self-test"),
        ("scripts/worktree_audit.py", "--self-test"),
        ("skills/patpat-learn/scripts/verify_corrections.py", "--self-test"),
        ("scripts/verify_ready.py", "--self-test"),
        ("scripts/eval_adversarial_controls.py", "--self-test"),
        ("scripts/context_footprint.py", "--check-budget"),
        ("skills/patpat-unslop/scripts/unslop_ast_check.py", "--self-test"),
        ("hooks/scripts/patpat_safety_guard.py", "--self-test"),
        ("scripts/context_footprint.py", "--self-test"),
        ("scripts/eval_routing.py", "--self-test"),
        ("skills/patpat-eval/scripts/eval_stats.py", "--self-test"),
        ("scripts/sanitize_logs.py", "--self-test"),
        ("scripts/run_ci_suite.py", "--self-test"),
    ),
}

# Timing-sensitive checks run sequentially after parallel workers finish so CPU/disk
# contention cannot skew wall-clock latency assertions (e.g. SessionEnd < 1.0s).
SUITE_SERIAL_TAILS: dict[str, tuple[tuple[str, ...], ...]] = {
    "windows-paths": (
        ("tests/smoke_windows_codex_hooks.py",),
    ),
}


@dataclass(frozen=True)
class CheckResult:
    label: str
    command: tuple[str, ...]
    returncode: int
    seconds: float
    stdout: str
    stderr: str


def _run_one(root: Path, cmd: Sequence[str], python_exe: str) -> CheckResult:
    started = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run(
        [python_exe, *cmd],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return CheckResult(
        label=" ".join(cmd),
        command=tuple(cmd),
        returncode=proc.returncode,
        seconds=time.perf_counter() - started,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def run_suite(
    root: Path,
    commands: Sequence[Sequence[str]],
    *,
    serial_commands: Sequence[Sequence[str]] = (),
    workers: int | None = None,
    python_exe: str = sys.executable,
) -> tuple[list[CheckResult], float]:
    wall_start = time.perf_counter()
    max_default = 4 if os.name == "nt" else 8
    worker_count = workers or min(max_default, max(2, os.cpu_count() or 4))
    results: list[CheckResult] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        futures = [pool.submit(_run_one, root, cmd, python_exe) for cmd in commands]
        for future in as_completed(futures):
            results.append(future.result())
    for cmd in serial_commands:
        results.append(_run_one(root, cmd, python_exe))
    wall_seconds = time.perf_counter() - wall_start
    results.sort(key=lambda item: (-item.seconds, item.label))
    return results, wall_seconds


def render_report(suite_name: str, results: Sequence[CheckResult], wall_seconds: float) -> str:
    failed = [item for item in results if item.returncode != 0]
    lines = [
        f"CI suite '{suite_name}': {len(results) - len(failed)}/{len(results)} passed in {wall_seconds:.2f}s wall time"
    ]
    for item in results:
        status = "PASS" if item.returncode == 0 else f"FAIL({item.returncode})"
        lines.append(f"  [{status:8s}] {item.seconds:6.2f}s  {item.label}")
    for item in failed:
        lines.append(f"\n--- FAILED: {item.label} (exit {item.returncode}) ---")
        if item.stdout.strip():
            lines.append(item.stdout.rstrip())
        if item.stderr.strip():
            lines.append(item.stderr.rstrip())
    return "\n".join(lines)


def self_test() -> int:
    root = Path(__file__).resolve().parents[1]
    for suite_name, commands in SUITES.items():
        if not commands:
            raise AssertionError(f"empty CI suite: {suite_name}")
        seen: set[tuple[str, ...]] = set()
        shard_groups: dict[tuple[str, tuple[str, ...]], tuple[int, set[int]]] = {}
        run_state_parts: set[str] = set()
        for cmd in (*commands, *SUITE_SERIAL_TAILS.get(suite_name, ())):
            if cmd in seen:
                raise AssertionError(f"duplicate command in {suite_name}: {cmd}")
            seen.add(cmd)
            script_path = root / cmd[0]
            if not script_path.is_file():
                raise AssertionError(f"missing script in suite {suite_name}: {cmd[0]}")
            if "--shard" in cmd:
                idx = cmd.index("--shard")
                spec = cmd[idx + 1]
                part_str, total_str = spec.split("/", 1)
                part_num, total_num = int(part_str), int(total_str)
                base_key = (cmd[0], cmd[1:idx] + cmd[idx + 2 :])
                prev_total, seen_parts = shard_groups.get(base_key, (total_num, set()))
                if prev_total != total_num:
                    raise AssertionError(f"mismatched shard total in {suite_name}: {base_key}")
                seen_parts.add(part_num)
                shard_groups[base_key] = (total_num, seen_parts)
            if cmd[0].endswith("run_state.py") and "--self-test-part" in cmd:
                part_idx = cmd.index("--self-test-part")
                run_state_parts.add(cmd[part_idx + 1])
        for base_key, (total_num, seen_parts) in shard_groups.items():
            if seen_parts != set(range(1, total_num + 1)):
                raise AssertionError(f"incomplete shards in {suite_name} for {base_key}: {sorted(seen_parts)} of {total_num}")
        if run_state_parts and run_state_parts != {"core", "delivery"}:
            raise AssertionError(f"incomplete run_state self-test parts in {suite_name}: {sorted(run_state_parts)}")

    # Keep SUITES["contracts"] in parity with scripts/validate.py's skipped child subtests.
    validate_src = (root / "scripts" / "validate.py").read_text(encoding="utf-8")
    import ast

    validate_tree = ast.parse(validate_src)
    expected_subtests: set[tuple[str, ...]] = set()
    for node in ast.walk(validate_tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "subtests"
            and isinstance(node.value, ast.List)
        ):
            for elt in node.value.elts:
                if isinstance(elt, ast.Tuple) and len(elt.elts) == 2 and isinstance(elt.elts[1], ast.List):
                    cmd_parts: list[str] = []
                    for item in elt.elts[1].elts[1:]:
                        if isinstance(item, ast.Constant) and isinstance(item.value, str):
                            cmd_parts.append(item.value)
                        elif (
                            isinstance(item, ast.Call)
                            and isinstance(item.func, ast.Name)
                            and item.func.id == "str"
                            and item.args
                        ):
                            segments: list[str] = []
                            cur = item.args[0]
                            while isinstance(cur, ast.BinOp) and isinstance(cur.op, ast.Div):
                                if isinstance(cur.right, ast.Constant) and isinstance(cur.right.value, str):
                                    segments.append(cur.right.value)
                                cur = cur.left
                            cmd_parts.append("/".join(reversed(segments)))
                    if cmd_parts:
                        expected_subtests.add(tuple(cmd_parts))
    if len(expected_subtests) < 20:
        raise AssertionError(f"failed to parse validate.py subtests list: found {len(expected_subtests)}")
    contracts_set = set(SUITES["contracts"])
    for subcmd in expected_subtests:
        if subcmd[0] == "skills/patpat-run/scripts/run_state.py":
            continue
        if subcmd not in contracts_set:
            raise AssertionError(f"validate.py subtest missing from SUITES['contracts']: {subcmd}")

    with tempfile.TemporaryDirectory(prefix="patpat-ci-runner-") as directory:
        tmp = Path(directory)
        (tmp / "ok_a.py").write_text("print('a ok')\n", encoding="utf-8")
        (tmp / "ok_b.py").write_text("print('b ok')\n", encoding="utf-8")
        (tmp / "fail_c.py").write_text("import sys; sys.stderr.write('boom\\n'); sys.exit(3)\n", encoding="utf-8")

        results_ok, wall_ok = run_suite(
            tmp,
            (("ok_a.py",),),
            serial_commands=(("ok_b.py",),),
            workers=2,
        )
        if len(results_ok) != 2 or any(r.returncode != 0 for r in results_ok) or wall_ok < 0:
            raise AssertionError("parallel+serial passing suite failed")

        results_fail, wall_fail = run_suite(tmp, (("ok_a.py",), ("fail_c.py",)), workers=2)
        failed = [r for r in results_fail if r.returncode != 0]
        if len(failed) != 1 or failed[0].returncode != 3 or "boom" not in failed[0].stderr:
            raise AssertionError("failing suite did not preserve exit code or stderr")
        report = render_report("fixture", results_fail, wall_fail)
        if "FAIL(3)" not in report or "boom" not in report:
            raise AssertionError("render_report omitted failure diagnostics")
    print("run_ci_suite self-test: ok")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=sorted(SUITES), help="Predefined CI suite to execute")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.suite:
        parser.error("--suite is required unless --self-test is passed")
    if args.workers is not None and args.workers < 1:
        parser.error("--workers must be >= 1")

    results, wall_seconds = run_suite(
        args.root.resolve(),
        SUITES[args.suite],
        serial_commands=SUITE_SERIAL_TAILS.get(args.suite, ()),
        workers=args.workers,
    )
    failed = [item for item in results if item.returncode != 0]
    if args.json:
        payload = {
            "suite": args.suite,
            "wall_seconds": round(wall_seconds, 3),
            "passed": len(results) - len(failed),
            "failed": len(failed),
            "results": [
                {
                    "label": item.label,
                    "returncode": item.returncode,
                    "seconds": round(item.seconds, 3),
                }
                for item in results
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(render_report(args.suite, results, wall_seconds))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
