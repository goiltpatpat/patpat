#!/usr/bin/env python3
"""Exercise Patpat's writable-parallelism boundaries in disposable Git worktrees."""

from __future__ import annotations

import importlib.util
import subprocess
import tempfile
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
DRY_RUN = ROOT / "scripts" / "dry_run_loop.py"
RUN_STATE = ROOT / "skills" / "patpat-run" / "scripts" / "run_state.py"
TEAM_SHAPE = ROOT / "skills" / "patpat-run" / "scripts" / "team_shape.py"


class ParallelEvalError(RuntimeError):
    """Raised when a representative parallelism invariant fails."""


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ParallelEvalError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ParallelEvalError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout.strip()


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def changed_paths(root: Path, base: str, head: str = "HEAD") -> set[str]:
    output = git(root, "diff", "--name-only", f"{base}..{head}")
    return {line for line in output.splitlines() if line}


def require_owned_change(root: Path, base: str, owned: set[str]) -> set[str]:
    changed = changed_paths(root, base)
    if not changed:
        raise ParallelEvalError("worker produced no committed change")
    unexpected = changed - owned
    if unexpected:
        raise ParallelEvalError(f"worker changed unowned paths: {sorted(unexpected)}")
    return changed


def commit(root: Path, message: str, *paths: str) -> str:
    git(root, "add", "--", *paths)
    git(root, "commit", "-m", message)
    return git(root, "rev-parse", "HEAD")


def initialize_repository(root: Path) -> str:
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Patpat Eval")
    git(root, "config", "user.email", "patpat-eval@example.invalid")
    write(root / "alpha.txt", "alpha base\n")
    write(root / "beta.txt", "beta base\n")
    write(root / "proof.txt", "proof base\n")
    commit(root, "base", "alpha.txt", "beta.txt", "proof.txt")
    return git(root, "rev-parse", "HEAD")


def run_self_test() -> None:
    routing = load_module("patpat_parallel_routing", DRY_RUN)
    state = load_module("patpat_parallel_state", RUN_STATE)
    team_shape = load_module("patpat_parallel_team_shape", TEAM_SHAPE)

    if routing.fan_out(
        kind="autopilot",
        worktree_or_sandbox=False,
        shared_worktree=True,
        read_only=False,
    ) != "serial-fallback":
        raise ParallelEvalError("shared writable worktree did not fall back to serial execution")
    if routing.fan_out(
        kind="autopilot",
        worktree_or_sandbox=True,
        shared_worktree=False,
        read_only=False,
    ) != "serial-fallback":
        raise ParallelEvalError("isolation without earned-parallelism evidence was admitted")

    receipt = {
        "schema_version": 1,
        "kind": team_shape.PARALLEL_GATE_KIND,
        "program_id": "parallel-eval",
        "plan_digest": "a" * 64,
        "integration_owner": "integration-owner",
        "checks": {name: True for name in team_shape.PARALLEL_GATE_CHECKS},
        "isolation_identities": {
            "alpha": "worktree-alpha",
            "beta": "worktree-beta",
        },
    }
    selection = team_shape.select_team_shape(
        work_kind="writable",
        decomposable=True,
        stable_verifier=True,
        worker_capacity=2,
        worker_budget=2,
        writable_gates_passed=True,
        uncertainty="low",
        consequence="medium",
        independent_oracle=False,
        parallel_gate_receipt=receipt,
        expected_program_id="parallel-eval",
        expected_plan_digest="a" * 64,
        expected_integration_owner="integration-owner",
        expected_units={"alpha", "beta"},
    )
    if selection["pattern"] != "distributed" or selection["worker_limit"] != 2:
        raise ParallelEvalError("valid earned-parallelism evidence was not admitted")

    with tempfile.TemporaryDirectory(prefix="patpat-parallel-eval-") as temporary:
        sandbox = Path(temporary)
        integration = sandbox / "integration"
        alpha_worker = sandbox / "worker-alpha"
        beta_worker = sandbox / "worker-beta"
        failing_worker = sandbox / "worker-failing"
        base = initialize_repository(integration)

        git(integration, "worktree", "add", "-b", "worker-alpha", str(alpha_worker), base)
        git(integration, "worktree", "add", "-b", "worker-beta", str(beta_worker), base)
        git(integration, "worktree", "add", "-b", "worker-failing", str(failing_worker), base)

        write(alpha_worker / "alpha.txt", "alpha worker result\n")
        alpha_head = commit(alpha_worker, "worker alpha", "alpha.txt")
        if require_owned_change(alpha_worker, base, {"alpha.txt"}) != {"alpha.txt"}:
            raise ParallelEvalError("alpha ownership evidence was incomplete")

        write(beta_worker / "beta.txt", "beta worker result\n")
        beta_head = commit(beta_worker, "worker beta", "beta.txt")
        if require_owned_change(beta_worker, base, {"beta.txt"}) != {"beta.txt"}:
            raise ParallelEvalError("beta ownership evidence was incomplete")

        write(failing_worker / "alpha.txt", "unauthorized worker result\n")
        commit(failing_worker, "worker violates ownership", "alpha.txt")
        try:
            require_owned_change(failing_worker, base, {"beta.txt"})
        except ParallelEvalError as error:
            if "unowned paths" not in str(error):
                raise
        else:
            raise ParallelEvalError("injected ownership violation was accepted")

        git(integration, "cherry-pick", alpha_head)
        git(integration, "cherry-pick", beta_head)
        if (integration / "alpha.txt").read_text(encoding="utf-8") != "alpha worker result\n":
            raise ParallelEvalError("parent integration lost alpha result")
        if (integration / "beta.txt").read_text(encoding="utf-8") != "beta worker result\n":
            raise ParallelEvalError("parent integration lost beta result")

        run_id = "parallel-integration"
        state.initialize(
            integration,
            run_id,
            "Prove the integrated worker result",
            "integration-owner",
            ["create-or-update-ready-pr"],
            ["merge", "deploy"],
            ["alpha.txt", "beta.txt"],
            [],
        )
        state.transition(integration, run_id, "INSPECT")
        state.transition(integration, run_id, "PROOF_CONTRACT")
        state.record_proof_contract(
            integration,
            run_id,
            {
                "claim": "Both isolated worker results survive parent integration.",
                "surface": "alpha.txt and beta.txt in the integration worktree",
                "action": "Read both files after cherry-picking the worker heads.",
                "expected": "Each file contains its assigned worker result.",
                "cleanup": "Disposable temporary repository is removed.",
            },
        )
        state.transition(integration, run_id, "ACT")
        state.transition(integration, run_id, "VERIFY")
        receipt_path = sandbox / "integration-proof.txt"
        write(receipt_path, f"base={base}\nalpha={alpha_head}\nbeta={beta_head}\nresult=pass\n")
        state.record_receipt(
            integration,
            run_id,
            "verification",
            "Integrated contents matched both worker assignments.",
            f"file:{receipt_path.resolve()}",
            "integration-owner",
            "verified",
        )
        if state.status(integration, run_id)["verification_stale"]:
            raise ParallelEvalError("fresh integration evidence was marked stale")

        write(integration / "proof.txt", "repository changed after verification\n")
        if not state.status(integration, run_id)["verification_stale"]:
            raise ParallelEvalError("repository drift did not invalidate integration evidence")

    print("Patpat writable-parallelism behavioral self-test passed.")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("--self-test is required")
    run_self_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
