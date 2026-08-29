#!/usr/bin/env python3
"""Select a bounded Patpat team topology from explicit task evidence."""

from __future__ import annotations

import argparse
import json
from typing import Any


LEVELS = ("low", "medium", "high")
WORK_KINDS = ("read-only", "writable")
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

    reasons = [
        f"work is {work_kind}",
        f"worker limit is bounded by observed capacity {capacity} and explicit budget {budget}",
    ]
    pattern = "iterative"
    worker_limit = 1

    if work_kind == "writable" and not writable_gates_passed:
        reasons.append("serial fallback: writable earned-parallelism gates lack a receipt")
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
        result = select_team_shape(**required)
    except TeamShapeError as error:
        command.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
