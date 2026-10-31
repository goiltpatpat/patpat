#!/usr/bin/env python3
"""Verify the presence, shape, and contract of a Patpat execution plan."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

PLAN_RELATIVE = ".patpat/plan.json"
MAX_PLAN_BYTES = 256 * 1024
UNIT_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
AUTHORITIES = {"none", "patpat-activation", "explicit-delivery", "explicit-merge"}

RUN_SCRIPTS = Path(__file__).resolve().parents[2] / "patpat-run" / "scripts"
if str(RUN_SCRIPTS) not in sys.path and (RUN_SCRIPTS / "validate_plan.py").is_file():
    sys.path.insert(0, str(RUN_SCRIPTS))

try:
    import validate_plan as canonical_plan_validator
except ImportError:
    canonical_plan_validator = None


class PlanVerificationError(ValueError):
    """The execution plan cannot establish execution-plan-settled."""


def verify_plan_data(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PlanVerificationError(f"plan at {path} must be a JSON object")
    if "schema_version" not in data or type(data["schema_version"]) is not int:
        raise PlanVerificationError(f"plan at {path} missing valid integer schema_version")
    if data["schema_version"] != 1:
        raise PlanVerificationError(f"plan at {path} has unsupported schema_version: {data['schema_version']!r}")
    objective = data.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise PlanVerificationError(f"plan at {path} missing non-empty objective")

    # Delivery authority check
    delivery = data.get("delivery")
    if not isinstance(delivery, dict):
        raise PlanVerificationError(f"plan at {path} missing valid delivery object")
    if delivery.get("authority") not in AUTHORITIES:
        raise PlanVerificationError(f"plan at {path} has invalid delivery authority: {delivery.get('authority')!r}")
    if not isinstance(delivery.get("actions"), list):
        raise PlanVerificationError(f"plan at {path} delivery actions must be a list")

    # Units check
    units = data.get("units")
    if not isinstance(units, list) or not units:
        raise PlanVerificationError(f"plan at {path} must declare non-empty units list")

    seen_ids: set[str] = set()
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise PlanVerificationError(f"plan at {path} unit {index} must be an object")
        unit_id = unit.get("id")
        if not isinstance(unit_id, str) or not UNIT_ID_PATTERN.match(unit_id):
            raise PlanVerificationError(f"plan at {path} unit {index} missing valid kebab-case id")
        if unit_id in seen_ids:
            raise PlanVerificationError(f"plan at {path} contains duplicate unit id: {unit_id!r}")
        seen_ids.add(unit_id)

        depends_on = unit.get("depends_on")
        if not isinstance(depends_on, list) or any(not isinstance(dep, str) for dep in depends_on):
            raise PlanVerificationError(f"plan at {path} unit {unit_id!r} depends_on must be a list of strings")
        if unit_id in depends_on:
            raise PlanVerificationError(f"plan at {path} unit {unit_id!r} cannot depend on itself")

    # Delegate to full canonical validator if available
    if canonical_plan_validator is not None:
        errors = canonical_plan_validator.validate_plan(data)
        if errors:
            raise PlanVerificationError(f"plan canonical contract violation: {'; '.join(errors)}")

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

        # 6. Valid canonical plan must pass
        valid = root / "valid.json"
        if canonical_plan_validator is not None:
            valid_data = canonical_plan_validator.example_plan()
        else:
            valid_data = {
                "schema_version": 1,
                "objective": "test plan",
                "delivery": {"authority": "none", "actions": []},
                "units": [
                    {
                        "id": "unit-1",
                        "depends_on": [],
                        "files": ["src/main.py"],
                        "build": "python3 -m compileall src",
                        "proof": {
                            "observable": "observable change",
                            "targeted": "python3 -m unittest",
                            "live": "N/A: library",
                            "performance": "N/A: standard",
                            "evidence_binding": "exact-head",
                        },
                        "review_gate": "independent-pass-before-delivery",
                    }
                ],
            }
        valid.write_text(json.dumps(valid_data), encoding="utf-8")
        res = verify_plan(valid)
        if len(res["units"]) < 1:
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
