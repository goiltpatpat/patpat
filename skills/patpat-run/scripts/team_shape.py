#!/usr/bin/env python3
"""Select a bounded Patpat team topology from explicit task evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


LEVELS = ("low", "medium", "high")
WORK_KINDS = ("read-only", "writable")
MAX_RECEIPT_BYTES = 64 * 1024
MAX_IDENTITY_LENGTH = 512
PLAN_DIGEST = re.compile(r"^[0-9a-f]{64}$")
PROGRAM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PARALLEL_GATE_KIND = "patpat.parallel_gate_receipt"
PARALLEL_GATE_CHECKS = (
    "representative_single_owner_run",
    "stable_verifier",
    "independent_slices",
    "isolated_workspaces",
    "isolated_resources",
    "whole_system_verification",
)
PARALLEL_GATE_KEYS = {
    "schema_version",
    "kind",
    "program_id",
    "plan_digest",
    "integration_owner",
    "checks",
    "isolation_identities",
}
HANDOFF_FIELDS = (
    "candidate_id",
    "objective",
    "owned_scope",
    "forbidden_scope",
    "proof_contract",
    "parallel_gate_receipt",
    "evidence_receipts",
    "objections",
    "reusable_parts",
    "verdict",
    "next_frontier",
)


class TeamShapeError(ValueError):
    """Raised when a team-shape input is invalid."""


def canonical_identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTITY_LENGTH
    ):
        raise TeamShapeError(f"{label} must be a bounded non-empty identity")
    if unicodedata.normalize("NFKC", value) != value:
        raise TeamShapeError(f"{label} must use canonical Unicode form")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise TeamShapeError(f"{label} must not contain control characters")
    return value.casefold()


def canonical_receipt_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_parallel_gate_receipt(
    value: Any,
    *,
    expected_program_id: str | None = None,
    expected_plan_digest: str | None = None,
    expected_integration_owner: str | None = None,
    expected_units: set[str] | None = None,
) -> dict[str, Any]:
    """Validate a content-bound earned-parallelism receipt."""
    if not isinstance(value, dict) or set(value) != PARALLEL_GATE_KEYS:
        raise TeamShapeError("parallel gate receipt fields do not match the contract")
    if value.get("schema_version") != 1 or value.get("kind") != PARALLEL_GATE_KIND:
        raise TeamShapeError("parallel gate receipt schema or kind is invalid")
    program_id = value.get("program_id")
    if (
        not isinstance(program_id, str)
        or len(program_id) > 64
        or PROGRAM_ID.fullmatch(program_id) is None
    ):
        raise TeamShapeError("parallel gate receipt program_id is invalid")
    plan_digest = value.get("plan_digest")
    if not isinstance(plan_digest, str) or PLAN_DIGEST.fullmatch(plan_digest) is None:
        raise TeamShapeError("parallel gate receipt plan_digest is invalid")
    owner_key = canonical_identity(value.get("integration_owner"), "integration owner")
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != set(PARALLEL_GATE_CHECKS)
        or any(checks[name] is not True for name in PARALLEL_GATE_CHECKS)
    ):
        raise TeamShapeError("parallel gate receipt requires every earned-parallelism check to pass")
    identities = value.get("isolation_identities")
    if not isinstance(identities, dict) or not identities:
        raise TeamShapeError("parallel gate receipt requires isolation identities")
    normalized: dict[str, str] = {}
    for unit_id, identity in identities.items():
        if (
            not isinstance(unit_id, str)
            or len(unit_id) > 64
            or PROGRAM_ID.fullmatch(unit_id) is None
        ):
            raise TeamShapeError("parallel gate receipt contains an invalid unit id")
        identity_key = canonical_identity(identity, f"isolation identity for {unit_id}")
        if identity_key == owner_key:
            raise TeamShapeError("worker isolation identity must differ from the integration owner")
        normalized[unit_id] = identity_key
    if len(normalized) != len(set(normalized.values())):
        raise TeamShapeError("parallel gate receipt isolation identities must be unique")
    if expected_program_id is not None and program_id != expected_program_id:
        raise TeamShapeError("parallel gate receipt program_id does not match the program")
    if expected_plan_digest is not None and plan_digest != expected_plan_digest:
        raise TeamShapeError("parallel gate receipt plan_digest does not match the program")
    if expected_integration_owner is not None and owner_key != canonical_identity(
        expected_integration_owner, "expected integration owner"
    ):
        raise TeamShapeError("parallel gate receipt integration owner does not match")
    if expected_units is not None and set(normalized) != expected_units:
        raise TeamShapeError("parallel gate receipt must bind every program unit exactly once")
    return {
        "program_id": program_id,
        "plan_digest": plan_digest,
        "integration_owner": value["integration_owner"],
        "isolation_count": len(normalized),
        "sha256": canonical_receipt_digest(value),
    }


def load_parallel_gate_receipt(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        canonical = path.resolve(strict=True)
    except OSError as error:
        raise TeamShapeError(f"could not resolve parallel gate receipt: {error}") from error
    if not path.is_absolute() or path != canonical:
        raise TeamShapeError("parallel gate receipt must be an absolute regular file without symlinks")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise TeamShapeError(
                "parallel gate receipt must be a unique regular file without symlinks"
            )
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_RECEIPT_BYTES:
            raise TeamShapeError("parallel gate receipt exceeds the byte limit")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise TeamShapeError(f"could not read parallel gate receipt: {error}") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    return value, validate_parallel_gate_receipt(value)


def positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TeamShapeError(f"{label} must be a positive integer")
    return value


def select_team_shape(
    *,
    work_kind: str,
    decomposable: bool,
    stable_verifier: bool,
    worker_capacity: int,
    worker_budget: int,
    writable_gates_passed: bool,
    uncertainty: str,
    consequence: str,
    independent_oracle: bool,
    parallel_gate_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a deterministic topology without granting execution authority."""
    if work_kind not in WORK_KINDS:
        raise TeamShapeError(f"work_kind must be one of {list(WORK_KINDS)}")
    if uncertainty not in LEVELS:
        raise TeamShapeError(f"uncertainty must be one of {list(LEVELS)}")
    if consequence not in LEVELS:
        raise TeamShapeError(f"consequence must be one of {list(LEVELS)}")
    for value, label in (
        (decomposable, "decomposable"),
        (stable_verifier, "stable_verifier"),
        (independent_oracle, "independent_oracle"),
        (writable_gates_passed, "writable_gates_passed"),
    ):
        if not isinstance(value, bool):
            raise TeamShapeError(f"{label} must be a boolean")

    capacity = positive_integer(worker_capacity, "worker_capacity")
    budget = positive_integer(worker_budget, "worker_budget")
    bounded_limit = min(capacity, budget)
    risk_requires_adversarial = uncertainty == "high" or consequence == "high"
    receipt_summary = None
    if parallel_gate_receipt is not None:
        receipt_summary = validate_parallel_gate_receipt(parallel_gate_receipt)

    reasons = [
        f"work is {work_kind}",
        f"worker limit is bounded by observed capacity {capacity} and explicit budget {budget}",
    ]
    pattern = "iterative"
    worker_limit = 1

    if work_kind == "writable" and (not writable_gates_passed or receipt_summary is None):
        reasons.append("serial fallback: writable earned-parallelism gates lack a valid content-bound receipt")
    elif work_kind == "writable" and receipt_summary["isolation_count"] < bounded_limit:
        reasons.append("serial fallback: receipt does not bind every budgeted worker to a unique isolation identity")
    elif not stable_verifier:
        reasons.append("serial fallback: no stable verifier")
    elif bounded_limit < 2:
        reasons.append("serial fallback: fewer than two isolated, budgeted lanes")
    elif risk_requires_adversarial and not independent_oracle:
        reasons.append("serial fallback: high uncertainty or consequence lacks an independent oracle")
    elif risk_requires_adversarial:
        pattern = "adversarial"
        worker_limit = bounded_limit
        reasons.append("adversarial search is warranted by high uncertainty or consequence")
        reasons.append("an independent oracle can falsify candidate results")
    elif decomposable:
        pattern = "distributed"
        worker_limit = bounded_limit
        reasons.append("independent slices can return to a stable verifier")
    else:
        reasons.append("serial fallback: work is not decomposable and does not require adversarial search")

    return {
        "schema_version": 1,
        "pattern": pattern,
        "worker_limit": worker_limit,
        "serial_fallback": pattern == "iterative",
        "reasons": reasons,
        "handoff_fields": list(HANDOFF_FIELDS),
        "handoff_policy": "typed-card-no-transcript",
        "parallel_gate_receipt_sha256": (
            receipt_summary["sha256"] if receipt_summary is not None else None
        ),
        "authority_granted": False,
    }


def parse_boolean(value: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def self_test() -> None:
    receipt = {
        "schema_version": 1,
        "kind": PARALLEL_GATE_KIND,
        "program_id": "release-train",
        "plan_digest": "a" * 64,
        "integration_owner": "integration-owner",
        "checks": {name: True for name in PARALLEL_GATE_CHECKS},
        "isolation_identities": {
            "contract": "worktree-contract",
            "consumer": "worktree-consumer",
            "docs": "worktree-docs",
        },
    }
    common = {
        "work_kind": "writable",
        "decomposable": True,
        "stable_verifier": True,
        "worker_capacity": 5,
        "worker_budget": 3,
        "writable_gates_passed": True,
        "uncertainty": "low",
        "consequence": "medium",
        "independent_oracle": False,
        "parallel_gate_receipt": receipt,
    }

    distributed = select_team_shape(**common)
    assert distributed["pattern"] == "distributed"
    assert distributed["worker_limit"] == 3
    assert distributed["serial_fallback"] is False

    adversarial = select_team_shape(
        **{**common, "uncertainty": "high", "independent_oracle": True, "worker_budget": 2}
    )
    assert adversarial["pattern"] == "adversarial"
    assert adversarial["worker_limit"] == 2

    no_verifier = select_team_shape(**{**common, "stable_verifier": False})
    assert no_verifier["pattern"] == "iterative" and no_verifier["worker_limit"] == 1

    no_oracle = select_team_shape(**{**common, "consequence": "high"})
    assert no_oracle["pattern"] == "iterative"
    assert any("independent oracle" in reason for reason in no_oracle["reasons"])

    no_capacity = select_team_shape(**{**common, "worker_capacity": 1})
    assert no_capacity["pattern"] == "iterative"

    unearned = select_team_shape(**{**common, "writable_gates_passed": False})
    assert unearned["pattern"] == "iterative" and unearned["authority_granted"] is False

    boolean_only = select_team_shape(**{**common, "parallel_gate_receipt": None})
    assert boolean_only["pattern"] == "iterative"

    reused_identity = json.loads(json.dumps(receipt))
    reused_identity["isolation_identities"]["consumer"] = "worktree-contract"
    try:
        validate_parallel_gate_receipt(reused_identity)
    except TeamShapeError:
        pass
    else:
        raise AssertionError("duplicate isolation identity was accepted")

    indivisible = select_team_shape(**{**common, "decomposable": False})
    assert indivisible["pattern"] == "iterative"

    read_only = select_team_shape(
        **{**common, "work_kind": "read-only", "worker_capacity": 2, "writable_gates_passed": False}
    )
    assert read_only["pattern"] == "distributed" and read_only["worker_limit"] == 2

    try:
        select_team_shape(**{**common, "worker_budget": 0})
    except TeamShapeError:
        pass
    else:
        raise AssertionError("zero worker budget was accepted")

    assert tuple(distributed["handoff_fields"]) == HANDOFF_FIELDS

    with tempfile.TemporaryDirectory(prefix="patpat-team-shape-") as raw:
        directory = Path(raw).resolve()
        receipt_path = directory / "parallel-gate.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        _, loaded = load_parallel_gate_receipt(receipt_path)
        assert loaded["sha256"] == canonical_receipt_digest(receipt)

        linked_path = directory / "linked-receipt.json"
        os.link(receipt_path, linked_path)
        try:
            load_parallel_gate_receipt(receipt_path)
        except TeamShapeError as error:
            assert "unique regular file" in str(error)
        else:
            raise AssertionError("hard-linked parallel gate receipt was accepted")
    print("Patpat team-shape self-test passed.")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--self-test", action="store_true")
    command.add_argument("--work-kind", choices=WORK_KINDS)
    command.add_argument("--decomposable", type=parse_boolean)
    command.add_argument("--stable-verifier", type=parse_boolean)
    command.add_argument("--worker-capacity", type=int)
    command.add_argument("--worker-budget", type=int)
    command.add_argument("--writable-gates-passed", type=parse_boolean)
    command.add_argument("--parallel-gate-receipt", type=Path)
    command.add_argument("--uncertainty", choices=LEVELS)
    command.add_argument("--consequence", choices=LEVELS)
    command.add_argument("--independent-oracle", type=parse_boolean)
    return command


def main() -> int:
    command = parser()
    args = command.parse_args()
    if args.self_test:
        self_test()
        return 0

    required = {
        "work_kind": args.work_kind,
        "decomposable": args.decomposable,
        "stable_verifier": args.stable_verifier,
        "worker_capacity": args.worker_capacity,
        "worker_budget": args.worker_budget,
        "writable_gates_passed": args.writable_gates_passed,
        "uncertainty": args.uncertainty,
        "consequence": args.consequence,
        "independent_oracle": args.independent_oracle,
    }
    missing = [name.replace("_", "-") for name, value in required.items() if value is None]
    if missing:
        command.error(f"missing required arguments: {', '.join(missing)}")
    try:
        receipt = None
        if args.parallel_gate_receipt is not None:
            receipt, _ = load_parallel_gate_receipt(args.parallel_gate_receipt)
        result = select_team_shape(**required, parallel_gate_receipt=receipt)
    except TeamShapeError as error:
        command.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
