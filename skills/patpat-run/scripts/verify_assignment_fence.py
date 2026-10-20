#!/usr/bin/env python3
"""Bounded pilot for the current-assignment generation and context guard."""

from __future__ import annotations

import argparse
import itertools
import sys
import tempfile
import types
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import program_state
from team_shape import PARALLEL_GATE_CHECKS, bind_parallel_gate_evidence


REQUESTED_GENERATIONS = (0, 1, 2, 3, 4, True, -1, "1", None)
ASSIGNMENT_GENERATIONS = (1, 2, 3)
ACTORS = (None, "worker", "WORKER", "other", " worker ")
ISOLATION_IDENTITIES = (
    None,
    "worker-space",
    "WORKER-SPACE",
    "other-space",
    " worker-space ",
)
MAX_ALLOWED_GENERATION = (1 << 63) - 1


def _evidence_binding(path: Path) -> dict[str, Any]:
    reference = bind_parallel_gate_evidence(path)
    return {
        check: [dict(reference)]
        for check in PARALLEL_GATE_CHECKS
    }


def _case_inputs() -> Any:
    for (
        gate_open,
        binding_mode,
        assigned,
        assignment_generation,
        requested_generation,
        actor,
        isolation,
    ) in itertools.product(
        (False, True),
        ("missing", "fresh", "stale"),
        (False, True),
        ASSIGNMENT_GENERATIONS,
        REQUESTED_GENERATIONS,
        ACTORS,
        ISOLATION_IDENTITIES,
    ):
        yield (
            gate_open,
            binding_mode,
            assigned,
            assignment_generation,
            requested_generation,
            actor,
            isolation,
        )


def _scenario(
    case: tuple[Any, ...], evidence: dict[str, list[dict[str, Any]]]
) -> tuple[dict[str, Any], dict[str, Any], Any, str | None, str | None]:
    (
        gate_open,
        binding_mode,
        assigned,
        assignment_generation,
        requested_generation,
        actor,
        isolation,
    ) = case
    supporting_evidence = evidence
    if binding_mode == "stale":
        supporting_evidence = {
            name: [dict(reference) for reference in references]
            for name, references in evidence.items()
        }
        reference = supporting_evidence[PARALLEL_GATE_CHECKS[0]][0]
        reference["sha256"] = "0" * 64 if reference["sha256"] != "0" * 64 else "1" * 64
    binding = (
        {"supporting_evidence": supporting_evidence}
        if binding_mode != "missing"
        else None
    )
    state = {
        "gates": {"dispatch": {"open": gate_open}},
        "dispatch_binding": binding,
    }
    unit = {
        "assignment": (
            {
                "actor": "worker",
                "isolation_identity": "worker-space",
                "generation": assignment_generation,
                "assigned_at": "2026-01-01T00:00:00+00:00",
            }
            if assigned
            else None
        )
    }
    return state, unit, requested_generation, actor, isolation


def _oracle(case: tuple[Any, ...]) -> bool:
    gate_open, binding_mode, assigned, assignment_generation, requested, actor, isolation = case
    valid_generation = (
        type(requested) is int
        and 0 <= requested <= MAX_ALLOWED_GENERATION
    )
    actor_matches = actor is None or (
        actor == actor.strip() and actor.casefold() == "worker"
    )
    isolation_matches = isolation is None or (
        isolation == isolation.strip()
        and isolation.casefold() == "worker-space"
    )
    return (
        gate_open
        and binding_mode == "fresh"
        and assigned
        and valid_generation
        and requested == assignment_generation
        and actor_matches
        and isolation_matches
    )


def _accepts(
    module: types.ModuleType,
    case: tuple[Any, ...],
    evidence: dict[str, list[dict[str, Any]]],
) -> bool:
    state, unit, generation, actor, isolation = _scenario(case, evidence)
    try:
        module.require_current_assignment(
            state,
            unit,
            generation,
            actor=actor,
            isolation_identity=isolation,
        )
    except module.ProgramStateError:
        return False
    return True


def _first_counterexample(
    module: types.ModuleType,
    evidence: dict[str, list[dict[str, Any]]],
) -> tuple[int, tuple[Any, ...] | None, bool | None, bool | None]:
    count = 0
    for case in _case_inputs():
        count += 1
        expected = _oracle(case)
        actual = _accepts(module, case, evidence)
        if expected != actual:
            return count, case, expected, actual
    return count, None, None, None


def _weaken_generation_guard() -> types.ModuleType:
    source_path = Path(program_state.__file__)
    source = source_path.read_text(encoding="utf-8")
    original = 'if snapshot["generation"] != expected_generation:'
    if source.count(original) != 1:
        raise AssertionError("generation guard mutation target is missing or ambiguous")
    mutant = types.ModuleType("program_state_generation_guard_mutant")
    mutant.__file__ = str(source_path)
    mutant.__package__ = ""
    mutated_source = source.replace(original, "if False:", 1)
    exec(compile(mutated_source, str(source_path), "exec"), mutant.__dict__)
    return mutant


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="patpat-assignment-fence-") as raw:
        evidence_path = Path(raw) / "parallel-gate-evidence.txt"
        evidence_path.write_text("bounded assignment-fence pilot evidence\n", encoding="utf-8")
        evidence = _evidence_binding(evidence_path)
        cases, counterexample, expected, actual = _first_counterexample(
            program_state, evidence
        )
        if counterexample is not None:
            raise AssertionError(
                "current assignment guard disagrees with the bounded oracle: "
                f"case={counterexample!r}, expected={expected}, actual={actual}"
            )
        mutant = _weaken_generation_guard()
        mutant_cases, mutant_case, mutant_expected, mutant_actual = _first_counterexample(
            mutant, evidence
        )
        if mutant_case is None:
            raise AssertionError("bounded checker did not detect the weakened generation guard")

    print(
        "Bounded assignment-fence pilot passed: "
        f"{cases} finite cases matched; weakened guard rejected at case {mutant_cases} "
        f"(expected={mutant_expected}, actual={mutant_actual})."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--self-test", action="store_true")
    args = command.parse_args(argv)
    if not args.self_test:
        command.error("--self-test is required")
    return self_test()


if __name__ == "__main__":
    raise SystemExit(main())
