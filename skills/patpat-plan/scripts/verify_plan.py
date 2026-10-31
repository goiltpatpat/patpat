#!/usr/bin/env python3
"""Verify the presence, shape, and contract of a Patpat execution plan."""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PLAN_RELATIVE = ".patpat/plan.json"
MAX_PLAN_BYTES = 256 * 1024
SCHEMA_VERSION = 1
UNIT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
NA_PATTERN = re.compile(r"^N/A:\s+\S", re.IGNORECASE)
PLAN_KEYS = {"schema_version", "objective", "delivery", "units"}
DELIVERY_KEYS = {"authority", "actions"}
UNIT_KEYS = {"id", "depends_on", "files", "build", "proof", "review_gate"}
PROOF_KEYS = {"observable", "targeted", "live", "performance", "evidence_binding"}
AUTHORITIES = {"none", "patpat-activation", "explicit-delivery", "explicit-merge"}
ACTIONS = {"commit", "non-force-push", "create-or-update-ready-pr", "merge"}
MAX_UNITS = 64
MAX_DEPENDENCIES = 32
MAX_FILES = 64
MAX_ID_LENGTH = 64
MAX_PATH_LENGTH = 512
MAX_OBJECTIVE_LENGTH = 2000
MAX_TEXT_LENGTH = 4096
GLOB_CHARACTERS = frozenset("*?[]{}")

RUN_SCRIPTS = Path(__file__).resolve().parents[2] / "patpat-run" / "scripts"
if str(RUN_SCRIPTS) not in sys.path and (RUN_SCRIPTS / "validate_plan.py").is_file():
    sys.path.insert(0, str(RUN_SCRIPTS))

try:
    import validate_plan as canonical_plan_validator
except ImportError:
    canonical_plan_validator = None


class PlanVerificationError(ValueError):
    """The execution plan cannot establish execution-plan-settled."""


def _nonempty(value: Any, maximum: int = MAX_TEXT_LENGTH) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and value == value.strip()
        and len(value) <= maximum
    )


def _command_or_na(value: Any) -> bool:
    return _nonempty(value) and (not value.casefold().startswith("n/a") or NA_PATTERN.match(value) is not None)


def _unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))


def _repository_pattern(value: Any) -> bool:
    if (
        not _nonempty(value, MAX_PATH_LENGTH)
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


def _ownership_patterns_overlap(left: str, right: str) -> bool:
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


def _validate_delivery(value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict) or set(value) != DELIVERY_KEYS:
        errors.append("delivery must contain exactly authority and actions")
        return
    authority = value.get("authority")
    actions = value.get("actions")
    if authority not in AUTHORITIES:
        errors.append(f"delivery.authority must be one of {sorted(AUTHORITIES)}")
    if not _unique_strings(actions) or not set(actions) <= ACTIONS:
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


def _validate_unit(value: Any, index: int, errors: list[str]) -> str | None:
    label = f"units[{index}]"
    if not isinstance(value, dict) or set(value) != UNIT_KEYS:
        errors.append(f"{label} must contain exactly {sorted(UNIT_KEYS)}")
        return None
    unit_id = value.get("id")
    if (
        not isinstance(unit_id, str)
        or len(unit_id) > MAX_ID_LENGTH
        or UNIT_ID_PATTERN.fullmatch(unit_id) is None
    ):
        errors.append(f"{label}.id must be lowercase kebab-case and at most {MAX_ID_LENGTH} characters")
        unit_id = None
    dependencies = value.get("depends_on")
    if (
        not _unique_strings(dependencies)
        or len(dependencies) > MAX_DEPENDENCIES
        or not all(len(item) <= MAX_ID_LENGTH and UNIT_ID_PATTERN.fullmatch(item) for item in dependencies)
    ):
        errors.append(f"{label}.depends_on must contain at most {MAX_DEPENDENCIES} unique unit ids")
    files = value.get("files")
    if (
        not _unique_strings(files)
        or not files
        or len(files) > MAX_FILES
        or not all(_repository_pattern(item) for item in files)
    ):
        errors.append(
            f"{label}.files must contain at most {MAX_FILES} unique bounded repository paths or patterns"
        )
    if not _command_or_na(value.get("build")):
        errors.append(f"{label}.build must name a command or use N/A: <reason>")
    proof = value.get("proof")
    if not isinstance(proof, dict) or set(proof) != PROOF_KEYS:
        errors.append(f"{label}.proof must contain exactly {sorted(PROOF_KEYS)}")
    else:
        if not _nonempty(proof.get("observable")) or NA_PATTERN.match(proof["observable"]):
            errors.append(f"{label}.proof.observable must name the behavior to observe")
        for field in ("targeted", "live", "performance"):
            if not _command_or_na(proof.get(field)):
                errors.append(f"{label}.proof.{field} must name a check or use N/A: <reason>")
        if proof.get("evidence_binding") != "exact-head":
            errors.append(f"{label}.proof.evidence_binding must be exact-head")
    if value.get("review_gate") != "independent-pass-before-delivery":
        errors.append(f"{label}.review_gate must be independent-pass-before-delivery")
    return unit_id


def _graph_errors(units: list[Any], ids: list[str], errors: list[str]) -> None:
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
                    if _ownership_patterns_overlap(left, right):
                        errors.append(
                            f"unordered units {left_id} and {right_id} have overlapping ownership: {left!r} vs {right!r}"
                        )
                        break
                else:
                    continue
                break


def validate_plan_contract(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        return [f"plan must contain exactly {sorted(PLAN_KEYS)}"]
    schema_version = value.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not _nonempty(value.get("objective"), MAX_OBJECTIVE_LENGTH):
        errors.append(
            f"objective must be a non-empty string of at most {MAX_OBJECTIVE_LENGTH} characters without outer whitespace"
        )
    _validate_delivery(value.get("delivery"), errors)
    units = value.get("units")
    if not isinstance(units, list) or not units or len(units) > MAX_UNITS:
        errors.append(f"units must be a non-empty list with at most {MAX_UNITS} entries")
        return errors
    ids = [unit_id for index, unit in enumerate(units) if (unit_id := _validate_unit(unit, index, errors))]
    _graph_errors(units, ids, errors)
    return errors


def example_plan() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "objective": "Verify plan contract enforcement",
        "delivery": {
            "authority": "explicit-delivery",
            "actions": ["commit", "non-force-push", "create-or-update-ready-pr"],
        },
        "units": [
            {
                "id": "contract",
                "depends_on": [],
                "files": ["src/contract.py", "tests/test_contract.py"],
                "build": "python3 -m compileall src",
                "proof": {
                    "observable": "The contract rejects invalid payloads.",
                    "targeted": "python3 -m unittest tests.test_contract",
                    "live": "N/A: pure library",
                    "performance": "N/A: standard path",
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
                    "observable": "The consumer processes validated payloads.",
                    "targeted": "python3 -m unittest tests.test_consumer",
                    "live": "N/A: test harness",
                    "performance": "N/A: standard path",
                    "evidence_binding": "exact-head",
                },
                "review_gate": "independent-pass-before-delivery",
            },
        ],
    }


def verify_plan_data(data: Any, path: Path) -> dict[str, Any]:
    # 1. Full self-contained validation (guaranteed portability, cannot silently downgrade)
    errors = validate_plan_contract(data)
    if errors:
        raise PlanVerificationError(f"plan contract violation: {'; '.join(errors)}")

    # 2. Canonical plan validator check when available (ensures full parity)
    if canonical_plan_validator is not None:
        canonical_errors = canonical_plan_validator.validate_plan(data)
        if canonical_errors:
            raise PlanVerificationError(f"plan canonical contract violation: {'; '.join(canonical_errors)}")

    return data


def verify_plan(plan_path: Path) -> dict[str, Any]:
    if not plan_path.is_file():
        raise PlanVerificationError(f"missing execution plan: {plan_path}")
    raw = plan_path.read_bytes()
    if len(raw) > MAX_PLAN_BYTES:
        raise PlanVerificationError(f"plan exceeds {MAX_PLAN_BYTES} byte limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlanVerificationError(f"invalid JSON in plan: {error}") from error
    return verify_plan_data(data, plan_path)


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1. Missing plan must fail
        missing = root / "missing.json"
        try:
            verify_plan(missing)
        except PlanVerificationError:
            pass
        else:
            raise AssertionError("missing plan was accepted")

        # 2. Invalid JSON must fail
        bad_json = root / "bad.json"
        bad_json.write_text("{not-json", encoding="utf-8")
        try:
            verify_plan(bad_json)
        except PlanVerificationError:
            pass
        else:
            raise AssertionError("invalid JSON plan was accepted")

        # 3. Missing objective must fail
        missing_obj = root / "no_obj.json"
        missing_obj.write_text(json.dumps({"schema_version": 1, "units": ["u1"]}), encoding="utf-8")
        try:
            verify_plan(missing_obj)
        except PlanVerificationError:
            pass
        else:
            raise AssertionError("plan without objective was accepted")

        # 4. Empty units must fail
        empty_units = root / "empty_units.json"
        empty_units.write_text(json.dumps({"schema_version": 1, "objective": "test", "units": []}), encoding="utf-8")
        try:
            verify_plan(empty_units)
        except PlanVerificationError:
            pass
        else:
            raise AssertionError("plan with empty units was accepted")

        # 5. Missing delivery must fail
        no_delivery = root / "no_delivery.json"
        no_delivery.write_text(
            json.dumps({"schema_version": 1, "objective": "test", "units": [{"id": "unit-1"}]}),
            encoding="utf-8",
        )
        try:
            verify_plan(no_delivery)
        except PlanVerificationError:
            pass
        else:
            raise AssertionError("plan without delivery was accepted")

        # 6. Unknown dependency must fail
        bad_dep = root / "unknown_dep.json"
        bad_dep_data = example_plan()
        bad_dep_data["units"][1]["depends_on"] = ["non-existent-unit"]
        bad_dep.write_text(json.dumps(bad_dep_data), encoding="utf-8")
        try:
            verify_plan(bad_dep)
        except PlanVerificationError as err:
            if "unknown dependencies" not in str(err):
                raise AssertionError(f"expected unknown dependencies error, got {err}") from err
        else:
            raise AssertionError("plan with unknown dependency was accepted")

        # 7. DAG cycle must fail
        cycle_plan = root / "cycle.json"
        cycle_data = example_plan()
        cycle_data["units"][0]["depends_on"] = ["consumer"]
        cycle_plan.write_text(json.dumps(cycle_data), encoding="utf-8")
        try:
            verify_plan(cycle_plan)
        except PlanVerificationError as err:
            if "acyclic" not in str(err):
                raise AssertionError(f"expected acyclic error, got {err}") from err
        else:
            raise AssertionError("cyclic plan was accepted")

        # 8. Overlapping ownership between unordered units must fail
        overlap_plan = root / "overlap.json"
        overlap_data = example_plan()
        overlap_data["units"][1]["depends_on"] = []  # Make unordered
        overlap_data["units"][0]["files"] = ["src/*"]
        overlap_data["units"][1]["files"] = ["src/consumer.py"]
        overlap_plan.write_text(json.dumps(overlap_data), encoding="utf-8")
        try:
            verify_plan(overlap_plan)
        except PlanVerificationError as err:
            if "overlapping ownership" not in str(err):
                raise AssertionError(f"expected overlapping ownership error, got {err}") from err
        else:
            raise AssertionError("plan with overlapping ownership was accepted")

        # 9. Valid canonical plan must pass
        valid = root / "valid.json"
        valid.write_text(json.dumps(example_plan()), encoding="utf-8")
        res = verify_plan(valid)
        if len(res["units"]) != 2:
            raise AssertionError("valid plan parsed incorrectly")

    print("Plan verifier self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="workspace root (default: current directory)")
    parser.add_argument("--plan", type=Path, help="direct path to plan JSON")
    parser.add_argument("--self-test", action="store_true", help="run self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    plan_path = args.plan or (args.root / PLAN_RELATIVE)
    try:
        data = verify_plan(plan_path)
        print(f"Execution plan verified: {plan_path} ({len(data['units'])} units)")
        return 0
    except (PlanVerificationError, OSError) as error:
        print(f"plan verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
