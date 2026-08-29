#!/usr/bin/env python3
"""Validate a host-neutral Patpat multi-PR plan contract."""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
UNIT_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NA = re.compile(r"^N/A:\s+\S", re.IGNORECASE)
PLAN_KEYS = {"schema_version", "objective", "delivery", "units"}
DELIVERY_KEYS = {"authority", "actions"}
UNIT_KEYS = {"id", "depends_on", "files", "build", "proof", "review_gate"}
PROOF_KEYS = {"observable", "targeted", "live", "performance", "evidence_binding"}
AUTHORITIES = {"none", "patpat-activation", "explicit-delivery", "explicit-merge"}
ACTIONS = {"commit", "non-force-push", "create-or-update-ready-pr", "merge"}
MAX_PLAN_BYTES = 256 * 1024
MAX_UNITS = 64
MAX_DEPENDENCIES = 32
MAX_FILES = 64
MAX_ID_LENGTH = 64
MAX_PATH_LENGTH = 512
MAX_OBJECTIVE_LENGTH = 2000
MAX_TEXT_LENGTH = 4096
GLOB_CHARACTERS = frozenset("*?[]{}")


class PlanError(ValueError):
    """Raised when a multi-PR plan violates the contract."""


def nonempty(value: Any, maximum: int = MAX_TEXT_LENGTH) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and len(value) <= maximum
    )


def command_or_na(value: Any) -> bool:
    return nonempty(value) and (not value.casefold().startswith("n/a") or NA.match(value) is not None)


def unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))


def repository_pattern(value: Any) -> bool:
    if (
        not nonempty(value, MAX_PATH_LENGTH)
        or value.startswith(("/", "\\"))
        or "\\" in value
        or "//" in value
    ):
        return False
    return ".." not in value.split("/")


def _parts(value: str) -> tuple[str, ...]:
    return tuple(part for part in value.strip("/").split("/") if part not in {"", "."})


def _literal_prefix(value: str) -> tuple[str, ...]:
    result: list[str] = []
    for part in _parts(value):
        if any(character in part for character in GLOB_CHARACTERS):
            break
        result.append(part)
    return tuple(result)


def _is_prefix(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    return len(left) <= len(right) and right[: len(left)] == left


def ownership_patterns_overlap(left: str, right: str) -> bool:
    """Conservatively detect exact, ancestor, and glob ownership collisions."""
    left_parts = _parts(left)
    right_parts = _parts(right)
    left_glob = any(character in left for character in GLOB_CHARACTERS)
    right_glob = any(character in right for character in GLOB_CHARACTERS)
    if not left_glob and not right_glob:
        return _is_prefix(left_parts, right_parts) or _is_prefix(right_parts, left_parts)
    if fnmatch.fnmatchcase(left, right) or fnmatch.fnmatchcase(right, left):
        return True
    left_prefix = _literal_prefix(left)
    right_prefix = _literal_prefix(right)
    if not left_prefix or not right_prefix:
        return True
    return _is_prefix(left_prefix, right_prefix) or _is_prefix(right_prefix, left_prefix)


def validate_delivery(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict) or set(value) != DELIVERY_KEYS:
        errors.append("delivery must contain exactly authority and actions")
        return
    authority = value.get("authority")
    actions = value.get("actions")
    if authority not in AUTHORITIES:
        errors.append(f"delivery.authority must be one of {sorted(AUTHORITIES)}")
    if not unique_strings(actions) or not set(actions) <= ACTIONS:
        errors.append(f"delivery.actions must be unique values from {sorted(ACTIONS)}")
        return
    if authority == "none" and actions:
        errors.append("delivery authority none requires no actions")
    if authority != "none" and not actions:
        errors.append("delivery authority must name at least one allowed action")
    if "merge" in actions and authority != "explicit-merge":
        errors.append("merge requires explicit-merge authority")
    if authority == "explicit-merge" and "merge" not in actions:
        errors.append("explicit-merge authority must name merge")
    if "create-or-update-ready-pr" in actions and "non-force-push" not in actions:
        errors.append("pull-request delivery requires non-force-push")


def validate_unit(value: Any, index: int, errors: list[str]) -> str | None:
    label = f"units[{index}]"
    if not isinstance(value, dict) or set(value) != UNIT_KEYS:
        errors.append(f"{label} must contain exactly {sorted(UNIT_KEYS)}")
        return None
    unit_id = value.get("id")
    if (
        not isinstance(unit_id, str)
        or len(unit_id) > MAX_ID_LENGTH
        or UNIT_ID.fullmatch(unit_id) is None
    ):
        errors.append(f"{label}.id must be lowercase kebab-case and at most {MAX_ID_LENGTH} characters")
        unit_id = None
    dependencies = value.get("depends_on")
    if (
        not unique_strings(dependencies)
        or len(dependencies) > MAX_DEPENDENCIES
        or not all(len(item) <= MAX_ID_LENGTH and UNIT_ID.fullmatch(item) for item in dependencies)
    ):
        errors.append(f"{label}.depends_on must contain at most {MAX_DEPENDENCIES} unique unit ids")
    files = value.get("files")
    if (
        not unique_strings(files)
        or not files
        or len(files) > MAX_FILES
        or not all(repository_pattern(item) for item in files)
    ):
        errors.append(
            f"{label}.files must contain at most {MAX_FILES} unique bounded repository paths or patterns"
        )
    if not command_or_na(value.get("build")):
        errors.append(f"{label}.build must name a command or use N/A: <reason>")
    proof = value.get("proof")
    if not isinstance(proof, dict) or set(proof) != PROOF_KEYS:
        errors.append(f"{label}.proof must contain exactly {sorted(PROOF_KEYS)}")
    else:
        if not nonempty(proof.get("observable")) or NA.match(proof["observable"]):
            errors.append(f"{label}.proof.observable must name the behavior to observe")
        for field in ("targeted", "live", "performance"):
            if not command_or_na(proof.get(field)):
                errors.append(f"{label}.proof.{field} must name a check or use N/A: <reason>")
        if proof.get("evidence_binding") != "exact-head":
            errors.append(f"{label}.proof.evidence_binding must be exact-head")
    if value.get("review_gate") != "independent-pass-before-delivery":
        errors.append(f"{label}.review_gate must be independent-pass-before-delivery")
    return unit_id


def graph_errors(units: list[Any], ids: list[str], errors: list[str]) -> None:
    if len(ids) != len(set(ids)):
        errors.append("unit ids must be unique")
    known = set(ids)
    graph: dict[str, list[str]] = {}
    for value in units:
        if not isinstance(value, dict) or value.get("id") not in known:
            continue
        dependencies = value.get("depends_on")
        if not isinstance(dependencies, list):
            continue
        graph[value["id"]] = dependencies
        missing = sorted(set(dependencies) - known)
        if missing:
            errors.append(f"unit {value['id']} has unknown dependencies: {missing}")
        if value["id"] in dependencies:
            errors.append(f"unit {value['id']} cannot depend on itself")

    indegree = {unit_id: 0 for unit_id in graph}
    dependents: dict[str, list[str]] = {unit_id: [] for unit_id in graph}
    for unit_id, dependencies in graph.items():
        for dependency in dependencies:
            if dependency in graph:
                indegree[unit_id] += 1
                dependents[dependency].append(unit_id)
    frontier = [unit_id for unit_id, degree in indegree.items() if degree == 0]
    visited = 0
    while frontier:
        unit_id = frontier.pop()
        visited += 1
        for dependent in dependents[unit_id]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                frontier.append(dependent)
    if visited != len(graph):
        errors.append("unit dependency graph must be acyclic")

    ancestors: dict[str, set[str]] = {}
    for unit_id in graph:
        found: set[str] = set()
        pending = list(graph[unit_id])
        while pending:
            dependency = pending.pop()
            if dependency in graph and dependency not in found:
                found.add(dependency)
                pending.extend(graph[dependency])
        ancestors[unit_id] = found

    valid_units = {
        unit["id"]: unit
        for unit in units
        if isinstance(unit, dict)
        and unit.get("id") in graph
        and isinstance(unit.get("files"), list)
        and all(isinstance(item, str) for item in unit["files"])
    }
    ordered_ids = sorted(valid_units)
    for index, left_id in enumerate(ordered_ids):
        for right_id in ordered_ids[index + 1 :]:
            if left_id in ancestors[right_id] or right_id in ancestors[left_id]:
                continue
            for left in valid_units[left_id]["files"]:
                for right in valid_units[right_id]["files"]:
                    if ownership_patterns_overlap(left, right):
                        errors.append(
                            f"unordered units {left_id} and {right_id} have overlapping ownership: {left!r} vs {right!r}"
                        )
                        break
                else:
                    continue
                break


def validate_plan(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        return [f"plan must contain exactly {sorted(PLAN_KEYS)}"]
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not nonempty(value.get("objective"), MAX_OBJECTIVE_LENGTH):
        errors.append(
            f"objective must be a non-empty string of at most {MAX_OBJECTIVE_LENGTH} characters without outer whitespace"
        )
    validate_delivery(value.get("delivery"), errors)
    units = value.get("units")
    if not isinstance(units, list) or not units or len(units) > MAX_UNITS:
        errors.append(f"units must be a non-empty list with at most {MAX_UNITS} entries")
        return errors
    ids = [unit_id for index, unit in enumerate(units) if (unit_id := validate_unit(unit, index, errors))]
    graph_errors(units, ids, errors)
    return errors


def example_plan() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "objective": "Deliver two independently provable pull requests.",
        "delivery": {
            "authority": "patpat-activation",
            "actions": ["commit", "non-force-push", "create-or-update-ready-pr"],
        },
        "units": [
            {
                "id": "contract",
                "depends_on": [],
                "files": ["src/contract.py", "tests/test_contract.py"],
                "build": "python3 -m compileall src",
                "proof": {
                    "observable": "The public contract rejects an invalid payload.",
                    "targeted": "python3 -m unittest tests.test_contract",
                    "live": "N/A: pure library with no live surface",
                    "performance": "N/A: no performance-sensitive path changed",
                    "evidence_binding": "exact-head",
                },
                "review_gate": "independent-pass-before-delivery",
            },
            {
                "id": "consumer",
                "depends_on": ["contract"],
                "files": ["src/consumer.py", "tests/test_consumer.py"],
                "build": "python3 -m compileall src",
                "proof": {
                    "observable": "The consumer handles the validated payload end to end.",
                    "targeted": "python3 -m unittest tests.test_consumer",
                    "live": "python3 -m app.smoke_consumer",
                    "performance": "N/A: no performance-sensitive path changed",
                    "evidence_binding": "exact-head",
                },
                "review_gate": "independent-pass-before-delivery",
            },
        ],
    }


def run_self_test() -> None:
    valid = example_plan()
    assert validate_plan(valid) == []

    mutations = [
        (lambda plan: plan["units"][1].update(depends_on=["missing"]), "unknown dependencies"),
        (lambda plan: plan["units"][0].update(depends_on=["consumer"]), "acyclic"),
        (lambda plan: plan["units"][0].update(files=[]), ".files"),
        (lambda plan: plan["units"][0].update(build="N/A"), ".build"),
        (lambda plan: plan["units"][0]["proof"].update(observable="N/A: nothing"), ".proof.observable"),
        (lambda plan: plan["units"][0]["proof"].update(targeted="N/A"), ".proof.targeted"),
        (lambda plan: plan["units"][0]["proof"].update(live="N/A"), ".proof.live"),
        (lambda plan: plan["units"][0]["proof"].update(performance="N/A"), ".proof.performance"),
        (lambda plan: plan["units"][0]["proof"].update(evidence_binding="branch"), "exact-head"),
        (lambda plan: plan["units"][0].update(review_gate="self-review"), "review_gate"),
        (lambda plan: plan["delivery"].update(authority="none"), "authority none"),
        (lambda plan: plan["delivery"]["actions"].append("merge"), "explicit-merge"),
        (lambda plan: plan.update(objective="x" * (MAX_OBJECTIVE_LENGTH + 1)), "objective"),
        (
            lambda plan: (
                plan["units"][1].update(depends_on=[]),
                plan["units"][0].update(files=["src"]),
            ),
            "overlapping ownership",
        ),
    ]
    for mutate, expected in mutations:
        candidate = copy.deepcopy(valid)
        mutate(candidate)
        observed = validate_plan(candidate)
        if not any(expected in error for error in observed):
            raise AssertionError(f"expected {expected!r} in {observed!r}")

    no_delivery = copy.deepcopy(valid)
    no_delivery["delivery"] = {"authority": "none", "actions": []}
    assert validate_plan(no_delivery) == []
    explicit_merge = copy.deepcopy(valid)
    explicit_merge["delivery"]["authority"] = "explicit-merge"
    explicit_merge["delivery"]["actions"].append("merge")
    assert validate_plan(explicit_merge) == []

    exact_overlap = copy.deepcopy(valid)
    exact_overlap["units"][1]["depends_on"] = []
    exact_overlap["units"][1]["files"] = ["src/contract.py"]
    assert any("overlapping ownership" in error for error in validate_plan(exact_overlap))

    glob_overlap = copy.deepcopy(valid)
    glob_overlap["units"][1]["depends_on"] = []
    glob_overlap["units"][0]["files"] = ["src/**"]
    glob_overlap["units"][1]["files"] = ["src/consumer.py"]
    assert any("overlapping ownership" in error for error in validate_plan(glob_overlap))

    disjoint_globs = copy.deepcopy(valid)
    disjoint_globs["units"][1]["depends_on"] = []
    disjoint_globs["units"][0]["files"] = ["src/contracts/**"]
    disjoint_globs["units"][1]["files"] = ["tests/**"]
    assert validate_plan(disjoint_globs) == []

    oversized = copy.deepcopy(valid)
    oversized["units"] = [copy.deepcopy(valid["units"][0]) for _ in range(MAX_UNITS + 1)]
    assert any("at most" in error for error in validate_plan(oversized))
    print("Patpat multi-PR plan self-test passed.")


def load_json(path: Path) -> Any:
    if path.is_symlink():
        raise PlanError("plan must be a unique regular file without symlinks")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise PlanError("plan must be a unique regular file without symlinks")
        if metadata.st_size > MAX_PLAN_BYTES:
            raise PlanError(f"plan exceeds the {MAX_PLAN_BYTES}-byte limit")
        chunks: list[bytes] = []
        remaining = MAX_PLAN_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_PLAN_BYTES:
            raise PlanError(f"plan exceeds the {MAX_PLAN_BYTES}-byte limit")
        return json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise PlanError(f"could not read plan: {error}") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--print-example", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
    if args.print_example:
        print(json.dumps(example_plan(), indent=2))
    if args.plan:
        try:
            errors = validate_plan(load_json(args.plan))
        except PlanError as error:
            print(error, file=sys.stderr)
            return 2
        if errors:
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Patpat multi-PR plan is valid: {args.plan}")
    if not (args.self_test or args.print_example or args.plan):
        parser.error("provide a plan, --self-test, or --print-example")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
