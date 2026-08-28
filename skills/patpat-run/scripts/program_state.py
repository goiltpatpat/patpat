#!/usr/bin/env python3
"""Maintain a locked, head-bound Patpat program coordination store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from validate_plan import ACTIONS, AUTHORITIES, example_plan, validate_plan


SCHEMA_VERSION = 1
PROGRAM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEAD_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
UNIT_STATES = {"pending", "running", "completed", "blocked"}
VERDICT_KINDS = {"verification", "review"}
VERDICTS = {"pass", "fail"}
GATE_NAMES = {"dispatch", "delivery"}
PROGRAM_KEYS = {
    "schema_version",
    "program_id",
    "repo_root",
    "objective",
    "plan_digest",
    "delivery",
    "gates",
    "units",
    "inbox",
    "inbox_sequence",
    "created_at",
    "updated_at",
}
UNIT_KEYS = {
    "id",
    "depends_on",
    "files",
    "state",
    "head_sha",
    "verification",
    "review",
    "updated_at",
}
GATE_KEYS = {"open", "reason", "updated_at"}
VERDICT_KEYS = {"actor", "verdict", "head_sha", "evidence", "recorded_at"}
EVIDENCE_KEYS = {"path", "sha256", "size"}
INBOX_KEYS = {"sequence", "kind", "unit_id", "summary", "head_sha", "recorded_at"}


class ProgramStateError(ValueError):
    """Raised when a program operation violates the store contract."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def git_text(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise ProgramStateError(f"git is required for program state: {error}") from error
    if result.returncode != 0:
        return None
    value = os.fsdecode(result.stdout).strip()
    return value or None


def git_commit_exists(root: Path, head_sha: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", f"{head_sha}^{{commit}}"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise ProgramStateError(f"git is required for exact-head evidence: {error}") from error
    return result.returncode == 0


def require_git_root(root: Path) -> Path:
    root = root.resolve()
    top = git_text(root, "rev-parse", "--show-toplevel")
    head = git_text(root, "rev-parse", "HEAD")
    if not top or not head:
        raise ProgramStateError("program state requires a Git worktree with at least one commit")
    if Path(top).resolve() != root:
        raise ProgramStateError(f"--root must be the Git worktree root: {Path(top).resolve()}")
    return root


def store_root(root: Path) -> Path:
    root = require_git_root(root)
    raw = git_text(root, "rev-parse", "--git-path", "patpat/programs")
    if not raw:
        raise ProgramStateError("Git did not return a Patpat program metadata path")
    candidate = Path(raw)
    return (candidate if candidate.is_absolute() else root / candidate).resolve()


def checked_program_id(program_id: str) -> str:
    if len(program_id) > 64 or PROGRAM_ID.fullmatch(program_id) is None:
        raise ProgramStateError("program id must be lowercase kebab-case and at most 64 characters")
    return program_id


def program_directory(root: Path, program_id: str) -> Path:
    path = store_root(root) / checked_program_id(program_id)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ProgramStateError("program store path must be a real directory without symlinks")
    return path


def state_path(root: Path, program_id: str) -> Path:
    return program_directory(root, program_id) / "state.json"


def fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def program_lock(root: Path, program_id: str) -> Iterator[None]:
    directory = program_directory(root, program_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise ProgramStateError(f"program is locked; inspect its owner before recovery: {path}") from error
    try:
        record = {"pid": os.getpid(), "host": socket.gethostname(), "created_at": now()}
        os.write(descriptor, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
        os.fsync(descriptor)
        os.close(descriptor)
        yield
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def canonical_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProgramStateError(f"{label} must be a non-empty identity without outer whitespace")
    if unicodedata.normalize("NFKC", value) != value:
        raise ProgramStateError(f"{label} must use canonical Unicode form")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ProgramStateError(f"{label} must not contain control characters")
    return value.casefold()


def checked_head(head_sha: str) -> str:
    if HEAD_SHA.fullmatch(head_sha) is None:
        raise ProgramStateError("head SHA must be 40 or 64 lowercase hexadecimal characters")
    return head_sha


def checked_commit(root: Path, head_sha: str) -> str:
    head_sha = checked_head(head_sha)
    if not git_commit_exists(root, head_sha):
        raise ProgramStateError("head SHA must identify a commit present in the repository")
    return head_sha


def checked_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProgramStateError(f"{label} must be a non-empty string without outer whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ProgramStateError(f"{label} must not contain control characters")
    return value


def evidence_binding(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path != path.resolve() or not path.is_file() or path.is_symlink():
        raise ProgramStateError("evidence must be an existing absolute regular file without symlinks")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    stat = path.stat()
    return {"path": str(path), "sha256": digest.hexdigest(), "size": stat.st_size}


def evidence_is_fresh(binding: Any) -> bool:
    if not isinstance(binding, dict) or set(binding) != EVIDENCE_KEYS:
        return False
    try:
        return evidence_binding(Path(binding["path"])) == binding
    except (KeyError, OSError, ProgramStateError, TypeError):
        return False


def canonical_json_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ProgramStateError("plan must be an existing regular file without symlinks")
    path = path.resolve()
    if not path.is_file():
        raise ProgramStateError("plan must be an existing regular file without symlinks")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProgramStateError(f"could not read plan: {error}") from error
    errors = validate_plan(value)
    if errors:
        raise ProgramStateError("plan is invalid: " + "; ".join(errors))
    return value


def verdict_is_fresh(root: Path, unit: dict[str, Any], kind: str) -> bool:
    record = unit.get(kind)
    return (
        isinstance(record, dict)
        and set(record) == VERDICT_KEYS
        and record.get("verdict") == "pass"
        and record.get("head_sha") == unit.get("head_sha")
        and isinstance(unit.get("head_sha"), str)
        and git_commit_exists(root, unit["head_sha"])
        and evidence_is_fresh(record.get("evidence"))
    )


def unit_is_complete(root: Path, unit: dict[str, Any]) -> bool:
    return (
        unit.get("state") == "completed"
        and verdict_is_fresh(root, unit, "verification")
        and verdict_is_fresh(root, unit, "review")
    )


def dependencies_complete(root: Path, state: dict[str, Any], unit: dict[str, Any]) -> bool:
    return all(
        unit_is_complete(root, state["units"][dependency])
        for dependency in unit["depends_on"]
    )


def frontier(root: Path, state: dict[str, Any]) -> list[str]:
    if not state["gates"]["dispatch"]["open"]:
        return []
    return sorted(
        unit_id
        for unit_id, unit in state["units"].items()
        if unit["state"] == "pending" and dependencies_complete(root, state, unit)
    )


def delivery_ready(root: Path, state: dict[str, Any]) -> bool:
    return bool(state["units"]) and all(
        unit_is_complete(root, unit) for unit in state["units"].values()
    )


def dependent_units(state: dict[str, Any], changed_unit: str) -> set[str]:
    affected: set[str] = set()
    pending = [changed_unit]
    while pending:
        dependency = pending.pop()
        for unit_id, unit in state["units"].items():
            if unit_id not in affected and dependency in unit["depends_on"]:
                affected.add(unit_id)
                pending.append(unit_id)
    return affected


def schema_errors(state: Any, root: Path, program_id: str) -> list[str]:
    if not isinstance(state, dict):
        return ["state root must be an object"]
    errors: list[str] = []
    if set(state) != PROGRAM_KEYS:
        errors.append("state fields do not match schema")
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema version")
    if state.get("program_id") != program_id:
        errors.append("stored program id does not match requested program")
    if state.get("repo_root") != str(root.resolve()):
        errors.append("stored repository root does not match requested root")
    if not isinstance(state.get("objective"), str) or not state.get("objective"):
        errors.append("objective is required")
    if not isinstance(state.get("plan_digest"), str) or re.fullmatch(r"[0-9a-f]{64}", state.get("plan_digest", "")) is None:
        errors.append("plan digest is invalid")
    delivery = state.get("delivery")
    if not isinstance(delivery, dict) or set(delivery) != {"authority", "actions"}:
        errors.append("delivery claim is malformed")
    elif (
        delivery.get("authority") not in AUTHORITIES
        or not isinstance(delivery.get("actions"), list)
        or not all(isinstance(action, str) for action in delivery["actions"])
        or len(delivery["actions"]) != len(set(delivery["actions"]))
        or not set(delivery["actions"]) <= ACTIONS
    ):
        errors.append("delivery claim values are invalid")
    else:
        authority = delivery["authority"]
        actions = delivery["actions"]
        if authority == "none" and actions:
            errors.append("delivery authority none requires no actions")
        if authority != "none" and not actions:
            errors.append("delivery authority must name at least one action")
        if "merge" in actions and authority != "explicit-merge":
            errors.append("merge requires explicit-merge authority")
        if authority == "explicit-merge" and "merge" not in actions:
            errors.append("explicit-merge authority must name merge")
        if "create-or-update-ready-pr" in actions and "non-force-push" not in actions:
            errors.append("pull-request delivery requires non-force-push")
    gates = state.get("gates")
    if not isinstance(gates, dict) or set(gates) != GATE_NAMES:
        errors.append("gates are malformed")
    else:
        for name, gate in gates.items():
            if not isinstance(gate, dict) or set(gate) != GATE_KEYS:
                errors.append(f"gate {name} is malformed")
            elif (
                not isinstance(gate.get("open"), bool)
                or not isinstance(gate.get("reason"), str)
                or not gate["reason"]
            ):
                errors.append(f"gate {name} fields are invalid")
    units = state.get("units")
    if not isinstance(units, dict) or not units:
        errors.append("units must be a non-empty object")
    else:
        known = set(units)
        for unit_id, unit in units.items():
            if PROGRAM_ID.fullmatch(unit_id) is None or not isinstance(unit, dict) or set(unit) != UNIT_KEYS:
                errors.append(f"unit {unit_id!r} is malformed")
                continue
            if unit.get("id") != unit_id or unit.get("state") not in UNIT_STATES:
                errors.append(f"unit {unit_id} identity or state is invalid")
            dependencies = unit.get("depends_on")
            if not isinstance(dependencies, list) or len(dependencies) != len(set(dependencies)) or not set(dependencies) <= known:
                errors.append(f"unit {unit_id} dependencies are invalid")
            elif unit_id in dependencies:
                errors.append(f"unit {unit_id} cannot depend on itself")
            if (
                not isinstance(unit.get("files"), list)
                or not unit["files"]
                or not all(isinstance(item, str) and item for item in unit["files"])
            ):
                errors.append(f"unit {unit_id} files are invalid")
            head = unit.get("head_sha")
            if head is not None and (not isinstance(head, str) or HEAD_SHA.fullmatch(head) is None):
                errors.append(f"unit {unit_id} head SHA is invalid")
            for kind in VERDICT_KINDS:
                record = unit.get(kind)
                if record is not None and (not isinstance(record, dict) or set(record) != VERDICT_KEYS):
                    errors.append(f"unit {unit_id} {kind} record is malformed")
                elif isinstance(record, dict):
                    try:
                        canonical_identity(record.get("actor"), f"unit {unit_id} {kind} actor")
                    except ProgramStateError:
                        errors.append(f"unit {unit_id} {kind} actor is invalid")
                    if record.get("verdict") not in VERDICTS:
                        errors.append(f"unit {unit_id} {kind} verdict is invalid")
                    if not isinstance(record.get("head_sha"), str) or HEAD_SHA.fullmatch(record["head_sha"]) is None:
                        errors.append(f"unit {unit_id} {kind} head SHA is invalid")
                    evidence = record.get("evidence")
                    if (
                        not isinstance(evidence, dict)
                        or set(evidence) != EVIDENCE_KEYS
                        or not isinstance(evidence.get("path"), str)
                        or not isinstance(evidence.get("sha256"), str)
                        or re.fullmatch(r"[0-9a-f]{64}", evidence.get("sha256", "")) is None
                        or not isinstance(evidence.get("size"), int)
                        or evidence.get("size", -1) < 0
                    ):
                        errors.append(f"unit {unit_id} {kind} evidence binding is invalid")
        graph = {
            unit_id: unit["depends_on"]
            for unit_id, unit in units.items()
            if isinstance(unit, dict)
            and isinstance(unit.get("depends_on"), list)
            and set(unit["depends_on"]) <= known
        }
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
                visit(dependency)
            visiting.remove(unit_id)
            visited.add(unit_id)

        for unit_id in graph:
            visit(unit_id)
    inbox = state.get("inbox")
    if not isinstance(inbox, list) or not all(isinstance(event, dict) and set(event) == INBOX_KEYS for event in inbox):
        errors.append("inbox is malformed")
    elif isinstance(units, dict):
        observed_sequences: list[int] = []
        for event in inbox:
            sequence_value = event.get("sequence")
            if not isinstance(sequence_value, int) or sequence_value < 1:
                errors.append("inbox event sequence is invalid")
            else:
                observed_sequences.append(sequence_value)
            if not isinstance(event.get("kind"), str) or not event["kind"]:
                errors.append("inbox event kind is invalid")
            if not isinstance(event.get("summary"), str) or not event["summary"]:
                errors.append("inbox event summary is invalid")
            if event.get("unit_id") is not None and event["unit_id"] not in units:
                errors.append("inbox event unit is invalid")
            event_head = event.get("head_sha")
            if event_head is not None and (not isinstance(event_head, str) or HEAD_SHA.fullmatch(event_head) is None):
                errors.append("inbox event head SHA is invalid")
        if observed_sequences != sorted(set(observed_sequences)):
            errors.append("inbox event sequence order is invalid")
    sequence = state.get("inbox_sequence")
    if not isinstance(sequence, int) or sequence < 0:
        errors.append("inbox sequence is invalid")
    elif isinstance(inbox, list) and inbox and any(event.get("sequence", 0) > sequence for event in inbox if isinstance(event, dict)):
        errors.append("inbox event sequence exceeds store sequence")
    return errors


def load_state(root: Path, program_id: str) -> dict[str, Any]:
    path = state_path(root, program_id)
    if not path.is_file() or path.is_symlink():
        raise ProgramStateError(f"program does not exist as a regular state file: {program_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProgramStateError(f"invalid state file: {error}") from error
    errors = schema_errors(value, root, program_id)
    if errors:
        raise ProgramStateError("; ".join(errors))
    return value


def save_state(root: Path, program_id: str, state: dict[str, Any]) -> None:
    errors = schema_errors(state, root, program_id)
    if errors:
        raise ProgramStateError("; ".join(errors))
    try:
        atomic_write_json(state_path(root, program_id), state)
    except OSError as error:
        raise ProgramStateError(f"could not persist atomic program state: {error}") from error


def initialize(root: Path, program_id: str, plan_path: Path) -> dict[str, Any]:
    plan = read_plan(plan_path)
    with program_lock(root, program_id):
        path = state_path(root, program_id)
        if path.exists():
            raise ProgramStateError(f"program already exists: {program_id}")
        timestamp = now()
        units = {
            unit["id"]: {
                "id": unit["id"],
                "depends_on": list(unit["depends_on"]),
                "files": list(unit["files"]),
                "state": "pending",
                "head_sha": None,
                "verification": None,
                "review": None,
                "updated_at": timestamp,
            }
            for unit in plan["units"]
        }
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "program_id": program_id,
            "repo_root": str(root.resolve()),
            "objective": plan["objective"],
            "plan_digest": canonical_json_digest(plan),
            "delivery": plan["delivery"],
            "gates": {
                "dispatch": {"open": False, "reason": "requires explicit coordinator decision", "updated_at": timestamp},
                "delivery": {"open": False, "reason": "requires complete fresh evidence", "updated_at": timestamp},
            },
            "units": units,
            "inbox": [],
            "inbox_sequence": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        save_state(root, program_id, state)
        return state


def set_gate(root: Path, program_id: str, name: str, opened: bool, reason: str) -> dict[str, Any]:
    if name not in GATE_NAMES:
        raise ProgramStateError(f"gate must be one of {sorted(GATE_NAMES)}")
    reason = checked_text(reason, "gate reason")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if opened and name == "delivery" and not delivery_ready(root, state):
            raise ProgramStateError("delivery gate requires every unit to have complete fresh evidence")
        timestamp = now()
        state["gates"][name] = {"open": opened, "reason": reason, "updated_at": timestamp}
        state["updated_at"] = timestamp
        save_state(root, program_id, state)
        return state


def set_head(root: Path, program_id: str, unit_id: str, head_sha: str) -> dict[str, Any]:
    head_sha = checked_commit(root, head_sha)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        if unit["head_sha"] != head_sha:
            timestamp = now()
            unit["head_sha"] = head_sha
            if unit["state"] == "completed":
                unit["state"] = "running"
            for dependent_id in dependent_units(state, unit_id):
                dependent = state["units"][dependent_id]
                dependent["verification"] = None
                dependent["review"] = None
                if dependent["state"] == "completed":
                    dependent["state"] = "running"
                dependent["updated_at"] = timestamp
            state["gates"]["delivery"] = {
                "open": False,
                "reason": f"unit {unit_id} head changed",
                "updated_at": timestamp,
            }
        unit["updated_at"] = now()
        state["updated_at"] = unit["updated_at"]
        save_state(root, program_id, state)
        return state


def record_verdict(
    root: Path,
    program_id: str,
    unit_id: str,
    kind: str,
    verdict: str,
    head_sha: str,
    actor: str,
    evidence_path: Path,
) -> dict[str, Any]:
    if kind not in VERDICT_KINDS or verdict not in VERDICTS:
        raise ProgramStateError("verdict kind or value is invalid")
    actor_key = canonical_identity(actor, "verdict actor")
    head_sha = checked_commit(root, head_sha)
    binding = evidence_binding(evidence_path)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        if unit["head_sha"] != head_sha:
            raise ProgramStateError("verdict head does not match the unit head")
        if kind == "review" and unit["verification"] is not None:
            verifier_key = canonical_identity(unit["verification"]["actor"], "verification actor")
            if actor_key == verifier_key:
                raise ProgramStateError("review actor must differ from the verification actor")
        timestamp = now()
        unit[kind] = {
            "actor": actor,
            "verdict": verdict,
            "head_sha": head_sha,
            "evidence": binding,
            "recorded_at": timestamp,
        }
        if kind == "verification":
            unit["review"] = None
        if verdict == "fail" and unit["state"] == "completed":
            unit["state"] = "running"
        state["gates"]["delivery"] = {
            "open": False,
            "reason": f"unit {unit_id} evidence changed",
            "updated_at": timestamp,
        }
        unit["updated_at"] = timestamp
        state["updated_at"] = timestamp
        save_state(root, program_id, state)
        return state


def set_unit_state(root: Path, program_id: str, unit_id: str, destination: str) -> dict[str, Any]:
    if destination not in UNIT_STATES:
        raise ProgramStateError(f"unit state must be one of {sorted(UNIT_STATES)}")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        transitions = {
            "pending": {"running", "blocked"},
            "running": {"pending", "completed", "blocked"},
            "blocked": {"pending"},
            "completed": {"running"},
        }
        if destination not in transitions[unit["state"]]:
            raise ProgramStateError(f"illegal unit transition: {unit['state']} -> {destination}")
        if destination == "running" and unit["state"] == "pending" and unit_id not in frontier(root, state):
            raise ProgramStateError("unit is not in the open dependency frontier")
        if destination == "completed":
            if not dependencies_complete(root, state, unit):
                raise ProgramStateError("unit dependencies are not complete with fresh evidence")
            if not verdict_is_fresh(root, unit, "verification") or not verdict_is_fresh(root, unit, "review"):
                raise ProgramStateError("unit completion requires fresh verification and independent review passes")
        timestamp = now()
        unit["state"] = destination
        unit["updated_at"] = timestamp
        state["gates"]["delivery"] = {
            "open": False,
            "reason": f"unit {unit_id} state changed",
            "updated_at": timestamp,
        }
        state["updated_at"] = timestamp
        save_state(root, program_id, state)
        return state


def append_inbox(
    root: Path,
    program_id: str,
    kind: str,
    summary: str,
    unit_id: str | None,
    head_sha: str | None,
) -> dict[str, Any]:
    kind = checked_text(kind, "event kind")
    summary = checked_text(summary, "event summary")
    if head_sha is not None:
        head_sha = checked_head(head_sha)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id is not None and unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        sequence = state["inbox_sequence"] + 1
        event = {
            "sequence": sequence,
            "kind": kind,
            "unit_id": unit_id,
            "summary": summary,
            "head_sha": head_sha,
            "recorded_at": now(),
        }
        state["inbox"].append(event)
        state["inbox_sequence"] = sequence
        state["updated_at"] = event["recorded_at"]
        save_state(root, program_id, state)
        return event


def peek_inbox(root: Path, program_id: str) -> list[dict[str, Any]]:
    return list(load_state(root, program_id)["inbox"])


def acknowledge_inbox(root: Path, program_id: str, through_sequence: int) -> dict[str, int]:
    if isinstance(through_sequence, bool) or not isinstance(through_sequence, int) or through_sequence < 1:
        raise ProgramStateError("acknowledgement sequence must be an integer >= 1")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if through_sequence > state["inbox_sequence"]:
            raise ProgramStateError("acknowledgement exceeds the last recorded inbox sequence")
        state["inbox"] = [
            event for event in state["inbox"]
            if event["sequence"] > through_sequence
        ]
        state["updated_at"] = now()
        save_state(root, program_id, state)
        return {
            "acknowledged_through": through_sequence,
            "remaining": len(state["inbox"]),
        }


def status(root: Path, program_id: str) -> dict[str, Any]:
    state = load_state(root, program_id)
    ready = delivery_ready(root, state)
    return {
        "store": str(program_directory(root, program_id)),
        "program_id": program_id,
        "objective": state["objective"],
        "plan_digest": state["plan_digest"],
        "gates": state["gates"],
        "frontier": frontier(root, state),
        "delivery_ready": ready,
        "delivery_admitted": state["gates"]["delivery"]["open"] and ready,
        "inbox_count": len(state["inbox"]),
        "units": {
            unit_id: {
                "state": unit["state"],
                "head_sha": unit["head_sha"],
                "head_present": (
                    isinstance(unit["head_sha"], str)
                    and git_commit_exists(root, unit["head_sha"])
                ),
                "dependencies_ready": dependencies_complete(root, state, unit),
                "verification_fresh": verdict_is_fresh(root, unit, "verification"),
                "review_fresh": verdict_is_fresh(root, unit, "review"),
            }
            for unit_id, unit in sorted(state["units"].items())
        },
    }


def expect_error(action: Any, expected: str) -> None:
    try:
        action()
    except ProgramStateError as error:
        if expected not in str(error):
            raise AssertionError(f"expected {expected!r} in {str(error)!r}") from error
    else:
        raise AssertionError(f"expected ProgramStateError containing {expected!r}")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="patpat-program-state-") as raw:
        root = Path(raw).resolve()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.name", "Patpat Test"], check=True)
        subprocess.run(["git", "-C", str(root), "config", "user.email", "patpat@example.invalid"], check=True)
        marker = root / "marker.txt"
        marker.write_text("initial\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "marker.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "initial"], check=True)

        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(example_plan()), encoding="utf-8")
        initialize(root, "release-train", plan_path)
        assert status(root, "release-train")["frontier"] == []
        expect_error(
            lambda: set_gate(root, "release-train", "delivery", True, "ship now"),
            "complete fresh evidence",
        )
        set_gate(root, "release-train", "dispatch", True, "plan reviewed")
        assert status(root, "release-train")["frontier"] == ["contract"]

        append_inbox(root, "release-train", "worker-update", "contract ready", "contract", None)
        append_inbox(root, "release-train", "ci", "checks queued", "contract", None)
        observed_inbox = peek_inbox(root, "release-train")
        assert [event["sequence"] for event in observed_inbox] == [1, 2]
        assert [event["sequence"] for event in peek_inbox(root, "release-train")] == [1, 2]
        assert acknowledge_inbox(root, "release-train", 1) == {
            "acknowledged_through": 1,
            "remaining": 1,
        }
        assert [event["sequence"] for event in peek_inbox(root, "release-train")] == [2]
        assert acknowledge_inbox(root, "release-train", 2) == {
            "acknowledged_through": 2,
            "remaining": 0,
        }
        assert acknowledge_inbox(root, "release-train", 2)["remaining"] == 0
        assert status(root, "release-train")["inbox_count"] == 0

        evidence = root / "evidence.txt"
        evidence.write_text("verified\n", encoding="utf-8")
        head_one = git_text(root, "rev-parse", "HEAD")
        assert head_one is not None
        set_unit_state(root, "release-train", "contract", "running")
        set_head(root, "release-train", "contract", head_one)
        record_verdict(root, "release-train", "contract", "verification", "pass", head_one, "Verifier", evidence)
        record_verdict(root, "release-train", "contract", "review", "pass", head_one, "Reviewer", evidence)
        set_unit_state(root, "release-train", "contract", "completed")
        assert status(root, "release-train")["frontier"] == ["consumer"]

        consumer_evidence = root / "consumer-evidence.txt"
        consumer_evidence.write_text("consumer verified\n", encoding="utf-8")
        consumer_head = head_one
        set_unit_state(root, "release-train", "consumer", "running")
        set_head(root, "release-train", "consumer", consumer_head)
        record_verdict(
            root, "release-train", "consumer", "verification", "pass",
            consumer_head, "Consumer Verifier", consumer_evidence,
        )
        record_verdict(
            root, "release-train", "consumer", "review", "pass",
            consumer_head, "Consumer Reviewer", consumer_evidence,
        )
        set_unit_state(root, "release-train", "consumer", "completed")
        set_gate(root, "release-train", "delivery", True, "all evidence is fresh")
        assert status(root, "release-train")["delivery_ready"]

        marker.write_text("changed dependency\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "marker.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "change dependency"], check=True)
        head_two = git_text(root, "rev-parse", "HEAD")
        assert head_two is not None
        set_head(root, "release-train", "contract", head_two)
        observed = status(root, "release-train")
        assert observed["units"]["contract"]["state"] == "running"
        assert not observed["units"]["contract"]["verification_fresh"]
        assert observed["units"]["consumer"]["state"] == "running"
        assert not observed["units"]["consumer"]["verification_fresh"]
        assert not observed["units"]["consumer"]["review_fresh"]
        assert not observed["delivery_ready"]
        assert observed["frontier"] == []

        tree = git_text(root, "write-tree")
        assert tree is not None
        orphan_result = subprocess.run(
            ["git", "-C", str(root), "commit-tree", tree],
            input=b"orphan evidence head\n",
            check=True,
            capture_output=True,
        )
        orphan_head = os.fsdecode(orphan_result.stdout).strip()
        set_head(root, "release-train", "contract", orphan_head)
        subprocess.run(
            ["git", "-C", str(root), "reflog", "expire", "--expire=now", "--all"],
            check=True,
        )
        subprocess.run(["git", "-C", str(root), "gc", "--prune=now"], check=True)
        assert not git_commit_exists(root, orphan_head)
        pruned = status(root, "release-train")
        assert not pruned["units"]["contract"]["head_present"]
        assert not pruned["delivery_ready"]
        assert not pruned["delivery_admitted"]
        set_head(root, "release-train", "contract", head_two)
        assert status(root, "release-train")["units"]["contract"]["head_present"]

        directory = program_directory(root, "release-train")
        lock = directory / ".lock"
        lock.write_text("occupied\n", encoding="utf-8")
        expect_error(lambda: append_inbox(root, "release-train", "note", "blocked", None, None), "locked")
        lock.unlink()

        stored_path = state_path(root, "release-train")
        valid_bytes = stored_path.read_bytes()
        stored_path.write_text('{"schema_version": 1}\n', encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "state fields")
        stored_path.write_bytes(valid_bytes)

        malformed = json.loads(valid_bytes)
        malformed["delivery"] = {
            "authority": "patpat-activation",
            "actions": ["merge"],
        }
        stored_path.write_text(json.dumps(malformed), encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "explicit-merge")
        stored_path.write_bytes(valid_bytes)

        malformed = json.loads(valid_bytes)
        malformed["units"]["contract"]["depends_on"] = ["consumer"]
        stored_path.write_text(json.dumps(malformed), encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "acyclic")
        stored_path.write_bytes(valid_bytes)
        expect_error(lambda: status(root, "../escape"), "program id")
        expect_error(
            lambda: set_head(root, "release-train", "contract", "f" * 40),
            "commit present",
        )
        invalid_plan = root / "invalid-plan.json"
        invalid_plan.write_text("{}\n", encoding="utf-8")
        expect_error(lambda: initialize(root, "invalid-plan", invalid_plan), "plan is invalid")
        plan_link = root / "plan-link.json"
        plan_link.symlink_to(plan_path)
        expect_error(lambda: initialize(root, "linked-plan", plan_link), "without symlinks")

        escaped_store = store_root(root) / "linked-store"
        escaped_store.symlink_to(root)
        expect_error(lambda: status(root, "linked-store"), "without symlinks")

    print("Patpat program state self-test passed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--program")
    parser.add_argument("--self-test", action="store_true")
    commands = parser.add_subparsers(dest="command")

    initialize_parser = commands.add_parser("init")
    initialize_parser.add_argument("--plan", type=Path, required=True)

    commands.add_parser("status")
    commands.add_parser("validate")

    gate_parser = commands.add_parser("set-gate")
    gate_parser.add_argument("name", choices=sorted(GATE_NAMES))
    gate_parser.add_argument("state", choices=["open", "closed"])
    gate_parser.add_argument("--reason", required=True)

    head_parser = commands.add_parser("set-head")
    head_parser.add_argument("unit_id")
    head_parser.add_argument("head_sha")

    unit_parser = commands.add_parser("set-unit")
    unit_parser.add_argument("unit_id")
    unit_parser.add_argument("state", choices=sorted(UNIT_STATES))

    verdict_parser = commands.add_parser("record-verdict")
    verdict_parser.add_argument("unit_id")
    verdict_parser.add_argument("kind", choices=sorted(VERDICT_KINDS))
    verdict_parser.add_argument("verdict", choices=sorted(VERDICTS))
    verdict_parser.add_argument("head_sha")
    verdict_parser.add_argument("--actor", required=True)
    verdict_parser.add_argument("--evidence", type=Path, required=True)

    append_parser = commands.add_parser("inbox-append")
    append_parser.add_argument("--kind", required=True)
    append_parser.add_argument("--summary", required=True)
    append_parser.add_argument("--unit")
    append_parser.add_argument("--head")

    commands.add_parser("inbox-peek")
    acknowledge_parser = commands.add_parser("inbox-ack")
    acknowledge_parser.add_argument("--through", type=int, required=True)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return 0
    if not args.command or not args.program:
        parser.error("provide --program and a command, or --self-test")
    root = args.root.resolve()
    try:
        if args.command == "init":
            result: Any = initialize(root, args.program, args.plan)
        elif args.command == "status":
            result = status(root, args.program)
        elif args.command == "validate":
            result = {"valid": True, "program_id": load_state(root, args.program)["program_id"]}
        elif args.command == "set-gate":
            result = set_gate(root, args.program, args.name, args.state == "open", args.reason)
        elif args.command == "set-head":
            result = set_head(root, args.program, args.unit_id, args.head_sha)
        elif args.command == "set-unit":
            result = set_unit_state(root, args.program, args.unit_id, args.state)
        elif args.command == "record-verdict":
            result = record_verdict(
                root, args.program, args.unit_id, args.kind, args.verdict,
                args.head_sha, args.actor, args.evidence,
            )
        elif args.command == "inbox-append":
            result = append_inbox(root, args.program, args.kind, args.summary, args.unit, args.head)
        elif args.command == "inbox-peek":
            result = peek_inbox(root, args.program)
        elif args.command == "inbox-ack":
            result = acknowledge_inbox(root, args.program, args.through)
        else:
            parser.error(f"unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ProgramStateError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
