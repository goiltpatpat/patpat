#!/usr/bin/env python3
"""Maintain an atomic, revision-bound Patpat execution graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import tempfile
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator


SCHEMA_VERSION = 2
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RECEIPT_PATTERN = re.compile(r"^file:/.+$")
NODES = {
    "FRAME",
    "INSPECT",
    "PROOF_CONTRACT",
    "ACT",
    "VERIFY",
    "REVIEW",
    "LEARN",
    "REPORT",
    "BLOCKED",
}
TRANSITIONS = {
    "FRAME": {"INSPECT"},
    "INSPECT": {"PROOF_CONTRACT"},
    "PROOF_CONTRACT": {"ACT", "INSPECT"},
    "ACT": {"VERIFY"},
    "VERIFY": {"REVIEW", "ACT", "PROOF_CONTRACT", "INSPECT"},
    "REVIEW": {"LEARN", "REPORT", "ACT", "VERIFY"},
    "LEARN": {"VERIFY", "REPORT"},
    "REPORT": set(),
    "BLOCKED": set(),
}
STATE_KEYS = {
    "schema_version",
    "run_id",
    "objective",
    "owner",
    "repo_root",
    "base_snapshot",
    "node",
    "epoch",
    "authorities",
    "prohibitions",
    "intentional_changes",
    "pre_existing_changes",
    "proof_contract",
    "verification",
    "review",
    "last_failure",
    "blocked_reason",
    "sequence",
    "events",
    "created_at",
    "updated_at",
}


class RunStateError(ValueError):
    """Raised when a run operation violates the graph contract."""


def now() -> str:
    return datetime.now(UTC).isoformat()


def git_process(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
        )
    except OSError as error:
        raise RunStateError(f"git is required for durable runs: {error}") from error


def git_text(root: Path, *args: str) -> str | None:
    result = git_process(root, *args)
    if result.returncode != 0:
        return None
    value = os.fsdecode(result.stdout).strip()
    return value or None


def require_git_root(root: Path) -> str:
    top = git_text(root, "rev-parse", "--show-toplevel")
    head = git_text(root, "rev-parse", "HEAD")
    if not top or not head:
        raise RunStateError("durable runs require a Git worktree with at least one commit")
    if Path(top).resolve() != root.resolve():
        raise RunStateError(f"--root must be the Git worktree root: {Path(top).resolve()}")
    return head


def git_store_root(root: Path) -> Path:
    require_git_root(root)
    raw_path = git_text(root, "rev-parse", "--git-path", "patpat/runs")
    if not raw_path:
        raise RunStateError("Git did not return a Patpat metadata path")
    path = Path(raw_path)
    return (path if path.is_absolute() else root / path).resolve()


def current_snapshot(root: Path) -> str:
    head = require_git_root(root)
    index = git_process(root, "ls-files", "--stage", "-z")
    tracked = git_process(root, "ls-files", "-z")
    if index.returncode != 0 or tracked.returncode != 0:
        raise RunStateError("could not enumerate tracked repository state")
    untracked = git_process(root, "ls-files", "--others", "--exclude-standard", "-z")
    if untracked.returncode != 0:
        raise RunStateError(f"could not list untracked files: {os.fsdecode(untracked.stderr).strip()}")

    digest = hashlib.sha256()
    digest.update(head.encode("ascii"))
    digest.update(b"\0index\0")
    digest.update(index.stdout)
    digest.update(b"\0worktree\0")
    for raw_name in sorted(name for name in tracked.stdout.split(b"\0") if name):
        relative = checked_relative_path(raw_name)
        digest_path(digest, root, relative, raw_name)
    digest.update(b"\0untracked\0")
    for raw_name in sorted(name for name in untracked.stdout.split(b"\0") if name):
        relative = checked_relative_path(raw_name)
        digest_path(digest, root, relative, raw_name)
    return f"git:{head}:{digest.hexdigest()}"


def checked_relative_path(raw_name: bytes) -> Path:
    relative = Path(os.fsdecode(raw_name))
    if relative.is_absolute() or ".." in relative.parts:
        raise RunStateError(f"repository path escapes root: {relative}")
    return relative


def digest_path(digest: Any, root: Path, relative: Path, label: bytes) -> None:
    path = root / relative
    digest.update(label)
    digest.update(b"\0")
    if path.is_symlink():
        digest.update(b"symlink\0")
        digest.update(os.fsencode(os.readlink(path)))
    elif path.is_file():
        digest.update(b"file\0")
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    elif path.is_dir():
        digest.update(b"directory\0")
        for child in sorted(path.rglob("*"), key=lambda item: os.fsencode(item.relative_to(path))):
            if ".git" in child.relative_to(path).parts or child.is_dir():
                continue
            child_label = label + b"/" + os.fsencode(child.relative_to(path))
            digest_path(digest, root, child.relative_to(root), child_label)
    else:
        digest.update(b"missing")
    digest.update(b"\0")


def run_directory(root: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RunStateError("run id must be lowercase kebab-case and at most 64 characters")
    return git_store_root(root) / run_id


def state_path(root: Path, run_id: str) -> Path:
    return run_directory(root, run_id) / "state.json"


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


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
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


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    atomic_write(path, payload)


@contextmanager
def run_lock(root: Path, run_id: str) -> Iterator[None]:
    directory = run_directory(root, run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".lock"
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise RunStateError(f"run is locked; use the unlock command only after confirming its owner stopped: {path}") from error
    try:
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": now(),
        }
        os.write(descriptor, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
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


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def recover_stale_lock(root: Path, run_id: str) -> Path:
    path = run_directory(root, run_id) / ".lock"
    if not path.is_file() or path.is_symlink():
        raise RunStateError("no regular run lock exists")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunStateError(f"lock metadata is invalid; inspect manually: {error}") from error
    if not isinstance(record, dict) or set(record) != {"pid", "host", "created_at"}:
        raise RunStateError("lock metadata is invalid; inspect manually")
    pid = record.get("pid")
    if record.get("host") != socket.gethostname():
        raise RunStateError("lock belongs to another host and cannot be recovered automatically")
    if not isinstance(pid, int) or pid <= 0:
        raise RunStateError("lock pid is invalid; inspect manually")
    if process_is_alive(pid):
        raise RunStateError(f"lock owner pid {pid} is still running")
    path.unlink()
    fsync_directory(path.parent)
    return path


def make_event(state: dict[str, Any], kind: str, summary: str, **details: Any) -> dict[str, Any]:
    sequence = int(state.get("sequence", 0)) + 1
    return {
        "id": str(uuid.uuid4()),
        "sequence": sequence,
        "time": now(),
        "kind": kind,
        "summary": summary,
        "node": state["node"],
        "epoch": state["epoch"],
        **{key: value for key, value in details.items() if value is not None},
    }


def append_state_event(state: dict[str, Any], kind: str, summary: str, **details: Any) -> None:
    event = make_event(state, kind, summary, **details)
    state["events"].append(event)
    state["sequence"] = event["sequence"]
    state["updated_at"] = now()


def canonical_identity(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RunStateError(f"{label} must be a non-empty identity without outer whitespace")
    if unicodedata.normalize("NFKC", value) != value:
        raise RunStateError(f"{label} must use canonical Unicode form")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise RunStateError(f"{label} must not contain control characters")
    return value.casefold()


def file_binding(path: Path) -> dict[str, Any]:
    if not path.is_absolute() or path != path.resolve() or not path.is_file() or path.is_symlink():
        raise RunStateError("file receipt must be an existing absolute regular file without symlinks")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    stat = path.stat()
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size": stat.st_size,
    }


def validate_receipt(receipt: str) -> dict[str, Any]:
    if not RECEIPT_PATTERN.fullmatch(receipt):
        raise RunStateError("receipt must use file:/absolute/path to an inspectable evidence file")
    return file_binding(Path(receipt.removeprefix("file:")))


def receipt_binding_is_fresh(record: dict[str, Any]) -> bool:
    binding = record.get("binding")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256", "size"}:
        return False
    try:
        receipt_binding = validate_receipt(record.get("receipt"))
        return receipt_binding == binding and receipt_binding["path"] == binding["path"]
    except (OSError, RunStateError, TypeError):
        return False


def receipt_is_fresh(
    record: Any,
    state: dict[str, Any],
    snapshot: str,
    verdict: str,
    *,
    independent: bool = False,
) -> bool:
    if not isinstance(record, dict):
        return False
    try:
        actor_key = canonical_identity(record.get("actor"), "receipt actor")
        owner_key = canonical_identity(state.get("owner"), "integration owner")
    except RunStateError:
        return False
    return (
        record.get("snapshot") == snapshot
        and record.get("epoch") == state.get("epoch")
        and record.get("verdict") == verdict
        and isinstance(record.get("receipt"), str)
        and (not independent or actor_key != owner_key)
        and receipt_binding_is_fresh(record)
    )


def schema_errors(state: dict[str, Any], root: Path, run_id: str) -> list[str]:
    errors: list[str] = []
    if set(state) != STATE_KEYS:
        errors.append("state fields do not match schema")
    if state.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema version")
    if state.get("run_id") != run_id:
        errors.append("stored run id does not match requested run")
    if state.get("repo_root") != str(root.resolve()):
        errors.append("stored repository root does not match requested root")
    if state.get("node") not in NODES:
        errors.append("invalid graph node")
    if not isinstance(state.get("objective"), str) or not state.get("objective"):
        errors.append("objective is required")
    try:
        canonical_identity(state.get("owner"), "integration owner")
    except RunStateError as error:
        errors.append(str(error))
    for key in ("authorities", "prohibitions", "intentional_changes", "pre_existing_changes", "events"):
        if not isinstance(state.get(key), list):
            errors.append(f"{key} must be a list")
        elif key != "events" and not all(isinstance(item, str) and item for item in state[key]):
            errors.append(f"{key} entries must be non-empty strings")
    if (
        isinstance(state.get("authorities"), list)
        and isinstance(state.get("prohibitions"), list)
        and all(isinstance(item, str) for item in state["authorities"] + state["prohibitions"])
    ):
        conflict = set(state["authorities"]) & set(state["prohibitions"])
        if conflict:
            errors.append(f"authority conflicts with prohibition: {sorted(conflict)}")
    if not isinstance(state.get("epoch"), int) or state.get("epoch", -1) < 0:
        errors.append("epoch must be a non-negative integer")
    if not isinstance(state.get("sequence"), int) or state.get("sequence", -1) < 1:
        errors.append("sequence must be a positive integer")
    events = state.get("events")
    if isinstance(events, list):
        if not events:
            errors.append("event history is required")
        elif not all(isinstance(event, dict) for event in events):
            errors.append("every event must be an object")
        else:
            expected = list(range(1, len(events) + 1))
            observed = [event.get("sequence") for event in events]
            if observed != expected or state.get("sequence") != expected[-1]:
                errors.append("event sequence is invalid")
            if events[-1].get("node") != state.get("node"):
                errors.append("last event node does not match state")
    return errors


def load_state(root: Path, run_id: str) -> dict[str, Any]:
    path = state_path(root, run_id)
    if not path.is_file():
        raise RunStateError(f"run does not exist: {run_id}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RunStateError(f"invalid state file: {error}") from error
    if not isinstance(value, dict):
        raise RunStateError("state root must be an object")
    errors = schema_errors(value, root, run_id)
    if errors:
        raise RunStateError("; ".join(errors))
    return value


def save_state(root: Path, run_id: str, state: dict[str, Any]) -> None:
    errors = schema_errors(state, root, run_id)
    if errors:
        raise RunStateError("; ".join(errors))
    try:
        atomic_write_json(state_path(root, run_id), state)
    except OSError as error:
        raise RunStateError(f"could not persist atomic run state: {error}") from error


def initialize(
    root: Path,
    run_id: str,
    objective: str,
    owner: str,
    authorities: list[str],
    prohibitions: list[str],
    intentional_changes: list[str],
    pre_existing_changes: list[str],
) -> dict[str, Any]:
    canonical_identity(owner, "integration owner")
    for label, values in {
        "authorities": authorities,
        "prohibitions": prohibitions,
        "intentional changes": intentional_changes,
        "pre-existing changes": pre_existing_changes,
    }.items():
        if not all(isinstance(value, str) and value for value in values):
            raise RunStateError(f"{label} entries must be non-empty strings")
    conflict = set(authorities) & set(prohibitions)
    if conflict:
        raise RunStateError(f"authority conflicts with prohibition: {sorted(conflict)}")
    with run_lock(root, run_id):
        path = state_path(root, run_id)
        if path.exists():
            raise RunStateError(f"run already exists: {run_id}")
        timestamp = now()
        state: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "objective": objective,
            "owner": owner,
            "repo_root": str(root.resolve()),
            "base_snapshot": current_snapshot(root),
            "node": "FRAME",
            "epoch": 0,
            "authorities": sorted(set(authorities)),
            "prohibitions": sorted(set(prohibitions)),
            "intentional_changes": intentional_changes,
            "pre_existing_changes": pre_existing_changes,
            "proof_contract": None,
            "verification": None,
            "review": None,
            "last_failure": None,
            "blocked_reason": None,
            "sequence": 0,
            "events": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        append_state_event(state, "init", objective)
        save_state(root, run_id, state)
        return state


def transition(root: Path, run_id: str, destination: str) -> dict[str, Any]:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        source = state["node"]
        if destination not in NODES or destination not in TRANSITIONS[source]:
            raise RunStateError(f"illegal graph transition: {source} -> {destination}")
        snapshot = current_snapshot(root)
        if destination == "ACT" and not state["proof_contract"]:
            raise RunStateError("ACT requires a structured proof contract")
        if destination == "REVIEW" and not receipt_is_fresh(state["verification"], state, snapshot, "verified"):
            raise RunStateError("REVIEW requires verified evidence for the current epoch and snapshot")
        if destination == "LEARN" and not receipt_is_fresh(
            state["review"], state, snapshot, "pass", independent=True
        ):
            raise RunStateError("LEARN requires current independent review")
        if destination == "REPORT":
            if not receipt_is_fresh(state["verification"], state, snapshot, "verified"):
                raise RunStateError("REPORT requires current verified evidence")
            if not receipt_is_fresh(state["review"], state, snapshot, "pass", independent=True):
                raise RunStateError("REPORT requires current independent review")
        if destination in {"ACT", "VERIFY"}:
            state["epoch"] += 1
            state["verification"] = None
            state["review"] = None
        state["node"] = destination
        state["last_failure"] = None
        append_state_event(state, "transition", f"{source} -> {destination}", snapshot=snapshot)
        save_state(root, run_id, state)
        return state


def record_proof_contract(root: Path, run_id: str, fields: dict[str, str]) -> dict[str, Any]:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] not in {"INSPECT", "PROOF_CONTRACT"}:
            raise RunStateError("proof contract must be recorded during INSPECT or PROOF_CONTRACT")
        if not all(fields.values()):
            raise RunStateError("proof contract requires claim, surface, action, expected observation, and cleanup")
        state["proof_contract"] = {**fields, "recorded_at": now()}
        state["last_failure"] = None
        append_state_event(state, "proof-contract", fields["claim"], snapshot=current_snapshot(root))
        save_state(root, run_id, state)
        return state


def record_receipt(
    root: Path,
    run_id: str,
    kind: str,
    summary: str,
    receipt: str,
    actor: str,
    verdict: str,
) -> dict[str, Any]:
    binding = validate_receipt(receipt)
    actor_key = canonical_identity(actor, f"{kind} actor")
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        expected_node = "VERIFY" if kind == "verification" else "REVIEW"
        if state["node"] != expected_node:
            raise RunStateError(f"{kind} receipt requires {expected_node} state")
        allowed = {"verification": {"verified", "partial", "failed"}, "review": {"pass", "changes-required"}}
        if verdict not in allowed[kind]:
            raise RunStateError(f"invalid {kind} verdict")
        if kind == "review" and actor_key == canonical_identity(state["owner"], "integration owner"):
            raise RunStateError("independent reviewer must differ from the integration owner")
        snapshot = current_snapshot(root)
        state[kind] = {
            "summary": summary,
            "receipt": receipt,
            "binding": binding,
            "actor": actor,
            "verdict": verdict,
            "snapshot": snapshot,
            "epoch": state["epoch"],
            "recorded_at": now(),
        }
        if kind == "verification":
            state["review"] = None
        state["last_failure"] = None
        append_state_event(
            state,
            kind,
            summary,
            snapshot=snapshot,
            receipt=receipt,
            binding=binding,
            actor=actor,
            verdict=verdict,
        )
        save_state(root, run_id, state)
        return state


def record_experiment(
    root: Path,
    run_id: str,
    hypothesis: str,
    metric: str,
    value: str,
    unit: str,
    receipt: str,
    actor: str,
    verdict: str,
    next_decision: str,
) -> dict[str, Any]:
    fields = {
        "hypothesis": hypothesis,
        "metric": metric,
        "value": value,
        "unit": unit,
        "next decision": next_decision,
    }
    if not all(isinstance(item, str) and item.strip() for item in fields.values()):
        raise RunStateError("experiment fields must be non-empty strings")
    if verdict not in {"keep", "revert"}:
        raise RunStateError("experiment verdict must be keep or revert")
    canonical_identity(actor, "experiment actor")
    binding = validate_receipt(receipt)
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] != "VERIFY":
            raise RunStateError("experiment record requires VERIFY state")
        snapshot = current_snapshot(root)
        state["last_failure"] = None
        append_state_event(
            state,
            "experiment",
            hypothesis,
            snapshot=snapshot,
            hypothesis=hypothesis,
            metric=metric,
            value=value,
            unit=unit,
            receipt=receipt,
            binding=binding,
            actor=actor,
            verdict=verdict,
            next_decision=next_decision,
        )
        save_state(root, run_id, state)
        return state


def record_decision(root: Path, run_id: str, summary: str) -> dict[str, Any]:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] in {"REPORT", "BLOCKED"}:
            raise RunStateError(f"cannot record into terminal node {state['node']}")
        state["last_failure"] = None
        append_state_event(state, "decision", summary, snapshot=current_snapshot(root))
        save_state(root, run_id, state)
        return state


def record_failure(root: Path, run_id: str, summary: str, blocker_key: str) -> dict[str, Any]:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] in {"REPORT", "BLOCKED"}:
            raise RunStateError(f"cannot record into terminal node {state['node']}")
        snapshot = current_snapshot(root)
        previous = state["last_failure"]
        unchanged = (
            isinstance(previous, dict)
            and previous.get("key") == blocker_key
            and previous.get("snapshot") == snapshot
            and previous.get("node") == state["node"]
        )
        count = int(previous["count"]) + 1 if unchanged else 1
        state["last_failure"] = {
            "key": blocker_key,
            "snapshot": snapshot,
            "node": state["node"],
            "count": count,
        }
        if count >= 3:
            state["node"] = "BLOCKED"
            state["blocked_reason"] = blocker_key
        append_state_event(state, "failure", summary, snapshot=snapshot, blocker_key=blocker_key, count=count)
        save_state(root, run_id, state)
        return state


def validation_errors(root: Path, run_id: str) -> list[str]:
    try:
        state = load_state(root, run_id)
    except RunStateError as error:
        return [str(error)]
    errors = schema_errors(state, root, run_id)
    snapshot = current_snapshot(root)
    if state["node"] in {"ACT", "VERIFY", "REVIEW", "LEARN", "REPORT"} and not state["proof_contract"]:
        errors.append("active run is missing a proof contract")
    if state["node"] in {"REVIEW", "LEARN", "REPORT"} and not receipt_is_fresh(state["verification"], state, snapshot, "verified"):
        errors.append("verification is missing or stale")
    if state["node"] in {"LEARN", "REPORT"} and not receipt_is_fresh(
        state["review"], state, snapshot, "pass", independent=True
    ):
        errors.append("review is missing or stale")
    for event in state.get("events", []):
        if not isinstance(event, dict) or event.get("kind") != "experiment":
            continue
        required = {
            "hypothesis", "metric", "value", "unit", "receipt", "binding",
            "actor", "verdict", "next_decision", "snapshot",
        }
        if not required.issubset(event) or event.get("verdict") not in {"keep", "revert"}:
            errors.append("experiment history is malformed")
        elif not receipt_binding_is_fresh(event):
            errors.append(f"experiment evidence is stale: event {event.get('sequence')}")
    return errors


def checkpoint(root: Path, run_id: str) -> Path:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        snapshot = current_snapshot(root)
        lines = [
            f"# Patpat Run: {run_id}",
            "",
            f"- Objective: {state['objective']}",
            f"- Integration owner: {state['owner']}",
            f"- Graph node: {state['node']}",
            f"- Repository: {state['repo_root']}",
            f"- Base snapshot: {state['base_snapshot']}",
            f"- Current snapshot: {snapshot}",
            f"- Authorities: {', '.join(state['authorities']) or 'none'}",
            f"- Prohibitions: {', '.join(state['prohibitions']) or 'none'}",
            "",
            "## Proof state",
            "",
            f"- Proof contract: {json.dumps(state['proof_contract'], sort_keys=True)}",
            f"- Verification: {json.dumps(state['verification'], sort_keys=True)}",
            f"- Review: {json.dumps(state['review'], sort_keys=True)}",
            "",
            "## Working tree boundary",
            "",
            f"- Intentional changes: {', '.join(state['intentional_changes']) or 'none recorded'}",
            f"- Pre-existing changes: {', '.join(state['pre_existing_changes']) or 'none recorded'}",
            "",
            "## Recent events",
            "",
        ]
        for event in state["events"][-10:]:
            lines.append(f"- {event['time']} | {event['kind']} | {event['summary']}")
        path = run_directory(root, run_id) / "handoff.md"
        atomic_write(path, ("\n".join(lines) + "\n").encode("utf-8"))
        return path


def status(root: Path, run_id: str) -> dict[str, Any]:
    state = load_state(root, run_id)
    snapshot = current_snapshot(root)
    return {
        "store": str(run_directory(root, run_id)),
        "run_id": run_id,
        "objective": state["objective"],
        "node": state["node"],
        "epoch": state["epoch"],
        "current_snapshot": snapshot,
        "verification_stale": bool(state["verification"]) and not receipt_is_fresh(state["verification"], state, snapshot, "verified"),
        "review_stale": bool(state["review"]) and not receipt_is_fresh(
            state["review"], state, snapshot, "pass", independent=True
        ),
        "errors": validation_errors(root, run_id),
    }


def make_test_repository(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "patpat@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Patpat Test"], check=True)
    (root / "source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)


def run_self_test() -> None:
    with (
        tempfile.TemporaryDirectory(prefix="patpat-run-state-") as directory,
        tempfile.TemporaryDirectory(prefix="patpat-run-evidence-") as evidence_directory,
    ):
        root = Path(directory)
        evidence_root = Path(evidence_directory)

        def evidence(name: str) -> str:
            path = evidence_root / f"{name}.txt"
            path.write_text(f"evidence for {name}\n", encoding="utf-8")
            return f"file:{path.resolve()}"

        verification_receipt = evidence("verification")
        self_review_receipt = evidence("self-review")
        review_receipt = evidence("review")
        learning_verification_receipt = evidence("learning-verification")
        learning_review_receipt = evidence("learning-review")
        experiment_receipt = evidence("experiment")
        make_test_repository(root)
        initialize(root, "main-run", "Prove state transitions", "integration-owner", ["open-pr"], ["deploy"], ["source.txt"], [])
        try:
            transition(root, "main-run", "ACT")
        except RunStateError:
            pass
        else:
            raise AssertionError("ACT was accepted without a proof contract")
        transition(root, "main-run", "INSPECT")
        transition(root, "main-run", "PROOF_CONTRACT")
        record_proof_contract(
            root,
            "main-run",
            {
                "claim": "The changed behavior is observable",
                "surface": "test fixture",
                "action": "exercise fixture",
                "expected": "expected value appears",
                "cleanup": "remove temporary evidence",
            },
        )
        transition(root, "main-run", "ACT")
        transition(root, "main-run", "VERIFY")
        record_experiment(
            root,
            "main-run",
            "A smaller buffer improves the target metric",
            "latency",
            "12.5",
            "ms",
            experiment_receipt,
            "integration-owner",
            "keep",
            "verify the retained state",
        )
        record_receipt(root, "main-run", "verification", "Behavior observed", verification_receipt, "integration-owner", "verified")
        transition(root, "main-run", "REVIEW")
        try:
            record_receipt(root, "main-run", "review", "Self review", self_review_receipt, "integration-owner", "pass")
        except RunStateError:
            pass
        else:
            raise AssertionError("owner was accepted as independent reviewer")
        try:
            record_receipt(root, "main-run", "review", "Whitespace alias", review_receipt, " integration-owner", "pass")
        except RunStateError:
            pass
        else:
            raise AssertionError("whitespace reviewer alias bypassed independence")
        record_receipt(root, "main-run", "review", "Independent review passed", review_receipt, "reviewer", "pass")
        transition(root, "main-run", "LEARN")
        transition(root, "main-run", "VERIFY")
        try:
            transition(root, "main-run", "REVIEW")
        except RunStateError:
            pass
        else:
            raise AssertionError("old verification crossed an epoch boundary")
        record_receipt(root, "main-run", "verification", "Learning verified", learning_verification_receipt, "integration-owner", "verified")
        transition(root, "main-run", "REVIEW")
        record_receipt(root, "main-run", "review", "Learning reviewed", learning_review_receipt, "reviewer", "pass")
        transition(root, "main-run", "REPORT")
        if not checkpoint(root, "main-run").is_file():
            raise AssertionError("checkpoint was not created")

        receipt_path = Path(learning_review_receipt.removeprefix("file:"))
        receipt_content = receipt_path.read_bytes()
        receipt_path.unlink()
        if not status(root, "main-run")["review_stale"]:
            raise AssertionError("deleted receipt remained fresh")
        receipt_path.write_bytes(receipt_content)
        receipt_path.write_text("modified evidence\n", encoding="utf-8")
        if not status(root, "main-run")["review_stale"]:
            raise AssertionError("modified receipt remained fresh")
        receipt_path.write_bytes(receipt_content)

        experiment_path = Path(experiment_receipt.removeprefix("file:"))
        experiment_content = experiment_path.read_bytes()
        experiment_path.write_text("tampered historical measurement\n", encoding="utf-8")
        if not any(
            "experiment evidence is stale" in error
            for error in validation_errors(root, "main-run")
        ):
            raise AssertionError("stale historical experiment evidence was accepted")
        experiment_path.write_bytes(experiment_content)

        main_state_path = state_path(root, "main-run")
        untampered_main = main_state_path.read_bytes()
        tampered_receipt = load_state(root, "main-run")
        tampered_receipt["review"]["receipt"] = "artifact:bogus"
        atomic_write_json(main_state_path, tampered_receipt)
        if not validation_errors(root, "main-run"):
            raise AssertionError("receipt URI diverged from its content binding")
        atomic_write(main_state_path, untampered_main)
        tampered_reviewer = load_state(root, "main-run")
        tampered_reviewer["review"]["actor"] = "integration-owner"
        atomic_write_json(main_state_path, tampered_reviewer)
        if not validation_errors(root, "main-run"):
            raise AssertionError("tampered reviewer identity was accepted")
        atomic_write(main_state_path, untampered_main)

        (root / "source.txt").write_text("dirty\n", encoding="utf-8")
        stale = status(root, "main-run")
        if not stale["verification_stale"] or not stale["review_stale"]:
            raise AssertionError("dirty working tree did not invalidate receipts")
        (root / "source.txt").write_text("one\n", encoding="utf-8")

        before_assume_unchanged = current_snapshot(root)
        subprocess.run(
            ["git", "-C", str(root), "update-index", "--assume-unchanged", "source.txt"],
            check=True,
        )
        (root / "source.txt").write_text("hidden dirty state\n", encoding="utf-8")
        if current_snapshot(root) == before_assume_unchanged:
            raise AssertionError("assume-unchanged content bypassed the snapshot")
        (root / "source.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(root), "update-index", "--no-assume-unchanged", "source.txt"],
            check=True,
        )

        nested = root / "nested"
        nested.mkdir()
        make_test_repository(nested)
        before_nested_change = current_snapshot(root)
        (nested / "source.txt").write_text("nested dirty state\n", encoding="utf-8")
        if current_snapshot(root) == before_nested_change:
            raise AssertionError("embedded Git repository content bypassed the snapshot")

        initialize(root, "blocked-run", "Bound retries", "owner", [], [], [], [])
        transition(root, "blocked-run", "INSPECT")
        record_failure(root, "blocked-run", "Same blocker", "missing-runtime")
        (root / "new.txt").write_text("new evidence\n", encoding="utf-8")
        record_failure(root, "blocked-run", "Changed snapshot", "missing-runtime")
        if load_state(root, "blocked-run")["last_failure"]["count"] != 1:
            raise AssertionError("blocker count did not reset after snapshot change")
        for _ in range(2):
            record_failure(root, "blocked-run", "Same blocker", "missing-runtime")
        if load_state(root, "blocked-run")["node"] != "BLOCKED":
            raise AssertionError("third unchanged blocker did not stop the run")

        try:
            initialize(root, "conflict-run", "Reject conflicts", "owner", ["deploy"], ["deploy"], [], [])
        except RunStateError:
            pass
        else:
            raise AssertionError("authority and prohibition conflict was accepted")

        initialize(root, "atomic-run", "Preserve atomic state", "owner", [], [], [], [])
        atomic_path = state_path(root, "atomic-run")
        before_failure = atomic_path.read_bytes()
        original_replace = os.replace

        def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
            del source, destination
            raise OSError("simulated replace failure")

        os.replace = fail_replace
        try:
            try:
                transition(root, "atomic-run", "INSPECT")
            except RunStateError:
                pass
            else:
                raise AssertionError("simulated persistence failure was accepted")
        finally:
            os.replace = original_replace
        if atomic_path.read_bytes() != before_failure:
            raise AssertionError("failed atomic write changed authoritative state")

        lock_path = run_directory(root, "atomic-run") / ".lock"
        lock_path.write_text(
            json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": now()}),
            encoding="utf-8",
        )
        try:
            try:
                transition(root, "atomic-run", "INSPECT")
            except RunStateError:
                pass
            else:
                raise AssertionError("concurrent run lock was ignored")
            try:
                recover_stale_lock(root, "atomic-run")
            except RunStateError:
                pass
            else:
                raise AssertionError("live run lock was recovered")
        finally:
            lock_path.write_text(
                json.dumps({"pid": 99999999, "host": socket.gethostname(), "created_at": now()}),
                encoding="utf-8",
            )
        recover_stale_lock(root, "atomic-run")
        if lock_path.exists():
            raise AssertionError("stale run lock was not recovered")

        malformed = load_state(root, "atomic-run")
        malformed["authorities"] = [{}]
        atomic_write_json(state_path(root, "atomic-run"), malformed)
        if not validation_errors(root, "atomic-run"):
            raise AssertionError("non-string authority was accepted")

        tampered = load_state(root, "main-run")
        tampered["run_id"] = "other-run"
        atomic_write_json(state_path(root, "main-run"), tampered)
        if not validation_errors(root, "main-run"):
            raise AssertionError("identity tamper was accepted")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--root", type=Path, default=Path.cwd())
    init_parser.add_argument("--run-id", required=True)
    init_parser.add_argument("--objective", required=True)
    init_parser.add_argument("--owner", required=True)
    init_parser.add_argument("--authority", action="append", default=[])
    init_parser.add_argument("--prohibition", action="append", default=[])
    init_parser.add_argument("--intentional-change", action="append", default=[])
    init_parser.add_argument("--pre-existing-change", action="append", default=[])

    for command in ("transition", "record", "checkpoint", "status", "validate", "unlock"):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--root", type=Path, default=Path.cwd())
        command_parser.add_argument("--run-id", required=True)
        if command == "transition":
            command_parser.add_argument("--to", required=True, choices=sorted(NODES))
        elif command == "record":
            command_parser.add_argument(
                "--kind",
                required=True,
                choices=("proof-contract", "verification", "review", "experiment", "decision", "failure"),
            )
            command_parser.add_argument("--summary")
            command_parser.add_argument("--receipt")
            command_parser.add_argument("--actor")
            command_parser.add_argument("--verdict")
            command_parser.add_argument("--blocker-key")
            command_parser.add_argument("--claim")
            command_parser.add_argument("--surface")
            command_parser.add_argument("--action")
            command_parser.add_argument("--expected")
            command_parser.add_argument("--cleanup")
            command_parser.add_argument("--hypothesis")
            command_parser.add_argument("--metric")
            command_parser.add_argument("--value")
            command_parser.add_argument("--unit")
            command_parser.add_argument("--next-decision")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        print("Patpat run-state self-test passed.")
        return 0
    if not args.command:
        parser.error("a command or --self-test is required")
    root = args.root.resolve()
    if not root.is_dir():
        print(f"Patpat run-state error: repository root is not a directory: {root}")
        return 2
    try:
        if args.command == "init":
            state = initialize(root, args.run_id, args.objective, args.owner, args.authority, args.prohibition, args.intentional_change, args.pre_existing_change)
            print(json.dumps({"store": str(run_directory(root, args.run_id)), "state": state}, indent=2))
        elif args.command == "transition":
            print(json.dumps(transition(root, args.run_id, args.to), indent=2))
        elif args.command == "record":
            if args.kind == "proof-contract":
                state = record_proof_contract(root, args.run_id, {"claim": args.claim, "surface": args.surface, "action": args.action, "expected": args.expected, "cleanup": args.cleanup})
            elif args.kind in {"verification", "review"}:
                if not all((args.summary, args.receipt, args.actor, args.verdict)):
                    raise RunStateError(f"{args.kind} requires summary, receipt, actor, and verdict")
                state = record_receipt(root, args.run_id, args.kind, args.summary, args.receipt, args.actor, args.verdict)
            elif args.kind == "experiment":
                required = (
                    args.hypothesis,
                    args.metric,
                    args.value,
                    args.unit,
                    args.receipt,
                    args.actor,
                    args.verdict,
                    args.next_decision,
                )
                if not all(required):
                    raise RunStateError(
                        "experiment requires hypothesis, metric, value, unit, receipt, actor, verdict, and next decision"
                    )
                state = record_experiment(
                    root,
                    args.run_id,
                    args.hypothesis,
                    args.metric,
                    args.value,
                    args.unit,
                    args.receipt,
                    args.actor,
                    args.verdict,
                    args.next_decision,
                )
            elif args.kind == "failure":
                if not args.summary or not args.blocker_key:
                    raise RunStateError("failure requires summary and blocker key")
                state = record_failure(root, args.run_id, args.summary, args.blocker_key)
            else:
                if not args.summary:
                    raise RunStateError("decision requires summary")
                state = record_decision(root, args.run_id, args.summary)
            print(json.dumps(state, indent=2))
        elif args.command == "checkpoint":
            path = checkpoint(root, args.run_id)
            print(json.dumps({"store": str(run_directory(root, args.run_id)), "checkpoint": str(path)}, indent=2))
        elif args.command == "status":
            print(json.dumps(status(root, args.run_id), indent=2))
        elif args.command == "validate":
            errors = validation_errors(root, args.run_id)
            print(json.dumps({"store": str(run_directory(root, args.run_id)), "errors": errors}, indent=2))
            return 1 if errors else 0
        elif args.command == "unlock":
            path = recover_stale_lock(root, args.run_id)
            print(json.dumps({"recovered_lock": str(path)}, indent=2))
    except RunStateError as error:
        print(f"Patpat run-state error: {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
