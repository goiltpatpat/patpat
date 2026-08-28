#!/usr/bin/env python3
"""Validate a host-neutral Patpat multi-PR plan contract."""

from __future__ import annotations

import argparse
import copy
import json
import re
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


class PlanError(ValueError):
    """Raised when a multi-PR plan violates the contract."""


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def command_or_na(value: Any) -> bool:
    return nonempty(value) and (not value.casefold().startswith("n/a") or NA.match(value) is not None)


def unique_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) == len(set(value))


def repository_pattern(value: Any) -> bool:
    if not nonempty(value) or value.startswith(("/", "\\")) or "\\" in value:
        return False
    return ".." not in value.split("/")


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
    if not isinstance(unit_id, str) or UNIT_ID.fullmatch(unit_id) is None:
        errors.append(f"{label}.id must be lowercase kebab-case")
        unit_id = None
    dependencies = value.get("depends_on")
    if not unique_strings(dependencies) or not all(UNIT_ID.fullmatch(item) for item in dependencies):
        errors.append(f"{label}.depends_on must contain unique unit ids")
    files = value.get("files")
    if not unique_strings(files) or not files or not all(repository_pattern(item) for item in files):
        errors.append(f"{label}.files must contain unique non-empty repository paths or patterns")
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

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(unit_id: str) -> None:
        if unit_id in visiting:
            errors.append("unit dependency graph must be acyclic")
            return
        if unit_id in visited:
            return
        visiting.add(unit_id)
        for dependency in graph.get(unit_id, []):
            if dependency in graph:
                visit(dependency)
        visiting.remove(unit_id)
        visited.add(unit_id)

    for unit_id in graph:
        visit(unit_id)


def validate_plan(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict) or set(value) != PLAN_KEYS:
        return [f"plan must contain exactly {sorted(PLAN_KEYS)}"]
    if value.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if not nonempty(value.get("objective")):
        errors.append("objective must be a non-empty string without outer whitespace")
    validate_delivery(value.get("delivery"), errors)
    units = value.get("units")
    if not isinstance(units, list) or not units:
        errors.append("units must be a non-empty list")
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
    print("Patpat multi-PR plan self-test passed.")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PlanError(f"could not read plan: {error}") from error


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
