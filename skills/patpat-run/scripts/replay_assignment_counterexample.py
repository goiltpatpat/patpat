#!/usr/bin/env python3
"""Replay the saved stale-generation TLC path through Patpat's Python API."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIRECTORY.parents[2]
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

import program_state


MODEL_RELATIVE = "skills/patpat-run/models/AssignmentGeneration.tla"
CONFIG_RELATIVE = "skills/patpat-run/models/AssignmentGeneration.mutant.cfg"
IMPLEMENTATION_RELATIVE = "skills/patpat-run/scripts/program_state.py"
REPLAY_KIND = "patpat-model-check-replay-receipt"
REPLAY_SCHEMA_VERSION = 1
MAX_RECEIPT_BYTES = 4 * 1024 * 1024
EXPECTED_BOUNDS = {"MaxGeneration": 3, "MaxSteps": 6}
SUPPORTED_MUTANTS = {
    "stale-generation": {
        "id": "stale-generation",
        "target_property": "NoStaleWrites",
        "changed_constants": {"EnforceGeneration": False},
    },
    "rejected-write": {
        "id": "rejected-write",
        "target_property": "SafeRejectedWrites",
        "changed_constants": {"InjectRejectedWrite": True},
    },
}
EXPECTED_MUTANT = SUPPORTED_MUTANTS["stale-generation"]
TLC_RECORD_PATTERNS = {
    "issued": re.compile(
        r"\[\s*token\s*\|->\s*(\d+)\s*,\s*worker\s*\|->\s*([A-Za-z][A-Za-z0-9_]*)\s*\]"
    ),
    "writes": re.compile(
        r"\[\s*token\s*\|->\s*(\d+)\s*,\s*current\s*\|->\s*(\d+)\s*\]"
    ),
    "attempts": re.compile(r"\[\s*accepted\s*\|->\s*(TRUE|FALSE)\s*\]"),
}


class ReplayError(ValueError):
    """Raised when a receipt is outside the supported replay pilot contract."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    with path.open("rb") as handle:
        payload = handle.read(MAX_RECEIPT_BYTES + 1)
    if len(payload) > MAX_RECEIPT_BYTES:
        raise ReplayError(f"receipt exceeds the {MAX_RECEIPT_BYTES}-byte limit")
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReplayError(f"receipt is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict):
        raise ReplayError("receipt root must be an object")
    return value, payload


def _parse_sequence(value: Any, variable: str) -> list[dict[str, Any]] | list[bool]:
    if not isinstance(value, str) or not value.startswith("<<") or not value.endswith(">>"):
        raise ReplayError(f"TLC variable {variable} is not a rendered sequence")
    body = value[2:-2]
    if not body.strip():
        return []
    pattern = TLC_RECORD_PATTERNS[variable]
    records = list(pattern.finditer(body))
    if not records:
        raise ReplayError(f"TLC variable {variable} has no parseable records")

    cursor = 0
    parsed: list[dict[str, Any]] | list[bool] = []
    for index, record in enumerate(records):
        separator = body[cursor : record.start()]
        if index == 0:
            if separator.strip():
                raise ReplayError(f"TLC variable {variable} has unexpected sequence content")
        elif re.fullmatch(r"\s*,\s*", separator) is None:
            raise ReplayError(f"TLC variable {variable} has an invalid record separator")
        groups = record.groups()
        if variable == "issued":
            parsed.append({"token": int(groups[0]), "worker": groups[1]})
        elif variable == "writes":
            parsed.append({"token": int(groups[0]), "current": int(groups[1])})
        else:
            parsed.append(groups[0] == "TRUE")
        cursor = record.end()
    if body[cursor:].strip():
        raise ReplayError(f"TLC variable {variable} has trailing sequence content")
    return parsed


def _parse_state(state: Any, index: int, max_steps: int) -> dict[str, Any]:
    expected_keys = {
        "generation",
        "assigned",
        "owner",
        "issued",
        "writes",
        "attempts",
        "steps",
    }
    if not isinstance(state, dict) or set(state) != expected_keys:
        raise ReplayError(f"trace state {index} has an unexpected variable set")
    if not isinstance(state["assigned"], str) or state["assigned"] not in {"TRUE", "FALSE"}:
        raise ReplayError(f"trace state {index} has an invalid assigned value")
    if not isinstance(state["owner"], str) or not state["owner"]:
        raise ReplayError(f"trace state {index} has an invalid owner value")
    counters = (state["generation"], state["steps"])
    if any(not isinstance(value, str) or re.fullmatch(r"(?:0|[1-9][0-9]*)", value) is None for value in counters):
        raise ReplayError(f"trace state {index} has a non-integer counter")
    generation, steps = (int(value) for value in counters)
    if generation < 0 or generation > EXPECTED_BOUNDS["MaxGeneration"]:
        raise ReplayError(f"trace state {index} exceeds the generation bound")
    if steps < 0 or steps > max_steps:
        raise ReplayError(f"trace state {index} exceeds the step bound")
    return {
        "generation": generation,
        "assigned": state["assigned"] == "TRUE",
        "owner": state["owner"],
        "issued": _parse_sequence(state["issued"], "issued"),
        "writes": _parse_sequence(state["writes"], "writes"),
        "attempts": _parse_sequence(state["attempts"], "attempts"),
        "steps": steps,
    }


def _validate_trace(receipt: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if (
        receipt.get("kind") != "patpat-model-check-receipt"
        or type(receipt.get("schema_version")) is not int
        or receipt.get("schema_version") != 1
    ):
        raise ReplayError("unsupported model-check receipt kind or schema version")
    case_id = receipt.get("case")
    if case_id not in SUPPORTED_MUTANTS:
        raise ReplayError(f"replay pilot accepts only supported mutants: {list(SUPPORTED_MUTANTS)}")
    if receipt.get("bounds") != EXPECTED_BOUNDS:
        raise ReplayError("receipt bounds do not match the AssignmentGeneration replay pilot")
    expected_meta = SUPPORTED_MUTANTS[case_id]
    if receipt.get("mutant", {}).get("id") != expected_meta["id"]:
        raise ReplayError("receipt mutant id does not match the supported mutant configuration")
    result = receipt.get("result")
    if not isinstance(result, dict) or result.get("outcome") != "counterexample":
        raise ReplayError("stale-generation receipt does not report a counterexample")
    if result.get("tlc_exit_code") != 0:
        raise ReplayError("TLC did not complete successfully for this receipt")
    checker = receipt.get("checker")
    if not isinstance(checker, dict) or checker.get("name") != "TLC" or not isinstance(checker.get("version"), str):
        raise ReplayError("receipt checker identity is missing or is not TLC")

    configuration = receipt.get("configuration")
    if not isinstance(configuration, dict) or configuration.get("path") != CONFIG_RELATIVE:
        raise ReplayError("receipt does not use the supported stale-generation TLC configuration")
    expected_constants = {
        "EnforceGeneration": True,
        "InjectRejectedWrite": False,
        "MaxGeneration": 3,
        "MaxSteps": 6,
        "NoWorker": "noWorker",
        "Workers": ["workerA", "workerB"],
    }
    expected_constants.update(expected_meta.get("changed_constants", {}))
    constants = configuration.get("constants")
    if not isinstance(constants, dict) or constants != expected_constants:
        raise ReplayError("receipt TLC constants do not match the replay pilot")

    properties = receipt.get("properties")
    if not isinstance(properties, list):
        raise ReplayError("receipt properties must be a list")
    target_prop = expected_meta["target_property"]
    matches = [item for item in properties if isinstance(item, dict) and item.get("name") == target_prop]
    if len(matches) != 1:
        raise ReplayError(f"receipt must contain exactly one {target_prop} property")
    prop = matches[0]
    if prop.get("outcome") != "counterexample" or type(prop.get("counterexample_count")) is not int:
        raise ReplayError(f"{target_prop} must contain a TLC counterexample")
    if prop["counterexample_count"] < 1:
        raise ReplayError(f"{target_prop} counterexample count must be positive")
    trace = prop.get("trace")
    if not isinstance(trace, list) or len(trace) < 2:
        raise ReplayError("replay pilot requires a valid counterexample path of at least 2 states")

    raw_states: list[dict[str, Any]] = []
    parsed_states: list[dict[str, Any]] = []
    previous: dict[str, str] | None = None
    for expected_index, item in enumerate(trace, 1):
        if not isinstance(item, dict) or item.get("index") != expected_index:
            raise ReplayError("trace indexes must be consecutive and one-based")
        action = item.get("action")
        if not isinstance(action, str) or not action:
            raise ReplayError(f"trace state {expected_index} has no raw TLC action")
        if expected_index == 1:
            if action != "Initial predicate":
                raise ReplayError("the first trace action must be the initial predicate")
        elif not action.startswith("Next line "):
            raise ReplayError("trace transition is not attributed to the expected TLC Next action")
        raw_state = item.get("state")
        parsed = _parse_state(raw_state, expected_index, EXPECTED_BOUNDS["MaxSteps"])
        changed_keys = item.get("changed_keys")
        expected_changed = (
            []
            if previous is None
            else sorted(key for key in previous.keys() | raw_state.keys() if previous.get(key) != raw_state.get(key))
        )
        if changed_keys != expected_changed:
            raise ReplayError(f"trace state {expected_index} changed_keys do not match adjacent states")
        raw_states.append(item)
        parsed_states.append(parsed)
        previous = raw_state

    if case_id == "stale-generation":
        if len(parsed_states) != 4:
            raise ReplayError("stale-generation receipt requires a 4-state trace")
        initial, first_assignment, reassignment, stale_write = parsed_states
        if initial != {
            "generation": 0,
            "assigned": False,
            "owner": "noWorker",
            "issued": [],
            "writes": [],
            "attempts": [],
            "steps": 0,
        }:
            raise ReplayError("receipt initial state is not the expected empty assignment state")
        if not _is_assignment_transition(initial, first_assignment):
            raise ReplayError("trace state 2 is not a single valid assignment")
        if not _is_assignment_transition(first_assignment, reassignment):
            raise ReplayError("trace state 3 is not a single reassignment")
        if first_assignment["owner"] not in {"workerA", "workerB"} or reassignment["owner"] not in {
            "workerA",
            "workerB",
        }:
            raise ReplayError("trace assignments name a worker outside the configured worker set")
        first_issued = first_assignment["issued"][-1]
        stale_record = stale_write["writes"][-1] if stale_write["writes"] else None
        if (
            stale_record is not None
            and (
                stale_record["token"] != first_issued["token"]
                or first_issued["worker"] != first_assignment["owner"]
                or first_issued["worker"] == reassignment["owner"]
            )
        ):
            raise ReplayError("stale write token was not issued to the earlier, now-stale worker")
        if not _is_stale_write_transition(reassignment, stale_write):
            raise ReplayError("trace state 4 is not the expected accepted stale write in the mutant")
        if all(record["token"] == record["current"] for record in stale_write["writes"]):
            raise ReplayError("selected trace does not violate NoStaleWrites")
        if first_assignment["owner"] == reassignment["owner"]:
            raise ReplayError("the pilot requires reassignment to a different model worker")
    elif case_id == "rejected-write":
        if len(parsed_states) < 2:
            raise ReplayError("rejected-write receipt requires at least 2 states")
    return raw_states, parsed_states


def parse_receipt(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    receipt_data, _ = _load_json_bytes(path)
    return _validate_trace(receipt_data)


def _is_assignment_transition(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if after["generation"] != before["generation"] + 1:
        return False
    if after["assigned"] is not True or after["owner"] == "noWorker":
        return False
    if after["issued"] != before["issued"] + [
        {"token": after["generation"], "worker": after["owner"]}
    ]:
        return False
    return (
        after["writes"] == before["writes"]
        and after["attempts"] == before["attempts"]
        and after["steps"] == before["steps"] + 1
    )


def _is_stale_write_transition(before: dict[str, Any], after: dict[str, Any]) -> bool:
    if after["generation"] != before["generation"] or after["assigned"] is not True:
        return False
    if after["owner"] != before["owner"] or after["issued"] != before["issued"]:
        return False
    if len(after["attempts"]) != len(before["attempts"]) + 1:
        return False
    if after["attempts"][:-1] != before["attempts"] or after["attempts"][-1] is not True:
        return False
    if len(after["writes"]) != len(before["writes"]) + 1:
        return False
    stale = after["writes"][-1]
    if stale["token"] == stale["current"] or stale["current"] != after["generation"]:
        return False
    issued = next((item for item in before["issued"] if item["token"] == stale["token"]), None)
    if issued is None or issued["worker"] == after["owner"]:
        return False
    return after["steps"] == before["steps"] + 1


def _implementation_refs() -> tuple[str, list[dict[str, Any]]]:
    source_path = Path(program_state.__file__).resolve()
    source_bytes = source_path.read_bytes()
    references: list[dict[str, Any]] = []
    for name in ("assign_unit", "set_head", "require_current_assignment"):
        source_lines, start = inspect.getsourcelines(getattr(program_state, name))
        references.append(
            {
                "path": IMPLEMENTATION_RELATIVE,
                "symbol": f"program_state.{name}()",
                "start_line": start,
                "end_line": start + len(source_lines) - 1,
            }
        )
    return sha256_bytes(source_bytes), references


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _runtime_replay(parsed_states: list[dict[str, Any]]) -> dict[str, Any]:
    initial, first_assignment, reassignment, stale_write = parsed_states
    first_worker = first_assignment["owner"]
    current_worker = reassignment["owner"]
    stale_token = first_assignment["issued"][-1]["token"]
    stale_generation = stale_write["writes"][-1]["token"]
    current_generation = reassignment["generation"]
    if stale_token != stale_generation:
        raise ReplayError("stale write token and modeled assignment generation do not match")
    source_digest, source_refs = _implementation_refs()

    with tempfile.TemporaryDirectory(prefix="patpat-assignment-replay-") as raw_root:
        root = Path(raw_root).resolve()
        _git(root, "init", "-q")
        _git(root, "config", "user.name", "Patpat Replay")
        _git(root, "config", "user.email", "patpat-replay@example.invalid")
        (root / "marker.txt").write_text("isolated replay\n", encoding="utf-8")
        _git(root, "add", "marker.txt")
        _git(root, "commit", "-qm", "initialize replay repository")
        head_sha = _git(root, "rev-parse", "HEAD")

        plan = program_state.example_plan()
        plan["delivery"] = {"authority": "none", "actions": []}
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        program_id = "assignment-replay"
        state = program_state.initialize(root, program_id, plan_path)

        evidence_path = root / "parallel-gate-evidence.txt"
        evidence_path.write_text("temporary evidence for isolated replay\n", encoding="utf-8")
        evidence = program_state.bind_parallel_gate_evidence(evidence_path)
        gate_receipt = {
            "schema_version": 2,
            "kind": program_state.PARALLEL_GATE_KIND,
            "program_id": program_id,
            "plan_digest": state["plan_digest"],
            "integration_owner": "replay-coordinator",
            "checks": {name: True for name in program_state.PARALLEL_GATE_CHECKS},
            "supporting_evidence": {
                name: [dict(evidence)] for name in program_state.PARALLEL_GATE_CHECKS
            },
            "isolation_identities": {
                "contract": "assignment-replay-worker",
                "consumer": "assignment-replay-consumer",
            },
        }
        gate_receipt_path = root / "parallel-gate.json"
        gate_receipt_path.write_text(json.dumps(gate_receipt), encoding="utf-8")
        program_state.set_gate(
            root,
            program_id,
            "dispatch",
            True,
            "open isolated replay dispatch",
            gate_receipt_path,
            "replay-coordinator",
        )

        first_assignment_result = program_state.assign_unit(
            root,
            program_id,
            "contract",
            first_worker,
            "assignment-replay-worker",
            initial["generation"],
        )
        reassignment_result = program_state.assign_unit(
            root,
            program_id,
            "contract",
            current_worker,
            "assignment-replay-worker",
            first_assignment["generation"],
        )
        first_observed = first_assignment_result["units"]["contract"]["assignment"]
        current_observed = reassignment_result["units"]["contract"]["assignment"]
        assignment_prefix_matches_model = (
            first_observed["generation"] == first_assignment["generation"]
            and first_observed["actor"] == first_worker.casefold()
            and current_observed["generation"] == reassignment["generation"]
            and current_observed["actor"] == current_worker.casefold()
        )

        persisted_state = program_state.state_path(root, program_id)
        state_before = persisted_state.read_bytes()
        digest_before = sha256_bytes(state_before)
        observed_error: str | None = None
        try:
            program_state.set_head(
                root,
                program_id,
                "contract",
                head_sha,
                None,
                stale_generation,
            )
        except program_state.ProgramStateError as error:
            observed_error = str(error)
        state_after = persisted_state.read_bytes()
        digest_after = sha256_bytes(state_after)
        unchanged = state_before == state_after
        expected_rejection = (
            assignment_prefix_matches_model
            and observed_error == "stale assignment generation"
            and unchanged
        )

        return {
            "status": "pass" if expected_rejection else "fail",
            "outcome": (
                "rejected-as-expected"
                if expected_rejection
                else "assignment-prefix-diverged"
                if not assignment_prefix_matches_model
                else "unexpected-rejection" if observed_error is not None else "accepted-stale-write"
            ),
            "entrypoint": "program_state.set_head()",
            "attempted_model_worker": first_worker,
            "attempted_token": stale_token,
            "attempted_generation": stale_generation,
            "current_assignment": {
                "worker": current_worker,
                "generation": current_generation,
            },
            "mapped_calls": [
                {
                    "model_transition": 2,
                    "entrypoint": "program_state.assign_unit()",
                    "worker_label_from_model_state": first_worker,
                    "expected_generation": initial["generation"],
                    "observed_generation": first_assignment_result["units"]["contract"]["assignment"]["generation"],
                },
                {
                    "model_transition": 3,
                    "entrypoint": "program_state.assign_unit()",
                    "worker_label_from_model_state": current_worker,
                    "expected_generation": first_assignment["generation"],
                    "observed_generation": reassignment_result["units"]["contract"]["assignment"]["generation"],
                },
                {
                    "model_transition": 4,
                    "entrypoint": "program_state.set_head()",
                    "worker_label_from_model_state": first_worker,
                    "stale_generation": stale_generation,
                    "current_generation": current_generation,
                },
            ],
            "observed_error": observed_error,
            "assignment_prefix_matches_model": assignment_prefix_matches_model,
            "state_sha256_before": digest_before,
            "state_sha256_after": digest_after,
            "persisted_state_unchanged": unchanged,
            "actor_authentication": "not-exercised; set_head() accepts a generation but no worker identity",
            "temporary_workspace": "isolated Git and program state; removed when replay returns",
            "implementation_source": {
                "path": IMPLEMENTATION_RELATIVE,
                "sha256": source_digest,
                "references": source_refs,
            },
        }


def replay_receipt(receipt_path: Path) -> dict[str, Any]:
    receipt, receipt_bytes = _load_json_bytes(receipt_path)
    model_ref = receipt.get("model")
    config_ref = receipt.get("configuration")
    if not isinstance(model_ref, dict) or model_ref.get("path") != MODEL_RELATIVE:
        raise ReplayError("receipt does not identify the supported AssignmentGeneration model")
    model_path = REPOSITORY_ROOT / MODEL_RELATIVE
    if not model_path.is_file() or sha256_bytes(model_path.read_bytes()) != model_ref.get("sha256"):
        raise ReplayError("receipt model digest does not match the current model source")
    if not isinstance(config_ref, dict) or config_ref.get("path") != CONFIG_RELATIVE:
        raise ReplayError("receipt does not identify the supported mutant configuration")
    config_path = REPOSITORY_ROOT / CONFIG_RELATIVE
    if not config_path.is_file() or sha256_bytes(config_path.read_bytes()) != config_ref.get("sha256"):
        raise ReplayError("receipt configuration digest does not match the current configuration")

    checker = receipt.get("checker")
    if not isinstance(checker, dict) or checker.get("name") != "TLC":
        raise ReplayError("receipt checker identity is missing or is not TLC")

    raw_trace, parsed_states = _validate_trace(receipt)
    prop = next(item for item in receipt["properties"] if item["name"] == "NoStaleWrites")
    replay = _runtime_replay(parsed_states)
    return {
        "kind": REPLAY_KIND,
        "schema_version": REPLAY_SCHEMA_VERSION,
        "evidence_layers": {
            "bounded_model_tlc": {
                "status": "counterexample",
                "model_path": MODEL_RELATIVE,
                "model_sha256": model_ref["sha256"],
                "receipt_sha256": sha256_bytes(receipt_bytes),
                "mutant": EXPECTED_MUTANT,
                "property": "NoStaleWrites",
                "counterexample_count": prop["counterexample_count"],
                "bounds": EXPECTED_BOUNDS,
                "selected_trace_states": len(raw_trace),
                "raw_tlc_actions": [step["action"] for step in raw_trace],
                "selected_trace": raw_trace,
                "model_action_interpretation": [
                    {
                        "transition": 2,
                        "interpretation": f"Assign({parsed_states[1]['owner']})",
                        "basis": "validated state delta; not emitted as TLC action text",
                    },
                    {
                        "transition": 3,
                        "interpretation": f"Assign({parsed_states[2]['owner']})",
                        "basis": "validated state delta; not emitted as TLC action text",
                    },
                    {
                        "transition": 4,
                        "interpretation": (
                            f"AcceptedWrite(token={parsed_states[3]['writes'][-1]['token']}, "
                            f"worker={parsed_states[1]['owner']}) in the mutant model"
                        ),
                        "basis": (
                            "validated stale token issuance plus the model WriteAllowed relation; "
                            "the worker argument is not serialized in TLC variables"
                        ),
                    },
                ],
            },
            "implementation_replay": replay,
        },
        "interpretation": (
            "The counterexample is produced by a model mutant. The Python replay checks the mapped stale-write path; "
            "a rejection is evidence that this selected mutant path was not reproduced as a Python defect."
        ),
    }


def serialize_report(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_report(path: Path, report: dict[str, Any]) -> Path:
    destination = path.expanduser().absolute()
    if not destination.parent.is_dir():
        raise FileNotFoundError(f"report parent directory does not exist: {destination.parent}")
    payload = serialize_report(report).encode("utf-8")
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            destination.unlink()
        except OSError:
            pass
        raise
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True, help="saved stale-generation TLC receipt JSON")
    parser.add_argument("--out", type=Path, help="write a JSON replay receipt to a new file; refuses overwrite")
    args = parser.parse_args(argv)
    try:
        report = replay_receipt(args.receipt)
        if args.out is not None:
            written = write_report(args.out, report)
            print(f"Replay receipt written: {written}")
        else:
            print(serialize_report(report), end="")
        return 0 if report["evidence_layers"]["implementation_replay"]["status"] == "pass" else 1
    except (OSError, ReplayError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"replay error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
