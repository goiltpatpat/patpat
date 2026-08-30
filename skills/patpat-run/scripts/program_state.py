#!/usr/bin/env python3
"""Maintain a locked, head-bound Patpat program coordination store."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIRECTORY = str(Path(__file__).resolve().parent)
if SCRIPT_DIRECTORY not in sys.path:
    sys.path.insert(0, SCRIPT_DIRECTORY)

from state_lock import (
    bounded_file_binding,
    path_guard,
    path_has_identity,
    process_is_alive,
    read_lock_record,
)
from team_shape import (
    PARALLEL_GATE_CHECKS,
    PARALLEL_GATE_KIND,
    TeamShapeError,
    load_parallel_gate_receipt,
    validate_parallel_gate_receipt,
)
from validate_plan import (
    ACTIONS,
    AUTHORITIES,
    MAX_DEPENDENCIES,
    MAX_FILES,
    MAX_OBJECTIVE_LENGTH,
    MAX_UNITS,
    PlanError,
    example_plan,
    load_json as load_plan_json,
    ownership_patterns_overlap,
    repository_pattern,
    validate_plan,
)


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
PROGRAM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEAD_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
LOCK_TOKEN = re.compile(r"^[0-9a-f]{32}$")
MAX_LOCK_BYTES = 4096
MAX_PROGRAM_STATE_BYTES = 4 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
MAX_INBOX_EVENTS = 4096
MAX_ASSIGNMENT_GENERATION = (1 << 63) - 1
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
    "dispatch_binding",
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
    "assignment",
    "updated_at",
}
GATE_KEYS = {"open", "reason", "updated_at"}
VERDICT_KEYS = {"actor", "verdict", "head_sha", "evidence", "assignment", "recorded_at"}
EVIDENCE_KEYS = {"path", "sha256", "size"}
INBOX_KEYS = {"sequence", "kind", "unit_id", "summary", "head_sha", "assignment", "recorded_at"}
ASSIGNMENT_KEYS = {"actor", "isolation_identity", "generation", "assigned_at"}
ASSIGNMENT_SNAPSHOT_KEYS = {"actor", "isolation_identity", "generation"}
DISPATCH_BINDING_KEYS = {"receipt_sha256", "integration_owner", "isolation_identities"}
LEGACY_PROGRAM_KEYS = PROGRAM_KEYS - {"dispatch_binding"}
LEGACY_UNIT_KEYS = UNIT_KEYS - {"assignment"}
LEGACY_VERDICT_KEYS = VERDICT_KEYS - {"assignment"}
LEGACY_INBOX_KEYS = INBOX_KEYS - {"assignment"}


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


def git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as error:
        raise ProgramStateError(f"git is required for dependency ancestry: {error}") from error
    if result.returncode not in {0, 1}:
        raise ProgramStateError("git could not evaluate dependency ancestry")
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
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_PROGRAM_STATE_BYTES:
        raise ProgramStateError("program state exceeds the byte limit")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
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
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    path = directory / ".lock"
    token = uuid.uuid4().hex
    with path_guard(directory, ProgramStateError):
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise ProgramStateError(f"program is locked; inspect its owner before recovery: {path}") from error
        record = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": now(),
            "token": token,
        }
        try:
            os.write(descriptor, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        except OSError as error:
            os.close(descriptor)
            path.unlink(missing_ok=True)
            fsync_directory(path.parent)
            raise ProgramStateError(f"could not create program lock: {error}") from error
        os.close(descriptor)
    try:
        yield
    finally:
        with path_guard(directory, ProgramStateError):
            current, identity = read_lock_record(path, MAX_LOCK_BYTES)
            if current is not None and current.get("token") == token and path_has_identity(path, identity):
                path.unlink()
                fsync_directory(path.parent)


def _inspect_lock_snapshot(
    root: Path,
    program_id: str,
) -> tuple[dict[str, Any], tuple[int, int] | None]:
    path = program_directory(root, program_id) / ".lock"
    if not path.exists():
        return {"path": str(path), "state": "absent", "recoverable": False}, None
    if not path.is_file() or path.is_symlink():
        return {"path": str(path), "state": "invalid", "recoverable": False}, None
    record, identity = read_lock_record(path, MAX_LOCK_BYTES)
    if record is None or identity is None:
        return {"path": str(path), "state": "invalid", "recoverable": False}, None
    if not isinstance(record, dict) or set(record) != {"pid", "host", "created_at", "token"}:
        return {"path": str(path), "state": "invalid", "recoverable": False}, identity
    pid = record.get("pid")
    host = record.get("host")
    created_at = record.get("created_at")
    token = record.get("token")
    if (
        not isinstance(pid, int)
        or pid <= 0
        or not isinstance(host, str)
        or len(host) > 255
        or not isinstance(created_at, str)
        or not 1 <= len(created_at) <= 64
        or not isinstance(token, str)
        or LOCK_TOKEN.fullmatch(token) is None
    ):
        return {"path": str(path), "state": "invalid", "recoverable": False}, identity
    if host != socket.gethostname():
        return {
            "path": str(path),
            "state": "other-host",
            "recoverable": False,
            "owner": record,
        }, identity
    alive = process_is_alive(pid)
    return {
        "path": str(path),
        "state": "live" if alive else "stale",
        "recoverable": not alive,
        "owner": record,
    }, identity


def _inspect_lock_unlocked(root: Path, program_id: str) -> dict[str, Any]:
    observation, _ = _inspect_lock_snapshot(root, program_id)
    return observation


def inspect_lock(root: Path, program_id: str) -> dict[str, Any]:
    directory = program_directory(root, program_id)
    with path_guard(directory, ProgramStateError):
        return _inspect_lock_unlocked(root, program_id)


def recover_stale_lock(root: Path, program_id: str) -> Path:
    directory = program_directory(root, program_id)
    with path_guard(directory, ProgramStateError):
        observation, identity = _inspect_lock_snapshot(root, program_id)
        if observation["state"] != "stale" or not observation["recoverable"]:
            raise ProgramStateError(f"program lock is not safely recoverable: {observation['state']}")
        path = Path(observation["path"])
        current_record, current_identity = read_lock_record(path, MAX_LOCK_BYTES)
        if (
            current_record != observation.get("owner")
            or current_identity != identity
            or not path_has_identity(path, identity)
        ):
            raise ProgramStateError("program lock identity changed during recovery")
        path.unlink()
        fsync_directory(path.parent)
        return path


def canonical_identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > 512
    ):
        raise ProgramStateError(f"{label} must be a bounded non-empty identity without outer whitespace")
    if unicodedata.normalize("NFKC", value) != value:
        raise ProgramStateError(f"{label} must use canonical Unicode form")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ProgramStateError(f"{label} must not contain control characters")
    return value.casefold()


def checked_generation(value: Any, label: str = "assignment generation") -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > MAX_ASSIGNMENT_GENERATION
    ):
        raise ProgramStateError(
            f"{label} must be an integer between 0 and {MAX_ASSIGNMENT_GENERATION}"
        )
    return value


def valid_timestamp(value: Any) -> bool:
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def empty_assignment(generation: int = 0) -> dict[str, Any]:
    return {
        "actor": None,
        "isolation_identity": None,
        "generation": checked_generation(generation),
        "assigned_at": None,
    }


def assignment_snapshot(unit: dict[str, Any]) -> dict[str, Any] | None:
    assignment = unit.get("assignment")
    if not isinstance(assignment, dict) or set(assignment) != ASSIGNMENT_KEYS:
        return None
    actor = assignment.get("actor")
    isolation_identity = assignment.get("isolation_identity")
    assigned_at = assignment.get("assigned_at")
    generation = assignment.get("generation")
    if (
        actor is None
        or isolation_identity is None
        or assigned_at is None
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 1
    ):
        return None
    return {
        "actor": actor,
        "isolation_identity": isolation_identity,
        "generation": generation,
    }


def require_current_assignment(
    state: dict[str, Any],
    unit: dict[str, Any],
    generation: Any,
    *,
    actor: str | None = None,
    isolation_identity: str | None = None,
) -> dict[str, Any]:
    if not state["gates"]["dispatch"]["open"] or state["dispatch_binding"] is None:
        raise ProgramStateError("worker mutation requires an open bound dispatch gate")
    expected_generation = checked_generation(generation)
    snapshot = assignment_snapshot(unit)
    if snapshot is None:
        raise ProgramStateError("unit requires a current assignment")
    if snapshot["generation"] != expected_generation:
        raise ProgramStateError("stale assignment generation")
    if actor is not None and snapshot["actor"] != canonical_identity(actor, "assignment actor"):
        raise ProgramStateError("assignment actor does not match the current assignment")
    if (
        isolation_identity is not None
        and snapshot["isolation_identity"]
        != canonical_identity(isolation_identity, "assignment isolation identity")
    ):
        raise ProgramStateError("assignment isolation identity does not match the current assignment")
    return snapshot


def checked_head(head_sha: str) -> str:
    if HEAD_SHA.fullmatch(head_sha) is None:
        raise ProgramStateError("head SHA must be 40 or 64 lowercase hexadecimal characters")
    return head_sha


def checked_commit(root: Path, head_sha: str) -> str:
    head_sha = checked_head(head_sha)
    if not git_commit_exists(root, head_sha):
        raise ProgramStateError("head SHA must identify a commit present in the repository")
    return head_sha


def checked_text(value: Any, label: str, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProgramStateError(f"{label} must be a non-empty string without outer whitespace")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise ProgramStateError(f"{label} must not contain control characters")
    if max_length is not None and len(value) > max_length:
        raise ProgramStateError(f"{label} must be at most {max_length} characters")
    return value


def evidence_binding(path: Path) -> dict[str, Any]:
    return bounded_file_binding(
        path,
        max_bytes=MAX_EVIDENCE_BYTES,
        error_type=ProgramStateError,
        label="evidence",
    )


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
    try:
        value = load_plan_json(path)
    except PlanError as error:
        raise ProgramStateError(f"could not read plan: {error}") from error
    errors = validate_plan(value)
    if errors:
        raise ProgramStateError("plan is invalid: " + "; ".join(errors))
    return value


def verdict_is_fresh(root: Path, unit: dict[str, Any], kind: str) -> bool:
    record = unit.get(kind)
    current_assignment = assignment_snapshot(unit)
    return (
        isinstance(record, dict)
        and set(record) == VERDICT_KEYS
        and current_assignment is not None
        and record.get("assignment") == current_assignment
        and record.get("verdict") == "pass"
        and record.get("head_sha") == unit.get("head_sha")
        and isinstance(unit.get("head_sha"), str)
        and git_commit_exists(root, unit["head_sha"])
        and evidence_is_fresh(record.get("evidence"))
    )


def head_includes_dependencies(
    root: Path,
    state: dict[str, Any],
    unit: dict[str, Any],
    head_sha: str,
) -> bool:
    return all(
        isinstance(state["units"][dependency].get("head_sha"), str)
        and git_commit_exists(root, state["units"][dependency]["head_sha"])
        and git_is_ancestor(root, state["units"][dependency]["head_sha"], head_sha)
        for dependency in unit["depends_on"]
    )


def unit_is_complete(root: Path, state: dict[str, Any], unit: dict[str, Any]) -> bool:
    return (
        unit.get("state") == "completed"
        and isinstance(unit.get("head_sha"), str)
        and head_includes_dependencies(root, state, unit, unit["head_sha"])
        and verdict_is_fresh(root, unit, "verification")
        and verdict_is_fresh(root, unit, "review")
    )


def dependencies_complete(root: Path, state: dict[str, Any], unit: dict[str, Any]) -> bool:
    return all(
        unit_is_complete(root, state, state["units"][dependency])
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
        unit_is_complete(root, state, unit) for unit in state["units"].values()
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


def schema_errors(
    state: Any,
    root: Path,
    program_id: str,
    allowed_versions: frozenset[int] = frozenset({SCHEMA_VERSION}),
) -> list[str]:
    if not isinstance(state, dict):
        return ["state root must be an object"]
    errors: list[str] = []
    version = state.get("schema_version")
    program_keys = PROGRAM_KEYS if version == SCHEMA_VERSION else LEGACY_PROGRAM_KEYS
    unit_keys = UNIT_KEYS if version == SCHEMA_VERSION else LEGACY_UNIT_KEYS
    verdict_keys = VERDICT_KEYS if version == SCHEMA_VERSION else LEGACY_VERDICT_KEYS
    inbox_keys = INBOX_KEYS if version == SCHEMA_VERSION else LEGACY_INBOX_KEYS
    if set(state) != program_keys:
        errors.append("state fields do not match schema")
    if isinstance(version, bool) or not isinstance(version, int) or version not in allowed_versions:
        errors.append("unsupported schema version")
    if state.get("program_id") != program_id:
        errors.append("stored program id does not match requested program")
    if state.get("repo_root") != str(root.resolve()):
        errors.append("stored repository root does not match requested root")
    if (
        not isinstance(state.get("objective"), str)
        or not state.get("objective")
        or len(state["objective"]) > MAX_OBJECTIVE_LENGTH
    ):
        errors.append("objective is required")
    if not isinstance(state.get("plan_digest"), str) or re.fullmatch(r"[0-9a-f]{64}", state.get("plan_digest", "")) is None:
        errors.append("plan digest is invalid")
    dispatch_binding = state.get("dispatch_binding") if version == SCHEMA_VERSION else None
    normalized_dispatch_identities: dict[str, str] = {}
    normalized_integration_owner: str | None = None
    if version == SCHEMA_VERSION and dispatch_binding is not None:
        if not isinstance(dispatch_binding, dict) or set(dispatch_binding) != DISPATCH_BINDING_KEYS:
            errors.append("dispatch binding is malformed")
        else:
            if (
                not isinstance(dispatch_binding.get("receipt_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", dispatch_binding["receipt_sha256"]) is None
            ):
                errors.append("dispatch binding receipt digest is invalid")
            try:
                normalized_integration_owner = canonical_identity(
                    dispatch_binding.get("integration_owner"), "dispatch integration owner"
                )
            except ProgramStateError:
                errors.append("dispatch integration owner is invalid")
            identities = dispatch_binding.get("isolation_identities")
            if not isinstance(identities, dict) or not identities:
                errors.append("dispatch isolation identities are malformed")
            else:
                for bound_unit_id, identity in identities.items():
                    try:
                        normalized_dispatch_identities[bound_unit_id] = canonical_identity(
                            identity, f"dispatch isolation identity for {bound_unit_id}"
                        )
                    except ProgramStateError:
                        errors.append(f"dispatch isolation identity for {bound_unit_id} is invalid")
                if len(normalized_dispatch_identities) != len(set(normalized_dispatch_identities.values())):
                    errors.append("dispatch isolation identities must be unique")
                if (
                    normalized_integration_owner is not None
                    and normalized_integration_owner in normalized_dispatch_identities.values()
                ):
                    errors.append("dispatch isolation identities must differ from integration owner")
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
                or len(gate["reason"]) > 2000
            ):
                errors.append(f"gate {name} fields are invalid")
        if (
            version == SCHEMA_VERSION
            and isinstance(gates.get("dispatch"), dict)
            and gates["dispatch"].get("open") is True
            and dispatch_binding is None
        ):
            errors.append("open dispatch gate requires a dispatch binding")
    units = state.get("units")
    if not isinstance(units, dict) or not units or len(units) > MAX_UNITS:
        errors.append(f"units must be a non-empty object with at most {MAX_UNITS} entries")
    else:
        known = set(units)
        for unit_id, unit in units.items():
            if (
                not isinstance(unit_id, str)
                or len(unit_id) > 64
                or PROGRAM_ID.fullmatch(unit_id) is None
                or not isinstance(unit, dict)
                or set(unit) != unit_keys
            ):
                errors.append(f"unit {unit_id!r} is malformed")
                continue
            if unit.get("id") != unit_id or unit.get("state") not in UNIT_STATES:
                errors.append(f"unit {unit_id} identity or state is invalid")
            dependencies = unit.get("depends_on")
            if (
                not isinstance(dependencies, list)
                or len(dependencies) > MAX_DEPENDENCIES
                or len(dependencies) != len(set(dependencies))
                or not set(dependencies) <= known
            ):
                errors.append(f"unit {unit_id} dependencies are invalid")
            elif unit_id in dependencies:
                errors.append(f"unit {unit_id} cannot depend on itself")
            if (
                not isinstance(unit.get("files"), list)
                or not unit["files"]
                or len(unit["files"]) > MAX_FILES
                or not all(repository_pattern(item) for item in unit["files"])
            ):
                errors.append(f"unit {unit_id} files are invalid")
            head = unit.get("head_sha")
            if head is not None and (not isinstance(head, str) or HEAD_SHA.fullmatch(head) is None):
                errors.append(f"unit {unit_id} head SHA is invalid")
            if version == SCHEMA_VERSION:
                assignment = unit.get("assignment")
                if not isinstance(assignment, dict) or set(assignment) != ASSIGNMENT_KEYS:
                    errors.append(f"unit {unit_id} assignment is malformed")
                else:
                    actor = assignment.get("actor")
                    isolation_identity = assignment.get("isolation_identity")
                    assigned_at = assignment.get("assigned_at")
                    generation = assignment.get("generation")
                    try:
                        checked_generation(generation, f"unit {unit_id} assignment generation")
                    except ProgramStateError:
                        errors.append(f"unit {unit_id} assignment generation is invalid")
                    all_empty = actor is None and isolation_identity is None and assigned_at is None
                    all_present = (
                        actor is not None
                        and isolation_identity is not None
                        and assigned_at is not None
                    )
                    if not all_empty and not all_present:
                        errors.append(f"unit {unit_id} assignment fields must be all present or all null")
                    if all_present:
                        if not valid_timestamp(assigned_at):
                            errors.append(f"unit {unit_id} assignment timestamp is invalid")
                        try:
                            actor_key = canonical_identity(actor, f"unit {unit_id} assignment actor")
                            isolation_key = canonical_identity(
                                isolation_identity, f"unit {unit_id} assignment isolation identity"
                            )
                        except ProgramStateError:
                            errors.append(f"unit {unit_id} assignment identity is invalid")
                        else:
                            if generation == 0:
                                errors.append(f"unit {unit_id} active assignment requires a positive generation")
                            if dispatch_binding is None:
                                errors.append(f"unit {unit_id} active assignment requires a dispatch binding")
                            elif normalized_dispatch_identities.get(unit_id) != isolation_key:
                                errors.append(f"unit {unit_id} assignment isolation identity does not match dispatch")
                            if normalized_integration_owner is not None and actor_key == normalized_integration_owner:
                                errors.append(f"unit {unit_id} assignment actor must differ from integration owner")
            for kind in VERDICT_KINDS:
                record = unit.get(kind)
                if record is not None and (not isinstance(record, dict) or set(record) != verdict_keys):
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
                    if version == SCHEMA_VERSION:
                        snapshot = record.get("assignment")
                        if not isinstance(snapshot, dict) or set(snapshot) != ASSIGNMENT_SNAPSHOT_KEYS:
                            errors.append(f"unit {unit_id} {kind} assignment snapshot is malformed")
                        else:
                            try:
                                canonical_identity(snapshot.get("actor"), "verdict assignment actor")
                                canonical_identity(
                                    snapshot.get("isolation_identity"),
                                    "verdict assignment isolation identity",
                                )
                                generation = checked_generation(
                                    snapshot.get("generation"), "verdict assignment generation"
                                )
                                if generation == 0:
                                    raise ProgramStateError("verdict assignment generation must be positive")
                            except ProgramStateError:
                                errors.append(f"unit {unit_id} {kind} assignment snapshot is invalid")
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
            if version == SCHEMA_VERSION and isinstance(unit.get("review"), dict):
                verification = unit.get("verification")
                current_assignment = assignment_snapshot(unit)
                if not isinstance(verification, dict) or current_assignment is None:
                    errors.append(f"unit {unit_id} review requires verification and assignment")
                else:
                    try:
                        review_key = canonical_identity(
                            unit["review"].get("actor"), f"unit {unit_id} review actor"
                        )
                        verifier_key = canonical_identity(
                            verification.get("actor"), f"unit {unit_id} verification actor"
                        )
                    except ProgramStateError:
                        pass
                    else:
                        prohibited_reviewers = {
                            verifier_key,
                            current_assignment["actor"],
                        }
                        if normalized_integration_owner is not None:
                            prohibited_reviewers.add(normalized_integration_owner)
                        if review_key in prohibited_reviewers:
                            errors.append(
                                f"unit {unit_id} review actor is not independent"
                            )
        if version == SCHEMA_VERSION and dispatch_binding is not None:
            if set(normalized_dispatch_identities) != known:
                errors.append("dispatch binding must map every program unit exactly once")
        graph = {
            unit_id: unit["depends_on"]
            for unit_id, unit in units.items()
            if isinstance(unit, dict)
            and isinstance(unit.get("depends_on"), list)
            and set(unit["depends_on"]) <= known
        }
        indegree = {unit_id: 0 for unit_id in graph}
        dependents: dict[str, list[str]] = {unit_id: [] for unit_id in graph}
        for unit_id, dependencies in graph.items():
            for dependency in dependencies:
                if dependency in graph:
                    indegree[unit_id] += 1
                    dependents[dependency].append(unit_id)
        frontier_ids = [unit_id for unit_id, degree in indegree.items() if degree == 0]
        visited = 0
        while frontier_ids:
            unit_id = frontier_ids.pop()
            visited += 1
            for dependent in dependents[unit_id]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    frontier_ids.append(dependent)
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
        ordered_ids = sorted(graph)
        for index, left_id in enumerate(ordered_ids):
            for right_id in ordered_ids[index + 1 :]:
                if left_id in ancestors[right_id] or right_id in ancestors[left_id]:
                    continue
                left_files = units[left_id].get("files", [])
                right_files = units[right_id].get("files", [])
                if any(
                    ownership_patterns_overlap(left, right)
                    for left in left_files
                    for right in right_files
                    if isinstance(left, str) and isinstance(right, str)
                ):
                    errors.append(
                        f"unordered units {left_id} and {right_id} have overlapping ownership"
                    )
    inbox = state.get("inbox")
    if (
        not isinstance(inbox, list)
        or len(inbox) > MAX_INBOX_EVENTS
        or not all(isinstance(event, dict) and set(event) == inbox_keys for event in inbox)
    ):
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
            if version == SCHEMA_VERSION:
                snapshot = event.get("assignment")
                if event.get("unit_id") is None:
                    if snapshot is not None:
                        errors.append("program-wide inbox event must not contain an assignment")
                elif not isinstance(snapshot, dict) or set(snapshot) != ASSIGNMENT_SNAPSHOT_KEYS:
                    errors.append("unit inbox event assignment is malformed")
                else:
                    try:
                        canonical_identity(snapshot.get("actor"), "inbox assignment actor")
                        canonical_identity(
                            snapshot.get("isolation_identity"), "inbox assignment isolation identity"
                        )
                        generation = checked_generation(
                            snapshot.get("generation"), "inbox assignment generation"
                        )
                        if generation == 0:
                            raise ProgramStateError("inbox assignment generation must be positive")
                    except ProgramStateError:
                        errors.append("unit inbox event assignment is invalid")
        if observed_sequences != sorted(set(observed_sequences)):
            errors.append("inbox event sequence order is invalid")
    sequence = state.get("inbox_sequence")
    if not isinstance(sequence, int) or sequence < 0:
        errors.append("inbox sequence is invalid")
    elif isinstance(inbox, list) and inbox and any(event.get("sequence", 0) > sequence for event in inbox if isinstance(event, dict)):
        errors.append("inbox event sequence exceeds store sequence")
    return errors


def read_state_document(root: Path, program_id: str) -> dict[str, Any]:
    path = state_path(root, program_id)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_PROGRAM_STATE_BYTES
        ):
            raise ProgramStateError("program state must be a bounded unique regular file")
        chunks: list[bytes] = []
        remaining = MAX_PROGRAM_STATE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_PROGRAM_STATE_BYTES:
            raise ProgramStateError("program state exceeds the byte limit")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ProgramStateError(f"invalid state file: {error}") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    if not isinstance(value, dict):
        raise ProgramStateError("state root must be an object")
    return value


def load_state(root: Path, program_id: str) -> dict[str, Any]:
    value = read_state_document(root, program_id)
    if (
        not isinstance(value.get("schema_version"), bool)
        and value.get("schema_version") == LEGACY_SCHEMA_VERSION
    ):
        raise ProgramStateError(
            "legacy schema v1 requires explicit migrate-v1 --invalidate-legacy-evidence"
        )
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


def migrate_v1(
    root: Path,
    program_id: str,
    invalidate_legacy_evidence: bool,
) -> dict[str, Any]:
    if invalidate_legacy_evidence is not True:
        raise ProgramStateError("v1 migration requires --invalidate-legacy-evidence")
    with program_lock(root, program_id):
        legacy = read_state_document(root, program_id)
        if (
            isinstance(legacy.get("schema_version"), bool)
            or legacy.get("schema_version") != LEGACY_SCHEMA_VERSION
        ):
            raise ProgramStateError("program state is not schema v1")
        errors = schema_errors(
            legacy,
            root,
            program_id,
            allowed_versions=frozenset({LEGACY_SCHEMA_VERSION}),
        )
        if errors:
            raise ProgramStateError("legacy state is invalid: " + "; ".join(errors))
        timestamp = now()
        migrated = dict(legacy)
        migrated["schema_version"] = SCHEMA_VERSION
        migrated["dispatch_binding"] = None
        migrated["gates"] = {
            "dispatch": {
                "open": False,
                "reason": "legacy migration requires a fresh dispatch receipt",
                "updated_at": timestamp,
            },
            "delivery": {
                "open": False,
                "reason": "legacy evidence invalidated during schema migration",
                "updated_at": timestamp,
            },
        }
        migrated["inbox"] = []
        for unit in migrated["units"].values():
            unit["state"] = "pending"
            unit["verification"] = None
            unit["review"] = None
            unit["assignment"] = empty_assignment()
            unit["updated_at"] = timestamp
        migrated["updated_at"] = timestamp
        save_state(root, program_id, migrated)
        return migrated


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
                "assignment": empty_assignment(),
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
            "dispatch_binding": None,
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


def invalidate_assignment(
    state: dict[str, Any],
    unit_id: str,
    timestamp: str,
    *,
    advance_generation: bool,
) -> None:
    unit = state["units"][unit_id]
    current_generation = checked_generation(
        unit["assignment"]["generation"], f"unit {unit_id} assignment generation"
    )
    next_generation = current_generation
    if advance_generation:
        if current_generation == MAX_ASSIGNMENT_GENERATION:
            raise ProgramStateError("assignment generation is exhausted")
        next_generation += 1
    unit["assignment"] = empty_assignment(next_generation)
    unit["verification"] = None
    unit["review"] = None
    unit["state"] = "pending"
    unit["updated_at"] = timestamp
    state["inbox"] = [event for event in state["inbox"] if event["unit_id"] != unit_id]


def set_gate(
    root: Path,
    program_id: str,
    name: str,
    opened: bool,
    reason: str,
    receipt_path: Path | None = None,
    integration_owner: str | None = None,
) -> dict[str, Any]:
    if name not in GATE_NAMES:
        raise ProgramStateError(f"gate must be one of {sorted(GATE_NAMES)}")
    reason = checked_text(reason, "gate reason", 1000)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if opened and name == "delivery" and not delivery_ready(root, state):
            raise ProgramStateError("delivery gate requires every unit to have complete fresh evidence")
        if opened and name == "dispatch":
            if receipt_path is None or integration_owner is None:
                raise ProgramStateError(
                    "dispatch gate requires a content-bound parallel gate receipt and integration owner"
                )
            try:
                receipt, _ = load_parallel_gate_receipt(receipt_path)
                receipt_summary = validate_parallel_gate_receipt(
                    receipt,
                    expected_program_id=program_id,
                    expected_plan_digest=state["plan_digest"],
                    expected_integration_owner=integration_owner,
                    expected_units=set(state["units"]),
                )
            except TeamShapeError as error:
                raise ProgramStateError(f"dispatch gate receipt is invalid: {error}") from error
            dispatch_binding = {
                "receipt_sha256": receipt_summary["sha256"],
                "integration_owner": canonical_identity(
                    receipt["integration_owner"], "dispatch integration owner"
                ),
                "isolation_identities": {
                    unit_id: canonical_identity(identity, f"isolation identity for {unit_id}")
                    for unit_id, identity in sorted(receipt["isolation_identities"].items())
                },
            }
            if state["dispatch_binding"] != dispatch_binding:
                timestamp = now()
                for unit_id, unit in state["units"].items():
                    if assignment_snapshot(unit) is not None:
                        invalidate_assignment(
                            state, unit_id, timestamp, advance_generation=True
                        )
                state["inbox"] = []
                state["dispatch_binding"] = dispatch_binding
                state["gates"]["delivery"] = {
                    "open": False,
                    "reason": "dispatch receipt changed",
                    "updated_at": timestamp,
                }
            reason = (
                f"{reason}; receipt_sha256={receipt_summary['sha256']}; "
                f"integration_owner={receipt_summary['integration_owner']}; "
                f"isolation_count={receipt_summary['isolation_count']}"
            )
        if not opened and name == "dispatch":
            timestamp = now()
            for unit_id, unit in state["units"].items():
                if assignment_snapshot(unit) is not None:
                    invalidate_assignment(state, unit_id, timestamp, advance_generation=True)
            state["gates"]["delivery"] = {
                "open": False,
                "reason": "dispatch closed and active assignments revoked",
                "updated_at": timestamp,
            }
        timestamp = now()
        state["gates"][name] = {"open": opened, "reason": reason, "updated_at": timestamp}
        state["updated_at"] = timestamp
        save_state(root, program_id, state)
        return state


def assign_unit(
    root: Path,
    program_id: str,
    unit_id: str,
    actor: str,
    isolation_identity: str,
    expected_generation: int,
) -> dict[str, Any]:
    actor_key = canonical_identity(actor, "assignment actor")
    isolation_key = canonical_identity(isolation_identity, "assignment isolation identity")
    expected_generation = checked_generation(expected_generation, "expected assignment generation")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        if not state["gates"]["dispatch"]["open"] or state["dispatch_binding"] is None:
            raise ProgramStateError("unit assignment requires an open bound dispatch gate")
        unit = state["units"][unit_id]
        if not dependencies_complete(root, state, unit):
            raise ProgramStateError("unit assignment requires complete fresh dependency evidence")
        assignment = unit["assignment"]
        current_generation = checked_generation(
            assignment["generation"], f"unit {unit_id} assignment generation"
        )
        if current_generation != expected_generation:
            raise ProgramStateError("stale expected assignment generation")
        if current_generation == MAX_ASSIGNMENT_GENERATION:
            raise ProgramStateError("assignment generation is exhausted")
        binding = state["dispatch_binding"]
        if isolation_key != binding["isolation_identities"][unit_id]:
            raise ProgramStateError("assignment isolation identity does not match dispatch")
        if actor_key == binding["integration_owner"]:
            raise ProgramStateError("assignment actor must differ from integration owner")
        timestamp = now()
        invalidate_assignment(
            state, unit_id, timestamp, advance_generation=False
        )
        state["units"][unit_id]["assignment"] = {
            "actor": actor_key,
            "isolation_identity": isolation_key,
            "generation": current_generation + 1,
            "assigned_at": timestamp,
        }
        state["gates"]["delivery"] = {
            "open": False,
            "reason": f"unit {unit_id} assignment changed",
            "updated_at": timestamp,
        }
        state["updated_at"] = timestamp
        save_state(root, program_id, state)
        return state


def set_head(
    root: Path,
    program_id: str,
    unit_id: str,
    head_sha: str,
    expected_head_sha: str | None,
    assignment_generation: int,
) -> dict[str, Any]:
    head_sha = checked_commit(root, head_sha)
    if expected_head_sha is not None:
        expected_head_sha = checked_head(expected_head_sha)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        require_current_assignment(state, unit, assignment_generation)
        if unit["head_sha"] != expected_head_sha:
            raise ProgramStateError("stale expected unit head")
        if not head_includes_dependencies(root, state, unit, head_sha):
            raise ProgramStateError(
                "unit head must contain every dependency head in its Git ancestry"
            )
        if unit["head_sha"] != head_sha:
            timestamp = now()
            unit["head_sha"] = head_sha
            unit["verification"] = None
            unit["review"] = None
            state["inbox"] = [event for event in state["inbox"] if event["unit_id"] != unit_id]
            if unit["state"] == "completed":
                unit["state"] = "running"
            for dependent_id in dependent_units(state, unit_id):
                dependent = state["units"][dependent_id]
                invalidate_assignment(
                    state,
                    dependent_id,
                    timestamp,
                    advance_generation=assignment_snapshot(dependent) is not None,
                )
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
    assignment_generation: int,
) -> dict[str, Any]:
    if kind not in VERDICT_KINDS or verdict not in VERDICTS:
        raise ProgramStateError("verdict kind or value is invalid")
    actor_key = canonical_identity(actor, "verdict actor")
    head_sha = checked_commit(root, head_sha)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        current_assignment = require_current_assignment(state, unit, assignment_generation)
        if unit["head_sha"] != head_sha:
            raise ProgramStateError("verdict head does not match the unit head")
        if not head_includes_dependencies(root, state, unit, head_sha):
            raise ProgramStateError(
                "verdict head must contain every dependency head in its Git ancestry"
            )
        if unit[kind] is not None:
            raise ProgramStateError(
                "verdict slot is already recorded for the current head and assignment"
            )
        if kind == "review":
            if not verdict_is_fresh(root, unit, "verification"):
                raise ProgramStateError("review requires a fresh passing verification verdict")
            verifier_key = canonical_identity(unit["verification"]["actor"], "verification actor")
            prohibited_reviewers = {
                verifier_key,
                current_assignment["actor"],
                state["dispatch_binding"]["integration_owner"],
            }
            if actor_key in prohibited_reviewers:
                raise ProgramStateError(
                    "review actor must differ from the verifier, assigned worker, and integration owner"
                )
        binding = evidence_binding(evidence_path)
        timestamp = now()
        unit[kind] = {
            "actor": actor,
            "verdict": verdict,
            "head_sha": head_sha,
            "evidence": binding,
            "assignment": current_assignment,
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


def set_unit_state(
    root: Path,
    program_id: str,
    unit_id: str,
    destination: str,
    assignment_generation: int,
) -> dict[str, Any]:
    if destination not in UNIT_STATES:
        raise ProgramStateError(f"unit state must be one of {sorted(UNIT_STATES)}")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        unit = state["units"][unit_id]
        require_current_assignment(state, unit, assignment_generation)
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
            if not isinstance(unit.get("head_sha"), str) or not head_includes_dependencies(
                root, state, unit, unit["head_sha"]
            ):
                raise ProgramStateError(
                    "unit completion requires a head containing every dependency head"
                )
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
    actor: str | None = None,
    isolation_identity: str | None = None,
    assignment_generation: int | None = None,
    coordinator_identity: str | None = None,
) -> dict[str, Any]:
    kind = checked_text(kind, "event kind", 64)
    summary = checked_text(summary, "event summary", 1000)
    if head_sha is not None:
        head_sha = checked_head(head_sha)
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if len(state["inbox"]) >= MAX_INBOX_EVENTS:
            raise ProgramStateError("inbox is full; acknowledge processed events before appending")
        if unit_id is not None and unit_id not in state["units"]:
            raise ProgramStateError(f"unknown unit: {unit_id}")
        if unit_id is None:
            if actor is not None or isolation_identity is not None or assignment_generation is not None:
                raise ProgramStateError("program-wide inbox event must not contain assignment fields")
            if coordinator_identity is None or state["dispatch_binding"] is None:
                raise ProgramStateError(
                    "program-wide inbox event requires the bound integration owner"
                )
            if (
                canonical_identity(coordinator_identity, "inbox coordinator")
                != state["dispatch_binding"]["integration_owner"]
            ):
                raise ProgramStateError("inbox coordinator does not match integration owner")
            current_assignment = None
        else:
            if coordinator_identity is not None:
                raise ProgramStateError("unit inbox event must not contain a coordinator identity")
            if actor is None or isolation_identity is None or assignment_generation is None:
                raise ProgramStateError(
                    "unit inbox event requires actor, isolation identity, and assignment generation"
                )
            current_assignment = require_current_assignment(
                state,
                state["units"][unit_id],
                assignment_generation,
                actor=actor,
                isolation_identity=isolation_identity,
            )
            if head_sha is None:
                raise ProgramStateError("unit inbox event requires the current unit head")
            if head_sha != state["units"][unit_id]["head_sha"]:
                raise ProgramStateError("unit inbox head does not match the current unit head")
            if not git_commit_exists(root, head_sha):
                raise ProgramStateError("unit inbox head must be a commit present in the repository")
        sequence = state["inbox_sequence"] + 1
        event = {
            "sequence": sequence,
            "kind": kind,
            "unit_id": unit_id,
            "summary": summary,
            "head_sha": head_sha,
            "assignment": current_assignment,
            "recorded_at": now(),
        }
        state["inbox"].append(event)
        state["inbox_sequence"] = sequence
        state["updated_at"] = event["recorded_at"]
        save_state(root, program_id, state)
        return event


def peek_inbox(
    root: Path,
    program_id: str,
    after_sequence: int = 0,
    limit: int = 10,
) -> list[dict[str, Any]]:
    if isinstance(after_sequence, bool) or not isinstance(after_sequence, int) or after_sequence < 0:
        raise ProgramStateError("inbox cursor must be an integer >= 0")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ProgramStateError("inbox limit must be between 1 and 100")
    return [
        event for event in load_state(root, program_id)["inbox"]
        if event["sequence"] > after_sequence
    ][:limit]


def acknowledge_inbox(
    root: Path,
    program_id: str,
    through_sequence: int,
    coordinator_identity: str,
) -> dict[str, int]:
    if isinstance(through_sequence, bool) or not isinstance(through_sequence, int) or through_sequence < 1:
        raise ProgramStateError("acknowledgement sequence must be an integer >= 1")
    with program_lock(root, program_id):
        state = load_state(root, program_id)
        if state["dispatch_binding"] is None:
            raise ProgramStateError("inbox acknowledgement requires a bound integration owner")
        if (
            canonical_identity(coordinator_identity, "inbox coordinator")
            != state["dispatch_binding"]["integration_owner"]
        ):
            raise ProgramStateError("inbox coordinator does not match integration owner")
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


def status(
    root: Path,
    program_id: str,
    unit_id: str | None = None,
    brief: bool = False,
) -> dict[str, Any]:
    state = load_state(root, program_id)
    if unit_id is not None and unit_id not in state["units"]:
        raise ProgramStateError(f"unknown unit: {unit_id}")
    ready = delivery_ready(root, state)
    open_frontier = frontier(root, state)
    result: dict[str, Any] = {
        "store": str(program_directory(root, program_id)),
        "program_id": program_id,
        "objective": state["objective"],
        "plan_digest": state["plan_digest"],
        "dispatch_binding": state["dispatch_binding"],
        "gates": state["gates"],
        "frontier": open_frontier,
        "delivery_ready": ready,
        "delivery_gate_open": state["gates"]["delivery"]["open"],
        "delivery_authority_granted": False,
        "delivery_admitted": state["gates"]["delivery"]["open"] and ready,
        "inbox_count": len(state["inbox"]),
    }
    if brief:
        result.pop("frontier")
        result.pop("objective")
        result["frontier_count"] = len(open_frontier)
        result["frontier_preview"] = open_frontier[:8]
        result["frontier_truncated"] = len(open_frontier) > 8
        result["unit_counts"] = {
            name: sum(unit["state"] == name for unit in state["units"].values())
            for name in sorted(UNIT_STATES)
        }
        result["assigned_unit_count"] = sum(
            assignment_snapshot(unit) is not None for unit in state["units"].values()
        )
        result.pop("dispatch_binding")
        return result
    selected_units = (
        {unit_id: state["units"][unit_id]}
        if unit_id is not None
        else state["units"]
    )
    result["units"] = {
            unit_id: {
                "state": unit["state"],
                "assignment": unit["assignment"],
                "head_sha": unit["head_sha"],
                "head_present": (
                    isinstance(unit["head_sha"], str)
                    and git_commit_exists(root, unit["head_sha"])
                ),
                "dependencies_ready": dependencies_complete(root, state, unit),
                "verification_fresh": verdict_is_fresh(root, unit, "verification"),
                "review_fresh": verdict_is_fresh(root, unit, "review"),
            }
            for unit_id, unit in sorted(selected_units.items())
    }
    return result


def compact_state_receipt(root: Path, state: dict[str, Any], action: str) -> dict[str, Any]:
    """Return a bounded coordination receipt instead of the full unit ledger."""
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ready = delivery_ready(root, state)
    open_frontier = frontier(root, state)
    return {
        "schema_version": 1,
        "kind": "patpat.program.mutation_receipt",
        "action": action,
        "store": str(program_directory(root, state["program_id"])),
        "program_id": state["program_id"],
        "plan_digest": state["plan_digest"],
        "frontier_count": len(open_frontier),
        "frontier_preview": open_frontier[:8],
        "frontier_truncated": len(open_frontier) > 8,
        "delivery_ready": ready,
        "delivery_gate_open": state["gates"]["delivery"]["open"],
        "delivery_authority_granted": False,
        "inbox_count": len(state["inbox"]),
        "assigned_unit_count": sum(
            assignment_snapshot(unit) is not None for unit in state["units"].values()
        ),
        "unit_counts": {
            name: sum(unit["state"] == name for unit in state["units"].values())
            for name in sorted(UNIT_STATES)
        },
        "state_sha256": hashlib.sha256(payload).hexdigest(),
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
        if os.name != "nt":
            assert program_directory(root, "release-train").stat().st_mode & 0o777 == 0o700
            assert state_path(root, "release-train").stat().st_mode & 0o777 == 0o600
        assert status(root, "release-train")["frontier"] == []
        expect_error(
            lambda: set_gate(root, "release-train", "delivery", True, "ship now"),
            "complete fresh evidence",
        )
        expect_error(
            lambda: set_gate(root, "release-train", "dispatch", True, "plan reviewed"),
            "content-bound parallel gate receipt",
        )
        initialized = load_state(root, "release-train")
        parallel_receipt = {
            "schema_version": 1,
            "kind": PARALLEL_GATE_KIND,
            "program_id": "release-train",
            "plan_digest": initialized["plan_digest"],
            "integration_owner": "Integration Owner",
            "checks": {name: True for name in PARALLEL_GATE_CHECKS},
            "isolation_identities": {
                "contract": "worktree-contract",
                "consumer": "worktree-consumer",
            },
        }
        receipt_path = root / "parallel-gate.json"
        receipt_path.write_text(json.dumps(parallel_receipt), encoding="utf-8")
        tampered_receipt = json.loads(json.dumps(parallel_receipt))
        tampered_receipt["plan_digest"] = "f" * 64
        tampered_path = root / "tampered-parallel-gate.json"
        tampered_path.write_text(json.dumps(tampered_receipt), encoding="utf-8")
        expect_error(
            lambda: set_gate(
                root,
                "release-train",
                "dispatch",
                True,
                "plan reviewed",
                tampered_path,
                "Integration Owner",
            ),
            "plan_digest does not match",
        )
        set_gate(
            root,
            "release-train",
            "dispatch",
            True,
            "plan reviewed",
            receipt_path,
            "Integration Owner",
        )
        assert status(root, "release-train")["frontier"] == ["contract"]

        expect_error(
            lambda: set_unit_state(root, "release-train", "contract", "running", 0),
            "current assignment",
        )
        expect_error(
            lambda: assign_unit(
                root, "release-train", "contract", "Worker Contract", "wrong-worktree", 0
            ),
            "does not match dispatch",
        )
        expect_error(
            lambda: assign_unit(
                root, "release-train", "contract", "Integration Owner", "worktree-contract", 0
            ),
            "differ from integration owner",
        )
        assigned = assign_unit(
            root, "release-train", "contract", "Worker Contract", "worktree-contract", 0
        )
        assert assigned["units"]["contract"]["assignment"]["generation"] == 1
        expect_error(
            lambda: assign_unit(
                root, "release-train", "consumer", "Worker Consumer", "worktree-consumer", 0
            ),
            "complete fresh dependency evidence",
        )
        expect_error(
            lambda: assign_unit(
                root, "release-train", "contract", "Worker Contract", "worktree-contract", 0
            ),
            "stale expected",
        )

        set_gate(root, "release-train", "dispatch", False, "coordinator pause")
        assert status(root, "release-train")["frontier"] == []
        expect_error(
            lambda: set_unit_state(root, "release-train", "contract", "running", 1),
            "open bound dispatch",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "paused worker", "contract", None,
                "Worker Contract", "worktree-contract", 1,
            ),
            "open bound dispatch",
        )
        reopened = set_gate(
            root,
            "release-train",
            "dispatch",
            True,
            "coordinator resume",
            receipt_path,
            "Integration Owner",
        )
        assert reopened["units"]["contract"]["assignment"] == empty_assignment(2)
        assert status(root, "release-train")["frontier"] == ["contract"]
        resumed = assign_unit(
            root, "release-train", "contract", "Worker Contract", "worktree-contract", 2
        )
        assert resumed["units"]["contract"]["assignment"]["generation"] == 3
        head_one = git_text(root, "rev-parse", "HEAD")
        assert head_one is not None
        set_head(root, "release-train", "contract", head_one, None, 3)

        append_inbox(
            root, "release-train", "worker-update", "contract ready", "contract", head_one,
            "Worker Contract", "worktree-contract", 3,
        )
        append_inbox(
            root, "release-train", "ci", "checks queued", None, None,
            coordinator_identity="Integration Owner",
        )
        expect_error(
            lambda: append_inbox(root, "release-train", "ci", "missing owner", None, None),
            "bound integration owner",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "ci", "wrong owner", None, None,
                coordinator_identity="Wrong Owner",
            ),
            "does not match integration owner",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "wrong actor", "contract", head_one,
                "Another Worker", "worktree-contract", 3,
            ),
            "actor does not match",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "wrong isolation", "contract", head_one,
                "Worker Contract", "worktree-consumer", 3,
            ),
            "isolation identity does not match",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "coordinator", "invalid global", None, None,
                "Worker Contract", "worktree-contract", 3,
            ),
            "program-wide inbox event",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "stale", "contract", head_one,
                "Worker Contract", "worktree-contract", 0,
            ),
            "stale assignment generation",
        )
        observed_inbox = peek_inbox(root, "release-train")
        assert [event["sequence"] for event in observed_inbox] == [1, 2]
        assert [event["sequence"] for event in peek_inbox(root, "release-train", 1, 1)] == [2]
        expect_error(lambda: peek_inbox(root, "release-train", 0, 101), "between 1 and 100")
        expect_error(
            lambda: append_inbox(root, "release-train", "note", "x" * 1001, None, None),
            "at most 1000",
        )
        assert [event["sequence"] for event in peek_inbox(root, "release-train")] == [1, 2]
        expect_error(
            lambda: acknowledge_inbox(root, "release-train", 1, "Wrong Owner"),
            "does not match integration owner",
        )
        assert acknowledge_inbox(root, "release-train", 1, "Integration Owner") == {
            "acknowledged_through": 1,
            "remaining": 1,
        }
        assert [event["sequence"] for event in peek_inbox(root, "release-train")] == [2]
        assert acknowledge_inbox(root, "release-train", 2, "Integration Owner") == {
            "acknowledged_through": 2,
            "remaining": 0,
        }
        assert acknowledge_inbox(root, "release-train", 2, "Integration Owner")["remaining"] == 0
        assert status(root, "release-train")["inbox_count"] == 0

        evidence = root / "evidence.txt"
        evidence.write_text("verified\n", encoding="utf-8")
        set_unit_state(root, "release-train", "contract", "running", 3)
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "wrong head", "contract", "f" * 40,
                "Worker Contract", "worktree-contract", 3,
            ),
            "head does not match",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "missing head", "contract", None,
                "Worker Contract", "worktree-contract", 3,
            ),
            "requires the current unit head",
        )
        record_verdict(
            root, "release-train", "contract", "verification", "pass",
            head_one, "Verifier", evidence, 3,
        )
        expect_error(
            lambda: record_verdict(
                root, "release-train", "contract", "verification", "fail",
                head_one, "Verifier", evidence, 3,
            ),
            "verdict slot is already recorded",
        )
        for non_reviewer in ("Verifier", "Worker Contract", "Integration Owner"):
            expect_error(
                lambda actor=non_reviewer: record_verdict(
                    root, "release-train", "contract", "review", "pass",
                    head_one, actor, evidence, 3,
                ),
                "review actor must differ",
            )
        record_verdict(
            root, "release-train", "contract", "review", "pass",
            head_one, "Reviewer", evidence, 3,
        )
        expect_error(
            lambda: record_verdict(
                root, "release-train", "contract", "review", "fail",
                head_one, "Reviewer", evidence, 3,
            ),
            "verdict slot is already recorded",
        )
        set_unit_state(root, "release-train", "contract", "completed", 3)
        assert status(root, "release-train")["frontier"] == ["consumer"]

        consumer_evidence = root / "consumer-evidence.txt"
        consumer_evidence.write_text("consumer verified\n", encoding="utf-8")
        consumer_head = head_one
        assign_unit(
            root, "release-train", "consumer", "Worker Consumer", "worktree-consumer", 0
        )
        set_unit_state(root, "release-train", "consumer", "running", 1)
        set_head(root, "release-train", "consumer", consumer_head, None, 1)
        record_verdict(
            root, "release-train", "consumer", "verification", "pass",
            consumer_head, "Consumer Verifier", consumer_evidence, 1,
        )
        record_verdict(
            root, "release-train", "consumer", "review", "pass",
            consumer_head, "Consumer Reviewer", consumer_evidence, 1,
        )
        set_unit_state(root, "release-train", "consumer", "completed", 1)
        set_gate(root, "release-train", "delivery", True, "all evidence is fresh")
        assert status(root, "release-train")["delivery_ready"]
        completed_state_path = state_path(root, "release-train")
        completed_state_bytes = completed_state_path.read_bytes()
        tampered_review = json.loads(completed_state_bytes)
        tampered_review["units"]["contract"]["review"]["actor"] = "WORKER CONTRACT"
        atomic_write_json(completed_state_path, tampered_review)
        expect_error(lambda: status(root, "release-train"), "review actor is not independent")
        completed_state_path.write_bytes(completed_state_bytes)

        marker.write_text("changed dependency\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "marker.txt"], check=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "change dependency"], check=True)
        head_two = git_text(root, "rev-parse", "HEAD")
        assert head_two is not None
        set_head(root, "release-train", "contract", head_two, head_one, 3)
        observed = status(root, "release-train")
        assert observed["units"]["contract"]["state"] == "running"
        assert not observed["units"]["contract"]["verification_fresh"]
        assert observed["units"]["consumer"]["state"] == "pending"
        assert observed["units"]["consumer"]["assignment"] == empty_assignment(2)
        assert not observed["units"]["consumer"]["verification_fresh"]
        assert not observed["units"]["consumer"]["review_fresh"]
        assert not observed["delivery_ready"]
        assert observed["frontier"] == []
        expect_error(
            lambda: set_head(root, "release-train", "consumer", head_two, head_one, 1),
            "current assignment",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "stale dependent", "consumer", head_two,
                "Worker Consumer", "worktree-consumer", 1,
            ),
            "current assignment",
        )

        record_verdict(
            root, "release-train", "contract", "verification", "fail",
            head_two, "Verifier", evidence, 3,
        )
        expect_error(
            lambda: record_verdict(
                root, "release-train", "contract", "review", "pass",
                head_two, "Reviewer", evidence, 3,
            ),
            "fresh passing verification",
        )
        append_inbox(
            root, "release-train", "worker-update", "head-two proof", "contract", head_two,
            "Worker Contract", "worktree-contract", 3,
        )
        assert not status(root, "release-train")["units"]["contract"]["verification_fresh"]

        tree = git_text(root, "write-tree")
        assert tree is not None
        orphan_result = subprocess.run(
            ["git", "-C", str(root), "commit-tree", tree],
            input=b"orphan evidence head\n",
            check=True,
            capture_output=True,
        )
        orphan_head = os.fsdecode(orphan_result.stdout).strip()
        set_head(root, "release-train", "contract", orphan_head, head_two, 3)
        subprocess.run(
            ["git", "-C", str(root), "reflog", "expire", "--expire=now", "--all"],
            check=True,
        )
        subprocess.run(["git", "-C", str(root), "gc", "--prune=now"], check=True)
        assert not git_commit_exists(root, orphan_head)
        pruned = status(root, "release-train")
        assert not pruned["units"]["contract"]["head_present"]
        assert not pruned["units"]["contract"]["verification_fresh"]
        assert not pruned["units"]["contract"]["review_fresh"]
        assert all(event["unit_id"] != "contract" for event in peek_inbox(root, "release-train"))
        assert not pruned["delivery_ready"]
        assert not pruned["delivery_gate_open"]
        expect_error(
            lambda: set_head(root, "release-train", "contract", head_two, head_two, 3),
            "stale expected unit head",
        )
        set_head(root, "release-train", "contract", head_two, orphan_head, 3)
        restored = status(root, "release-train")
        assert restored["units"]["contract"]["head_present"]
        assert not restored["units"]["contract"]["verification_fresh"]
        assert not restored["units"]["contract"]["review_fresh"]
        assert set(status(root, "release-train", "contract")["units"]) == {"contract"}
        assert "objective" not in status(root, "release-train", brief=True)

        append_inbox(
            root, "release-train", "worker-update", "old assignment", "contract", head_two,
            "Worker Contract", "worktree-contract", 3,
        )
        append_inbox(
            root, "release-train", "coordinator", "global event", None, None,
            coordinator_identity="Integration Owner",
        )
        reassigned = assign_unit(
            root, "release-train", "contract", "Worker Contract Two", "worktree-contract", 3
        )
        assert reassigned["units"]["contract"]["assignment"]["generation"] == 4
        assert reassigned["units"]["contract"]["verification"] is None
        assert reassigned["units"]["contract"]["review"] is None
        assert reassigned["units"]["contract"]["state"] == "pending"
        assert [event["summary"] for event in reassigned["inbox"]] == ["global event"]
        expect_error(
            lambda: set_head(root, "release-train", "contract", head_two, head_two, 3),
            "stale assignment generation",
        )
        expect_error(
            lambda: set_unit_state(root, "release-train", "contract", "running", 3),
            "stale assignment generation",
        )
        expect_error(
            lambda: record_verdict(
                root, "release-train", "contract", "verification", "pass",
                head_two, "Verifier", evidence, 3,
            ),
            "stale assignment generation",
        )
        expect_error(
            lambda: append_inbox(
                root, "release-train", "worker-update", "stale replay", "contract", head_two,
                "Worker Contract", "worktree-contract", 3,
            ),
            "stale assignment generation",
        )

        rebound_receipt = json.loads(json.dumps(parallel_receipt))
        rebound_receipt["isolation_identities"] = {
            "contract": "worktree-contract-v2",
            "consumer": "worktree-consumer-v2",
        }
        rebound_path = root / "rebound-parallel-gate.json"
        rebound_path.write_text(json.dumps(rebound_receipt), encoding="utf-8")
        rebound = set_gate(
            root,
            "release-train",
            "dispatch",
            True,
            "isolation rebound",
            rebound_path,
            "Integration Owner",
        )
        assert rebound["units"]["contract"]["assignment"] == empty_assignment(5)
        assert rebound["units"]["consumer"]["assignment"] == empty_assignment(2)
        assert rebound["inbox"] == []
        assert not rebound["gates"]["delivery"]["open"]
        compact = compact_state_receipt(root, load_state(root, "release-train"), "self-test")
        assert "units" not in compact and len(json.dumps(compact)) < 2048
        assert compact["delivery_authority_granted"] is False
        large_state = json.loads(json.dumps(load_state(root, "release-train")))
        prototype = large_state["units"]["contract"]
        large_state["gates"]["dispatch"]["open"] = True
        large_state["units"] = {
            f"unit-{index}": {
                **prototype,
                "id": f"unit-{index}",
                "depends_on": [],
                "state": "pending",
                "head_sha": None,
                "verification": None,
                "review": None,
            }
            for index in range(1000)
        }
        large_receipt = compact_state_receipt(root, large_state, "large-self-test")
        assert large_receipt["frontier_count"] == 1000
        assert large_receipt["frontier_truncated"] and len(json.dumps(large_receipt)) < 2048

        directory = program_directory(root, "release-train")
        lock = directory / ".lock"
        lock.write_text("occupied\n", encoding="utf-8")
        expect_error(lambda: append_inbox(root, "release-train", "note", "blocked", None, None), "locked")
        assert inspect_lock(root, "release-train")["state"] == "invalid"
        expect_error(lambda: recover_stale_lock(root, "release-train"), "not safely recoverable")
        lock.unlink()
        lock.write_text(
            json.dumps(
                {
                    "pid": 99999999,
                    "host": socket.gethostname(),
                    "created_at": now(),
                    "token": "d" * (MAX_LOCK_BYTES + 1),
                }
            ),
            encoding="utf-8",
        )
        large_lock_status = inspect_lock(root, "release-train")
        assert large_lock_status == {
            "path": str(lock),
            "state": "invalid",
            "recoverable": False,
        }
        lock.unlink()
        lock.write_text(
            json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": now(), "token": "a" * 32}),
            encoding="utf-8",
        )
        assert inspect_lock(root, "release-train")["state"] == "live"
        expect_error(lambda: recover_stale_lock(root, "release-train"), "not safely recoverable")
        lock.write_text(
            json.dumps({"pid": 99999999, "host": socket.gethostname(), "created_at": now(), "token": "b" * 32}),
            encoding="utf-8",
        )
        assert inspect_lock(root, "release-train")["recoverable"]
        recover_stale_lock(root, "release-train")
        assert not lock.exists()

        lock.write_text(
            json.dumps({"pid": 99999999, "host": socket.gethostname(), "created_at": now(), "token": "e" * 32}),
            encoding="utf-8",
        )
        original_snapshot = _inspect_lock_snapshot

        def replace_after_snapshot(
            observed_root: Path,
            observed_program_id: str,
        ) -> tuple[dict[str, Any], tuple[int, int] | None]:
            observation, identity = original_snapshot(observed_root, observed_program_id)
            replacement = lock.with_name(".replacement-live-lock")
            replacement.write_text(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "host": socket.gethostname(),
                        "created_at": now(),
                        "token": "f" * 32,
                    }
                ),
                encoding="utf-8",
            )
            os.replace(replacement, lock)
            return observation, identity

        globals()["_inspect_lock_snapshot"] = replace_after_snapshot
        try:
            expect_error(
                lambda: recover_stale_lock(root, "release-train"),
                "identity changed",
            )
        finally:
            globals()["_inspect_lock_snapshot"] = original_snapshot
        assert lock.exists(), "recovery removed a replacement live lock"
        lock.unlink()

        with program_lock(root, "release-train"):
            lock.write_text(
                json.dumps(
                    {
                        "pid": 99999999,
                        "host": socket.gethostname(),
                        "created_at": now(),
                        "token": "c" * 32,
                    }
                ),
                encoding="utf-8",
            )
        assert lock.exists(), "program owner removed a replacement lock it did not own"
        recover_stale_lock(root, "release-train")

        initialize(root, "legacy-program", plan_path)
        legacy_state = load_state(root, "legacy-program")
        legacy_state["schema_version"] = LEGACY_SCHEMA_VERSION
        legacy_state.pop("dispatch_binding")
        legacy_timestamp = now()
        legacy_evidence = evidence_binding(evidence)
        for unit in legacy_state["units"].values():
            unit.pop("assignment")
        legacy_contract = legacy_state["units"]["contract"]
        legacy_contract["state"] = "completed"
        legacy_contract["head_sha"] = head_two
        legacy_contract["verification"] = {
            "actor": "Legacy Verifier",
            "verdict": "pass",
            "head_sha": head_two,
            "evidence": legacy_evidence,
            "recorded_at": legacy_timestamp,
        }
        legacy_contract["review"] = {
            "actor": "Legacy Reviewer",
            "verdict": "pass",
            "head_sha": head_two,
            "evidence": legacy_evidence,
            "recorded_at": legacy_timestamp,
        }
        legacy_state["inbox"] = [
            {
                "sequence": 1,
                "kind": "worker-update",
                "unit_id": "contract",
                "summary": "legacy handoff",
                "head_sha": head_two,
                "recorded_at": legacy_timestamp,
            }
        ]
        legacy_state["inbox_sequence"] = 1
        atomic_write_json(state_path(root, "legacy-program"), legacy_state)
        expect_error(lambda: status(root, "legacy-program"), "legacy schema v1")
        expect_error(
            lambda: migrate_v1(root, "legacy-program", False),
            "--invalidate-legacy-evidence",
        )
        migrated = migrate_v1(root, "legacy-program", True)
        assert migrated["schema_version"] == SCHEMA_VERSION
        assert migrated["dispatch_binding"] is None
        assert not migrated["gates"]["dispatch"]["open"]
        assert not migrated["gates"]["delivery"]["open"]
        assert migrated["inbox"] == [] and migrated["inbox_sequence"] == 1
        assert migrated["units"]["contract"]["head_sha"] == head_two
        assert all(unit["state"] == "pending" for unit in migrated["units"].values())
        assert all(unit["verification"] is None for unit in migrated["units"].values())
        assert all(unit["review"] is None for unit in migrated["units"].values())
        assert all(unit["assignment"] == empty_assignment() for unit in migrated["units"].values())
        assert schema_errors(migrated, root, "legacy-program") == []

        initialize(root, "ancestry-program", plan_path)
        ancestry_state = load_state(root, "ancestry-program")
        ancestry_receipt = {
            **parallel_receipt,
            "program_id": "ancestry-program",
            "plan_digest": ancestry_state["plan_digest"],
        }
        ancestry_receipt_path = root / "ancestry-parallel-gate.json"
        ancestry_receipt_path.write_text(json.dumps(ancestry_receipt), encoding="utf-8")
        set_gate(
            root,
            "ancestry-program",
            "dispatch",
            True,
            "ancestry test",
            ancestry_receipt_path,
            "Integration Owner",
        )
        assign_unit(
            root, "ancestry-program", "contract", "Worker Contract", "worktree-contract", 0
        )
        set_head(root, "ancestry-program", "contract", head_two, None, 1)
        set_unit_state(root, "ancestry-program", "contract", "running", 1)
        record_verdict(
            root, "ancestry-program", "contract", "verification", "pass",
            head_two, "Verifier", evidence, 1,
        )
        record_verdict(
            root, "ancestry-program", "contract", "review", "pass",
            head_two, "Reviewer", evidence, 1,
        )
        set_unit_state(root, "ancestry-program", "contract", "completed", 1)
        assign_unit(
            root, "ancestry-program", "consumer", "Worker Consumer", "worktree-consumer", 0
        )
        expect_error(
            lambda: set_head(
                root, "ancestry-program", "consumer", head_one, None, 1
            ),
            "contain every dependency head",
        )
        set_head(root, "ancestry-program", "consumer", head_two, None, 1)

        stored_path = state_path(root, "release-train")
        valid_bytes = stored_path.read_bytes()
        stored_path.write_text('{"schema_version": 1}\n', encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "legacy schema v1")
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

        malformed = json.loads(valid_bytes)
        owner = malformed["dispatch_binding"]["integration_owner"]
        malformed["dispatch_binding"]["isolation_identities"]["contract"] = owner
        stored_path.write_text(json.dumps(malformed), encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "differ from integration owner")
        stored_path.write_bytes(valid_bytes)

        malformed = json.loads(valid_bytes)
        malformed["units"]["contract"]["assignment"] = {
            "actor": "worker contract",
            "isolation_identity": "worktree-contract-v2",
            "generation": 3,
            "assigned_at": "invalid\ntimestamp",
        }
        stored_path.write_text(json.dumps(malformed), encoding="utf-8")
        expect_error(lambda: status(root, "release-train"), "assignment timestamp is invalid")
        stored_path.write_bytes(valid_bytes)
        expect_error(lambda: status(root, "../escape"), "program id")
        expect_error(
            lambda: set_head(root, "release-train", "contract", "f" * 40, head_two, 3),
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

        parsed = build_parser().parse_args(
            [
                "--program", "release-train", "set-head", "contract", "a" * 40,
                "--expected-head", "none", "--assignment-generation", "3",
            ]
        )
        assert parsed.expected_head == "none" and parsed.assignment_generation == 3
        parsed = build_parser().parse_args(
            [
                "--program", "release-train", "inbox-append", "--kind", "ci",
                "--summary", "queued", "--coordinator", "Integration Owner",
            ]
        )
        assert parsed.coordinator == "Integration Owner"

    print("Patpat program state self-test passed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--program")
    parser.add_argument("--self-test", action="store_true")
    commands = parser.add_subparsers(dest="command")

    initialize_parser = commands.add_parser("init")
    initialize_parser.add_argument("--plan", type=Path, required=True)
    initialize_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    status_parser = commands.add_parser("status")
    status_parser.add_argument("--brief", action="store_true")
    status_parser.add_argument("--unit")
    commands.add_parser("validate")
    commands.add_parser("lock-status")
    commands.add_parser("recover-lock")
    migrate_parser = commands.add_parser("migrate-v1")
    migrate_parser.add_argument("--invalidate-legacy-evidence", action="store_true")
    migrate_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    gate_parser = commands.add_parser("set-gate")
    gate_parser.add_argument("name", choices=sorted(GATE_NAMES))
    gate_parser.add_argument("state", choices=["open", "closed"])
    gate_parser.add_argument("--reason", required=True)
    gate_parser.add_argument("--receipt", type=Path)
    gate_parser.add_argument("--integration-owner")
    gate_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    head_parser = commands.add_parser("set-head")
    head_parser.add_argument("unit_id")
    head_parser.add_argument("head_sha")
    head_parser.add_argument(
        "--expected-head",
        required=True,
        help="Current unit head SHA, or 'none' before the first head is recorded",
    )
    head_parser.add_argument("--assignment-generation", type=int, required=True)
    head_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    assignment_parser = commands.add_parser("assign-unit")
    assignment_parser.add_argument("unit_id")
    assignment_parser.add_argument("--actor", required=True)
    assignment_parser.add_argument("--isolation-identity", required=True)
    assignment_parser.add_argument("--expected-generation", type=int, required=True)
    assignment_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    unit_parser = commands.add_parser("set-unit")
    unit_parser.add_argument("unit_id")
    unit_parser.add_argument("state", choices=sorted(UNIT_STATES))
    unit_parser.add_argument("--assignment-generation", type=int, required=True)
    unit_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    verdict_parser = commands.add_parser("record-verdict")
    verdict_parser.add_argument("unit_id")
    verdict_parser.add_argument("kind", choices=sorted(VERDICT_KINDS))
    verdict_parser.add_argument("verdict", choices=sorted(VERDICTS))
    verdict_parser.add_argument("head_sha")
    verdict_parser.add_argument("--actor", required=True)
    verdict_parser.add_argument("--evidence", type=Path, required=True)
    verdict_parser.add_argument("--assignment-generation", type=int, required=True)
    verdict_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    append_parser = commands.add_parser("inbox-append")
    append_parser.add_argument("--kind", required=True)
    append_parser.add_argument("--summary", required=True)
    append_parser.add_argument("--unit")
    append_parser.add_argument("--head")
    append_parser.add_argument("--actor")
    append_parser.add_argument("--isolation-identity")
    append_parser.add_argument("--assignment-generation", type=int)
    append_parser.add_argument("--coordinator")

    peek_parser = commands.add_parser("inbox-peek")
    peek_parser.add_argument("--after", type=int, default=0)
    peek_parser.add_argument("--limit", type=int, default=10)
    acknowledge_parser = commands.add_parser("inbox-ack")
    acknowledge_parser.add_argument("--through", type=int, required=True)
    acknowledge_parser.add_argument("--coordinator", required=True)
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
            result = status(root, args.program, args.unit, args.brief)
        elif args.command == "validate":
            result = {"valid": True, "program_id": load_state(root, args.program)["program_id"]}
        elif args.command == "lock-status":
            result = inspect_lock(root, args.program)
        elif args.command == "recover-lock":
            result = {"recovered_lock": str(recover_stale_lock(root, args.program))}
        elif args.command == "migrate-v1":
            result = migrate_v1(root, args.program, args.invalidate_legacy_evidence)
        elif args.command == "set-gate":
            result = set_gate(
                root,
                args.program,
                args.name,
                args.state == "open",
                args.reason,
                args.receipt,
                args.integration_owner,
            )
        elif args.command == "set-head":
            expected_head = None if args.expected_head == "none" else args.expected_head
            result = set_head(
                root,
                args.program,
                args.unit_id,
                args.head_sha,
                expected_head,
                args.assignment_generation,
            )
        elif args.command == "assign-unit":
            result = assign_unit(
                root,
                args.program,
                args.unit_id,
                args.actor,
                args.isolation_identity,
                args.expected_generation,
            )
        elif args.command == "set-unit":
            result = set_unit_state(
                root, args.program, args.unit_id, args.state, args.assignment_generation
            )
        elif args.command == "record-verdict":
            result = record_verdict(
                root, args.program, args.unit_id, args.kind, args.verdict,
                args.head_sha, args.actor, args.evidence, args.assignment_generation,
            )
        elif args.command == "inbox-append":
            result = append_inbox(
                root,
                args.program,
                args.kind,
                args.summary,
                args.unit,
                args.head,
                args.actor,
                args.isolation_identity,
                args.assignment_generation,
                args.coordinator,
            )
        elif args.command == "inbox-peek":
            result = peek_inbox(root, args.program, args.after, args.limit)
        elif args.command == "inbox-ack":
            result = acknowledge_inbox(root, args.program, args.through, args.coordinator)
        else:
            parser.error(f"unsupported command: {args.command}")
        full_state_commands = {
            "init", "migrate-v1", "set-gate", "assign-unit", "set-head", "set-unit", "record-verdict"
        }
        if args.command in full_state_commands and not args.full:
            result = compact_state_receipt(root, result, args.command)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ProgramStateError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
