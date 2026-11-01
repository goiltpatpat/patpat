#!/usr/bin/env python3
"""Maintain an atomic, revision-bound Patpat execution graph."""

from __future__ import annotations

import argparse
import errno
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
from datetime import UTC, datetime, timedelta
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

SHIP_SCRIPTS_DIRECTORY = str(Path(__file__).resolve().parents[2] / "patpat-ship" / "scripts")
if SHIP_SCRIPTS_DIRECTORY not in sys.path:
    sys.path.insert(0, SHIP_SCRIPTS_DIRECTORY)

import pr_watch


SCHEMA_VERSION = 2
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
LOCK_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")
MAX_LOCK_BYTES = 4096
MAX_STATE_BYTES = 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
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
    "REVIEW": {"LEARN", "REPORT", "ACT", "VERIFY", "INSPECT", "PROOF_CONTRACT"},
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


@contextmanager
def private_objects(root: Path) -> Iterator[Any]:
    """Run Git with a throwaway object store, so reading a gate writes nothing to the repository."""
    raw_objects = git_text(root, "rev-parse", "--git-path", "objects")
    if not raw_objects:
        raise RunStateError("Git did not return an object directory")
    objects = Path(raw_objects)
    objects = (objects if objects.is_absolute() else root / objects).resolve()
    with tempfile.TemporaryDirectory(prefix="patpat-candidate-") as directory:
        private = Path(directory)
        (private / "objects").mkdir()

        def run(*args: str, index: Path | None = None) -> subprocess.CompletedProcess[bytes]:
            environment = {
                **os.environ,
                "GIT_OBJECT_DIRECTORY": str(private / "objects"),
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(objects),
            }
            if index is not None:
                environment["GIT_INDEX_FILE"] = str(index)
            return subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                env=environment,
            )

        yield run, private / "index"


def worktree_tree(root: Path) -> tuple[str | None, bool]:
    """Return the tree a full commit of the worktree would have, and whether it holds a gitlink."""
    with private_objects(root) as (run, index):
        if run("read-tree", "HEAD", index=index).returncode != 0:
            return None, False
        if run("add", "-A", "--", ".", index=index).returncode != 0:
            return None, False
        stage = run("ls-files", "--stage", "-z", index=index)
        if stage.returncode != 0:
            return None, False
        has_gitlink = any(entry.startswith(b"160000 ") for entry in stage.stdout.split(b"\0"))
        tree = run("write-tree", index=index)
        if tree.returncode != 0:
            return None, has_gitlink
        return os.fsdecode(tree.stdout).strip() or None, has_gitlink


def current_candidate(root: Path) -> dict[str, Any]:
    snapshot = current_snapshot(root)
    worktree, has_gitlink = worktree_tree(root)
    return {
        "snapshot": snapshot,
        "worktree_tree": worktree,
        # A gitlink records only a pointer, so a tree cannot bind what the proof actually read.
        "tree": None if has_gitlink else worktree,
        "head": snapshot.split(":")[1],
    }


def worktree_matches_head(root: Path, candidate: dict[str, Any]) -> bool:
    state = git_process(
        root,
        "--no-optional-locks",
        "status",
        "--porcelain",
        "--ignore-submodules=none",
    )
    if state.returncode != 0 or state.stdout.strip():
        return False
    if (
        candidate["worktree_tree"] is None
        or candidate["worktree_tree"] != git_text(root, "rev-parse", "HEAD^{tree}")
    ):
        return False
    return gitlinks_match_their_heads(root)


def gitlinks_match_their_heads(root: Path) -> bool:
    """The parent tree holds only a pointer, so each populated gitlink must be clean on its own."""
    stage = git_process(root, "ls-files", "--stage", "-z")
    if stage.returncode != 0:
        return False
    for entry in stage.stdout.split(b"\0"):
        if not entry.startswith(b"160000 "):
            continue
        nested = root / checked_relative_path(entry.split(b"\t", 1)[1])
        if not nested.is_dir() or not any(nested.iterdir()):
            continue
        try:
            if not worktree_matches_head(nested, current_candidate(nested)):
                return False
        except RunStateError:
            return False
    return True


def index_holds_candidate(root: Path, candidate: dict[str, Any]) -> bool:
    """A commit of this index holds exactly the proven content."""
    raw_index = git_text(root, "rev-parse", "--git-path", "index")
    if not raw_index:
        return False
    index = Path(raw_index)
    index = (index if index.is_absolute() else root / index).resolve()
    with private_objects(root) as (run, private_index):
        # Work on a copy so the real index never caches a tree from the throwaway object store.
        try:
            private_index.write_bytes(index.read_bytes())
        except OSError:
            return False
        tree = run("write-tree", index=private_index)
    return tree.returncode == 0 and os.fsdecode(tree.stdout).strip() == candidate["tree"]


def git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return git_process(root, "merge-base", "--is-ancestor", ancestor, descendant).returncode == 0


def merge_result_is_proven(root: Path, head: str, base_head: str | None) -> tuple[bool, str]:
    if not base_head:
        return False, "merge gate failed: --base-head is required to prove the merged result"
    base_commit = git_text(root, "rev-parse", "--verify", "--quiet", f"{base_head}^{{commit}}")
    if not base_commit:
        return False, f"merge gate failed: base head is not a local commit; fetch it first: {base_head}"
    if not git_is_ancestor(root, base_commit, head):
        return (
            False,
            f"merge gate failed: head does not contain base {base_commit}; "
            "the merged result would be unproven, so update onto the base and prove the new head",
        )
    return True, "head contains the base"


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
            if ".git" in child.relative_to(path).parts or (
                child.is_dir() and not child.is_symlink()
            ):
                continue
            child_label = label + b"/" + os.fsencode(child.relative_to(path))
            digest_path(digest, root, child.relative_to(root), child_label)
    else:
        digest.update(b"missing")
    digest.update(b"\0")


def run_directory(root: Path, run_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise RunStateError("run id must be lowercase kebab-case and at most 64 characters")
    path = git_store_root(root) / run_id
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise RunStateError("run store path must be a real directory without symlinks")
    return path


def state_path(root: Path, run_id: str) -> Path:
    return run_directory(root, run_id) / "state.json"


def provider_receipt_path(root: Path, run_id: str) -> Path:
    return run_directory(root, run_id) / "provider-receipt.json"


def evaluate_merge_provider_receipt(root: Path, run_id: str) -> tuple[bool, str, bool]:
    return evaluate_provider_receipt(provider_receipt_path(root, run_id), require_git_root(root))


def evaluate_provider_receipt(path: Path, current_head: str) -> tuple[bool, str, bool]:
    """Fail-closed until a pr_watch ready receipt binds repository, PR, head, base, and policy."""
    if not path.is_file():
        return (
            False,
            f"merge gate failed: missing bound pr_watch ready receipt at {path}; "
            "merge authority is unattested",
            False,
        )
    try:
        bounded_file_binding(
            path,
            max_bytes=pr_watch.MAX_INPUT_BYTES,
            error_type=RunStateError,
            label="provider receipt",
        )
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RunStateError) as error:
        return False, f"merge gate failed: provider receipt is unreadable: {error}", True
    if not isinstance(document, dict):
        return False, "merge gate failed: provider receipt must be a JSON object", True
    if not isinstance(document.get("policy"), dict):
        return False, "merge gate failed: provider receipt does not bind policy", True
    verdict = pr_watch.evaluate(document)
    binding = verdict.get("binding") if isinstance(verdict.get("binding"), dict) else {}
    bound_head = str(binding.get("head_sha") or "").lower()
    if not all(
        binding.get(key) not in (None, "")
        for key in ("repository", "pull_request", "head_sha", "base_ref")
    ):
        return (
            False,
            "merge gate failed: provider receipt does not bind repository, PR, head, and base",
            True,
        )
    if bound_head != current_head.lower():
        return (
            False,
            "merge gate failed: provider receipt is not bound to the current HEAD: "
            f"bound={binding.get('head_sha')}, current={current_head}",
            True,
        )
    if verdict.get("verdict") != "ready":
        reasons = verdict.get("reasons") if isinstance(verdict.get("reasons"), list) else []
        first = reasons[0] if reasons and isinstance(reasons[0], dict) else {}
        detail = first.get("code") or first.get("detail") or verdict.get("verdict")
        return (
            False,
            f"merge gate failed: provider receipt is not ready ({verdict.get('verdict')}): {detail}",
            True,
        )
    return True, "bound pr_watch ready receipt observed", True


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
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
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


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_STATE_BYTES:
        raise RunStateError(f"run state must not exceed {MAX_STATE_BYTES} bytes")
    atomic_write(path, payload)


@contextmanager
def run_lock(root: Path, run_id: str) -> Iterator[None]:
    directory = run_directory(root, run_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != "nt":
        os.chmod(directory, 0o700)
    path = directory / ".lock"
    token = uuid.uuid4().hex
    with path_guard(directory, RunStateError):
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as error:
            raise RunStateError(f"run is locked; use the unlock command only after confirming its owner stopped: {path}") from error
        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "created_at": now(),
            "token": token,
        }
        try:
            os.write(descriptor, (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
            os.fsync(descriptor)
        except OSError as error:
            os.close(descriptor)
            path.unlink(missing_ok=True)
            fsync_directory(path.parent)
            raise RunStateError(f"could not create run lock: {error}") from error
        os.close(descriptor)
    try:
        yield
    finally:
        with path_guard(directory, RunStateError):
            record, identity = read_lock_record(path, MAX_LOCK_BYTES)
            if record is not None and record.get("token") == token and path_has_identity(path, identity):
                path.unlink()
                fsync_directory(path.parent)


def recover_stale_lock(root: Path, run_id: str) -> Path:
    directory = run_directory(root, run_id)
    path = directory / ".lock"
    with path_guard(directory, RunStateError):
        if not path.is_file() or path.is_symlink():
            raise RunStateError("no regular run lock exists")
        record, identity = read_lock_record(path, MAX_LOCK_BYTES)
        if record is None or identity is None:
            raise RunStateError("lock metadata is invalid or too large; inspect manually")
        if not isinstance(record, dict) or set(record) != {"pid", "host", "created_at", "token"}:
            raise RunStateError("lock metadata is invalid; inspect manually")
        pid = record.get("pid")
        token = record.get("token")
        host = record.get("host")
        created_at = record.get("created_at")
        if host != socket.gethostname():
            raise RunStateError("lock belongs to another host and cannot be recovered automatically")
        if (
            isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid <= 0
            or not isinstance(token, str)
            or LOCK_TOKEN_PATTERN.fullmatch(token) is None
            or not isinstance(host, str)
            or len(host) > 255
            or not isinstance(created_at, str)
            or not 1 <= len(created_at) <= 64
        ):
            raise RunStateError("lock identity is invalid; inspect manually")
        if process_is_alive(pid):
            raise RunStateError(f"lock owner pid {pid} is still running")
        current_record, current_identity = read_lock_record(path, MAX_LOCK_BYTES)
        if (
            current_record != record
            or current_identity != identity
            or not path_has_identity(path, identity)
        ):
            raise RunStateError("lock identity changed during recovery; inspect again")
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
    return bounded_file_binding(
        path,
        max_bytes=MAX_EVIDENCE_BYTES,
        error_type=RunStateError,
        label="file receipt",
    )


def validate_receipt(receipt: str) -> dict[str, Any]:
    if not isinstance(receipt, str) or not receipt.startswith("file:") or len(receipt) == 5:
        raise RunStateError("receipt must use file:<absolute-path> to an inspectable evidence file")
    path = Path(receipt.removeprefix("file:"))
    if not path.is_absolute():
        raise RunStateError("receipt must use file:<absolute-path> to an inspectable evidence file")
    return file_binding(path)


def receipt_binding_is_fresh(record: dict[str, Any]) -> bool:
    binding = record.get("binding")
    if not isinstance(binding, dict) or set(binding) != {"path", "sha256", "size"}:
        return False
    try:
        receipt_binding = validate_receipt(record.get("receipt"))
        return receipt_binding == binding and receipt_binding["path"] == binding["path"]
    except (OSError, RunStateError, TypeError):
        return False


def proof_covers_candidate(root: Path, record: dict[str, Any], candidate: dict[str, Any]) -> bool:
    snapshot = record.get("snapshot")
    if snapshot == candidate["snapshot"]:
        return True
    tree = record.get("tree")
    if not isinstance(tree, str) or tree != candidate["tree"] or not isinstance(snapshot, str):
        return False
    parts = snapshot.split(":")
    return len(parts) == 3 and git_is_ancestor(root, parts[1], candidate["head"])


def receipt_is_fresh(
    root: Path,
    record: Any,
    state: dict[str, Any],
    candidate: dict[str, Any],
    verdict: str,
    *,
    independent: bool = False,
) -> bool:
    if not isinstance(record, dict):
        return False
    try:
        actor_key = canonical_identity(record.get("actor"), "receipt actor")
        owner_key = canonical_identity(state.get("owner"), "integration owner")
        verifier_key = None
        if independent:
            verification = state.get("verification")
            if not isinstance(verification, dict):
                return False
            verifier_key = canonical_identity(
                verification.get("actor"), "verification actor"
            )
    except RunStateError:
        return False
    return (
        proof_covers_candidate(root, record, candidate)
        and record.get("epoch") == state.get("epoch")
        and record.get("verdict") == verdict
        and isinstance(record.get("receipt"), str)
        and (
            not independent
            or (actor_key != owner_key and actor_key != verifier_key)
        )
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
    owner_key: str | None = None
    try:
        owner_key = canonical_identity(state.get("owner"), "integration owner")
    except RunStateError as error:
        errors.append(str(error))
    for kind in ("verification", "review"):
        record = state.get(kind)
        if record is not None and not isinstance(record, dict):
            errors.append(f"{kind} record must be an object or null")
    review = state.get("review")
    verification = state.get("verification")
    if isinstance(review, dict):
        try:
            review_key = canonical_identity(review.get("actor"), "review actor")
        except RunStateError as error:
            errors.append(str(error))
        else:
            if not isinstance(verification, dict):
                errors.append("review record requires a verification record")
            else:
                try:
                    verifier_key = canonical_identity(
                        verification.get("actor"), "verification actor"
                    )
                except RunStateError as error:
                    errors.append(str(error))
                else:
                    if review_key == verifier_key or (
                        owner_key is not None and review_key == owner_key
                    ):
                        errors.append(
                            "review actor must differ from the integration owner and verifier"
                        )
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
    epoch = state.get("epoch")
    if isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 0:
        errors.append("epoch must be a non-negative integer")
    sequence = state.get("sequence")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
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
            if (
                not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in observed
                )
                or observed != expected
                or sequence != expected[-1]
            ):
                errors.append("event sequence is invalid")
            if events[-1].get("node") != state.get("node"):
                errors.append("last event node does not match state")
    return errors


def load_state(root: Path, run_id: str) -> dict[str, Any]:
    path = state_path(root, run_id)
    if not path.exists() and not path.is_symlink():
        raise RunStateError(f"run does not exist: {run_id}")
    value, identity = read_lock_record(path, MAX_STATE_BYTES)
    if value is None or identity is None or not path_has_identity(path, identity):
        raise RunStateError("state must be a unique bounded regular JSON file")
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
        candidate = current_candidate(root)
        snapshot = candidate["snapshot"]
        if destination == "ACT" and not state["proof_contract"]:
            raise RunStateError("ACT requires a structured proof contract")
        if destination == "REVIEW" and not receipt_is_fresh(root, state["verification"], state, candidate, "verified"):
            raise RunStateError("REVIEW requires verified evidence for the current epoch and snapshot")
        if destination in {"LEARN", "REPORT"}:
            if not receipt_is_fresh(root, state["verification"], state, candidate, "verified"):
                raise RunStateError(f"{destination} requires current verified evidence")
            if not receipt_is_fresh(root, state["review"], state, candidate, "pass", independent=True):
                raise RunStateError(f"{destination} requires current independent review")
        revisiting_contract = (
            destination == "INSPECT" and source != "FRAME"
        ) or (destination == "PROOF_CONTRACT" and source in {"VERIFY", "REVIEW"})
        if revisiting_contract:
            state["proof_contract"] = None
        if destination in {"ACT", "VERIFY"} or revisiting_contract:
            state["epoch"] += 1
            state["verification"] = None
            state["review"] = None
        state["node"] = destination
        append_state_event(state, "transition", f"{source} -> {destination}", snapshot=snapshot)
        save_state(root, run_id, state)
        return state


PROOF_CONTRACT_CANONICAL_KEYS = ("claim", "surface", "action", "expect", "cleanup")


def normalize_proof_contract(fields: dict[str, str]) -> dict[str, str]:
    if not isinstance(fields, dict):
        raise RunStateError("proof contract must be a key-value mapping")
    normalized: dict[str, str] = {}
    for key, val in fields.items():
        if not isinstance(key, str):
            continue
        canon_key = key.lower().strip().replace("-", "_").replace(" ", "_")
        if canon_key in {"expected_observation", "expected"}:
            canon_key = "expect"
        if isinstance(val, str) and val.strip():
            normalized[canon_key] = val.strip()
    missing = [k for k in PROOF_CONTRACT_CANONICAL_KEYS if k not in normalized]
    if missing:
        raise RunStateError("proof contract requires claim, surface, action, expect, and cleanup")
    normalized["expected"] = normalized["expect"]
    normalized["expected_observation"] = normalized["expect"]
    return normalized


def record_proof_contract(root: Path, run_id: str, fields: dict[str, str]) -> dict[str, Any]:
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] not in {"INSPECT", "PROOF_CONTRACT"}:
            raise RunStateError("proof contract must be recorded during INSPECT or PROOF_CONTRACT")
        normalized = normalize_proof_contract(fields)
        previous_contract = state["proof_contract"]
        contract_changed = not isinstance(previous_contract, dict) or any(
            previous_contract.get(key) != normalized[key]
            for key in PROOF_CONTRACT_CANONICAL_KEYS
        )
        state["proof_contract"] = {**normalized, "recorded_at": now()}
        if contract_changed:
            state["last_failure"] = None
        append_state_event(state, "proof-contract", normalized["claim"], snapshot=current_snapshot(root))
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
        candidate = current_candidate(root)
        snapshot = candidate["snapshot"]
        if kind == "review":
            owner_key = canonical_identity(state["owner"], "integration owner")
            verification = state.get("verification")
            if not receipt_is_fresh(root, verification, state, candidate, "verified"):
                raise RunStateError("independent review requires current verified evidence")
            verifier_key = canonical_identity(
                verification.get("actor"), "verification actor"
            )
            if actor_key in {owner_key, verifier_key}:
                raise RunStateError(
                    "independent reviewer must differ from the integration owner and verifier"
                )
        state[kind] = {
            "summary": summary,
            "receipt": receipt,
            "binding": binding,
            "actor": actor,
            "verdict": verdict,
            "snapshot": snapshot,
            "tree": candidate["tree"],
            "epoch": state["epoch"],
            "recorded_at": now(),
        }
        if kind == "verification":
            state["review"] = None
        if verdict in {"verified", "pass"}:
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
        append_state_event(state, "decision", summary, snapshot=current_snapshot(root))
        save_state(root, run_id, state)
        return state


FAILURE_CLASSES = frozenset({"implementation", "verifier", "environment"})
GATES = frozenset({"pre-edit", "verify", "commit", "ship", "merge"})


def record_failure(
    root: Path,
    run_id: str,
    summary: str,
    blocker_key: str,
    failure_class: str = "implementation",
) -> dict[str, Any]:
    if failure_class not in FAILURE_CLASSES:
        raise RunStateError(
            f"failure class must be one of {sorted(FAILURE_CLASSES)}, got {failure_class!r}"
        )
    with run_lock(root, run_id):
        state = load_state(root, run_id)
        if state["node"] in {"REPORT", "BLOCKED"}:
            raise RunStateError(f"cannot record into terminal node {state['node']}")
        snapshot = current_snapshot(root)
        previous = state["last_failure"]
        same_failure_sequence = (
            isinstance(previous, dict)
            and previous.get("key") == blocker_key
            and previous.get("failure_class") == failure_class
            and previous.get("node") == state["node"]
        )
        count = int(previous["count"]) + 1 if same_failure_sequence else 1
        state["last_failure"] = {
            "key": blocker_key,
            "failure_class": failure_class,
            "snapshot": snapshot,
            "node": state["node"],
            "count": count,
        }
        if count >= 3:
            state["node"] = "BLOCKED"
            state["blocked_reason"] = f"[{failure_class}] {blocker_key}"
        append_state_event(
            state,
            "failure",
            summary,
            snapshot=snapshot,
            blocker_key=blocker_key,
            failure_class=failure_class,
            count=count,
        )
        save_state(root, run_id, state)
        return state


def check_gate(
    root: Path, run_id: str, gate: str, base_head: str | None = None
) -> tuple[bool, str]:
    if gate not in GATES:
        raise RunStateError(f"gate must be one of {sorted(GATES)}, got {gate!r}")
    state = load_state(root, run_id)
    candidate = current_candidate(root)

    if gate == "pre-edit":
        pc = state.get("proof_contract")
        if not pc or not isinstance(pc, dict):
            return False, "pre-edit gate failed: no structured proof contract recorded"
        if not all(pc.get(k) for k in PROOF_CONTRACT_CANONICAL_KEYS):
            return False, "pre-edit gate failed: proof contract missing required canonical fields"
        return True, "pre-edit gate passed: structured proof contract is recorded and valid"

    if gate == "verify":
        verification = state.get("verification")
        if not receipt_is_fresh(root, verification, state, candidate, "verified"):
            return False, "verify gate failed: missing fresh verified receipt for current snapshot"
        return True, "verify gate passed: fresh verified receipt observed on authoritative surface"

    if gate in {"commit", "ship"}:
        if state.get("node") == "BLOCKED":
            return False, f"{gate} gate failed: the run is BLOCKED: {state.get('blocked_reason')}"
        verification = state.get("verification")
        review = state.get("review")
        if not receipt_is_fresh(root, verification, state, candidate, "verified"):
            return False, f"{gate} gate failed: verification receipt is missing or stale"
        if not receipt_is_fresh(root, review, state, candidate, "pass", independent=True):
            return False, f"{gate} gate failed: independent review pass is missing or stale"
        if state.get("owner") == "worker":
            return False, f"{gate} gate failed: workers never ship; parent integration owner must ship"
        matches_head = worktree_matches_head(root, candidate)
        if gate == "ship":
            if not matches_head:
                return (
                    False,
                    "ship gate failed: the checkout differs from HEAD, so the proof does not cover "
                    "this head; commit the proven content, or prove the head in a clean worktree",
                )
            return True, f"ship gate passed: proof covers the clean head {candidate['head']}"
        if matches_head:
            return False, "commit gate failed: HEAD already holds the proven content; use the ship gate"
        if candidate["tree"] is None:
            return (
                False,
                "commit gate failed: a Git tree cannot bind this worktree; commit first and prove that head",
            )
        if not index_holds_candidate(root, candidate):
            return (
                False,
                "commit gate failed: the index does not hold exactly the proven content; stage all "
                "of it, or commit the in-scope paths and prove that head in a clean worktree",
            )
        return True, f"commit gate passed: proof covers candidate tree {candidate['tree']}"

    if gate == "merge":
        authorities = set(state.get("authorities", []))
        if "explicit-merge" not in authorities:
            return False, "merge gate failed: missing explicit-merge authority"
        ship_ok, ship_reason = check_gate(root, run_id, "ship")
        if not ship_ok:
            return False, f"merge gate failed: {ship_reason}"
        ready, provider_reason, _present = evaluate_merge_provider_receipt(root, run_id)
        if not ready:
            return False, provider_reason
        proven, base_reason = merge_result_is_proven(root, candidate["head"], base_head)
        if not proven:
            return False, base_reason
        return True, "merge gate passed: explicit merge authority, bound pr_watch ready receipt, and head contains the base"

    return False, f"unknown gate: {gate}"


def validation_errors(root: Path, run_id: str) -> list[str]:
    try:
        state = load_state(root, run_id)
    except RunStateError as error:
        return [str(error)]
    errors = schema_errors(state, root, run_id)
    candidate = current_candidate(root)
    if state["node"] in {"ACT", "VERIFY", "REVIEW", "LEARN", "REPORT"} and not state["proof_contract"]:
        errors.append("active run is missing a proof contract")
    if state["node"] in {"REVIEW", "LEARN", "REPORT"} and not receipt_is_fresh(root, state["verification"], state, candidate, "verified"):
        errors.append("verification is missing or stale")
    if state["node"] in {"LEARN", "REPORT"} and not receipt_is_fresh(
        root, state["review"], state, candidate, "pass", independent=True
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
    candidate = current_candidate(root)
    snapshot = candidate["snapshot"]
    verification = state["verification"]
    review = state["review"]
    return {
        "store": str(run_directory(root, run_id)),
        "run_id": run_id,
        "objective": state["objective"],
        "node": state["node"],
        "epoch": state["epoch"],
        "declared_authorities": state["authorities"],
        "declared_prohibitions": state["prohibitions"],
        "current_snapshot": snapshot,
        "verification_present": verification is not None,
        "verification_verdict": verification.get("verdict") if isinstance(verification, dict) else None,
        "verification_actor": verification.get("actor") if isinstance(verification, dict) else None,
        "verification_stale": verification is not None and not receipt_is_fresh(root, verification, state, candidate, "verified"),
        "review_present": review is not None,
        "review_verdict": review.get("verdict") if isinstance(review, dict) else None,
        "review_actor": review.get("actor") if isinstance(review, dict) else None,
        "review_stale": review is not None and not receipt_is_fresh(
            root, review, state, candidate, "pass", independent=True
        ),
        "errors": validation_errors(root, run_id),
    }


def compact_state_receipt(root: Path, state: dict[str, Any], action: str) -> dict[str, Any]:
    """Return a bounded mutation receipt instead of replaying the event ledger."""
    payload = json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    verification = state.get("verification")
    review = state.get("review")
    return {
        "schema_version": 1,
        "kind": "patpat.run.mutation_receipt",
        "action": action,
        "store": str(run_directory(root, state["run_id"])),
        "run_id": state["run_id"],
        "node": state["node"],
        "epoch": state["epoch"],
        "sequence": state["sequence"],
        "verification_verdict": verification.get("verdict") if isinstance(verification, dict) else None,
        "review_verdict": review.get("verdict") if isinstance(review, dict) else None,
        "blocked": state["node"] == "BLOCKED",
        "state_sha256": hashlib.sha256(payload).hexdigest(),
    }


def print_state_result(root: Path, state: dict[str, Any], action: str, full: bool) -> None:
    print(json.dumps(state if full else compact_state_receipt(root, state, action), indent=2, sort_keys=True))


def make_test_repository(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "patpat@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "Patpat Test"], check=True)
    (root / "source.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "source.txt"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "baseline"], check=True)


def symlink_creation_is_unsupported(error: OSError) -> bool:
    unsupported_errnos = {
        errno.EACCES,
        errno.EPERM,
        errno.ENOSYS,
        getattr(errno, "ENOTSUP", errno.EOPNOTSUPP),
        errno.EOPNOTSUPP,
    }
    return error.errno in unsupported_errnos or getattr(error, "winerror", None) == 1314


def write_test_provider_receipt(path: Path, head: str, **observation_overrides: Any) -> None:
    def rfc3339_z(value: datetime) -> str:
        return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    observed_at = rfc3339_z(datetime.now(UTC) - timedelta(seconds=5))
    deadline = rfc3339_z(datetime.now(UTC) + timedelta(hours=1))
    document = {
        "schema_version": pr_watch.SCHEMA_VERSION,
        "binding": {
            "repository": "example/project",
            "pull_request": 17,
            "head_sha": head,
            "base_ref": "main",
        },
        "policy": {
            "required_checks": ["contracts"],
            "allow_no_required_checks": False,
            "required_review": True,
            "max_attempts": 3,
            "max_observation_age_seconds": 900,
            "deadline": deadline,
        },
        "observation": {
            "observed_at": observed_at,
            "attempt": 1,
            "head_sha": head,
            "provider_repository": "example/project",
            "provider_pull_request": 17,
            "provider_head_sha": head,
            "state": "open",
            "unresolved_threads": 0,
            "base_ref": "main",
            "draft": False,
            "review_decision": "approved",
            "mergeability": "mergeable",
            "merge_state_status": "CLEAN",
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "success"},
            ],
        },
    }
    document["observation"].update(observation_overrides)
    path.write_text(json.dumps(document), encoding="utf-8")


def run_delivery_self_test() -> None:
    """Exercise every path decided in references/delivery-proof.md."""
    with (
        tempfile.TemporaryDirectory(prefix="patpat-run-delivery-") as directory,
        tempfile.TemporaryDirectory(prefix="patpat-run-delivery-evidence-") as evidence_directory,
    ):
        root = Path(directory).resolve()
        make_test_repository(root)
        evidence_path = Path(evidence_directory).resolve() / "evidence.txt"
        evidence_path.write_text("observed\n", encoding="utf-8")
        evidence = f"file:{evidence_path}"
        source = root / "source.txt"

        def git(*args: str, repository: Path = root) -> str:
            return subprocess.run(
                ["git", "-C", str(repository), *args], check=True, capture_output=True, text=True
            ).stdout.strip()

        def commit_all(message: str, repository: Path = root) -> str:
            git("add", "-A", repository=repository)
            git("commit", "-qm", message, repository=repository)
            return git("rev-parse", "HEAD", repository=repository)

        def start(run_id: str, *authorities: str, repository: Path = root) -> None:
            initialize(repository, run_id, "Deliver", "owner", list(authorities), [], [], [])
            transition(repository, run_id, "INSPECT")
            record_proof_contract(
                repository,
                run_id,
                {"claim": "c", "surface": "s", "action": "a", "expect": "e", "cleanup": "n"},
            )
            transition(repository, run_id, "PROOF_CONTRACT")
            transition(repository, run_id, "ACT")

        def prove(run_id: str, repository: Path = root) -> None:
            transition(repository, run_id, "VERIFY")
            record_receipt(repository, run_id, "verification", "v", evidence, "verifier", "verified")
            transition(repository, run_id, "REVIEW")
            record_receipt(repository, run_id, "review", "r", evidence, "reviewer", "pass")

        def expect_gate(
            run_id: str, gate: str, passed: bool, fragment: str = "", repository: Path = root, **kwargs: Any
        ) -> None:
            actual, reason = check_gate(repository, run_id, gate, **kwargs)
            if actual is not passed or fragment not in reason:
                raise AssertionError(f"{run_id} {gate}: expected {passed} {fragment!r}, got {actual} {reason!r}")

        def ready_provider(run_id: str, repository: Path = root) -> None:
            write_test_provider_receipt(
                provider_receipt_path(repository, run_id), require_git_root(repository)
            )

        base = require_git_root(root)

        # Proof first: admission survives staging, the commit carries proof, and merge is reachable from REPORT.
        start("proof-first", "explicit-merge")
        source.write_text("proof first\n", encoding="utf-8")
        prove("proof-first")
        expect_gate("proof-first", "commit", False, "does not hold exactly")
        expect_gate("proof-first", "ship", False, "differs from HEAD")
        git("add", "source.txt")
        expect_gate("proof-first", "commit", True)
        expect_gate("proof-first", "ship", False, "differs from HEAD")
        ready_provider("proof-first")
        expect_gate("proof-first", "merge", False, "differs from HEAD", base_head=base)
        head = commit_all("proof first")
        expect_gate("proof-first", "ship", True)
        expect_gate("proof-first", "commit", False, "already holds")
        transition(root, "proof-first", "REPORT")
        if validation_errors(root, "proof-first"):
            raise AssertionError("a carried proof failed validation at REPORT")
        try:
            record_receipt(root, "proof-first", "verification", "v", evidence, "verifier", "verified")
        except RunStateError:
            pass
        else:
            raise AssertionError("REPORT accepted a new receipt")
        ready_provider("proof-first")
        expect_gate("proof-first", "merge", False, "--base-head")
        expect_gate("proof-first", "merge", True, base_head=base)
        write_test_provider_receipt(provider_receipt_path(root, "proof-first"), base)
        expect_gate("proof-first", "merge", False, "not bound to the current HEAD", base_head=base)
        ready_provider("proof-first")

        # Reading a gate changes no object or index byte, on every path that computes a tree.
        def repository_bytes() -> dict[Path, bytes]:
            git_directory = root / ".git"
            paths = [git_directory / "index", *(git_directory / "objects").rglob("*")]
            return {path: path.read_bytes() for path in paths if path.is_file()}

        start("gate-read")
        nested_source = root / "sub" / "dir" / "nested.txt"
        nested_source.parent.mkdir(parents=True)
        nested_source.write_text("nested\n", encoding="utf-8")
        prove("gate-read")
        git("add", "-A")
        before_read = repository_bytes()
        expect_gate("gate-read", "commit", True)
        expect_gate("gate-read", "ship", False, "differs from HEAD")
        if repository_bytes() != before_read:
            raise AssertionError("evaluating a gate changed repository objects or the index")
        commit_all("gate read")
        git("fsck", "--strict", "--connectivity-only")
        expect_gate("gate-read", "ship", True)
        before_read = repository_bytes()
        nested_source.write_text("bytes the repository has never stored\n", encoding="utf-8")
        expect_gate("gate-read", "ship", False, "stale")
        if repository_bytes() != before_read:
            raise AssertionError("evaluating a gate stored new objects in the repository")
        git("checkout", "--", "sub/dir/nested.txt")

        # A stopped run admits nothing, even with fresh receipts.
        start("stopped", "explicit-merge")
        prove("stopped")
        expect_gate("stopped", "ship", True)
        for _attempt in range(3):
            record_failure(root, "stopped", "same", "same-blocker")
        ready_provider("stopped")
        expect_gate("stopped", "ship", False, "BLOCKED")
        expect_gate("stopped", "commit", False, "BLOCKED")
        expect_gate("stopped", "merge", False, "BLOCKED", base_head=base)

        # A later commit leaves the proven content behind.
        source.write_text("after proof\n", encoding="utf-8")
        commit_all("after proof")
        expect_gate("proof-first", "ship", False, "stale")
        expect_gate("proof-first", "merge", False, "stale", base_head=base)

        # Commit first passes the same predicate, for proofs that depend on commit identity.
        start("commit-first", "explicit-merge")
        source.write_text("commit first\n", encoding="utf-8")
        head = commit_all("commit first")
        prove("commit-first")
        expect_gate("commit-first", "ship", True)
        transition(root, "commit-first", "REPORT")
        ready_provider("commit-first")
        expect_gate("commit-first", "merge", True, base_head=base)

        # A commit that differs from the proven tree carries nothing.
        start("edited", "explicit-merge")
        source.write_text("proven\n", encoding="utf-8")
        prove("edited")
        source.write_text("edited after proof\n", encoding="utf-8")
        commit_all("edited")
        expect_gate("edited", "ship", False, "stale")
        ready_provider("edited")
        expect_gate("edited", "merge", False, "stale", base_head=base)

        # An amend that adds content is stale. So is a same-tree amend of a proven commit: it
        # removes the proof's base from history, and failing closed there costs one new run.
        start("amended")
        source.write_text("amend base\n", encoding="utf-8")
        commit_all("amend base")
        prove("amended")
        expect_gate("amended", "ship", True)
        git("commit", "-q", "--amend", "-m", "same tree, new message")
        expect_gate("amended", "ship", False, "stale")
        start("amend-parent")
        source.write_text("proven on parent\n", encoding="utf-8")
        prove("amend-parent")
        commit_all("first message")
        expect_gate("amend-parent", "ship", True)
        git("commit", "-q", "--amend", "-m", "reworded on the same parent")
        expect_gate("amend-parent", "ship", True)
        source.write_text("amended content\n", encoding="utf-8")
        git("add", "source.txt")
        git("commit", "-q", "--amend", "-m", "changed content")
        expect_gate("amend-parent", "ship", False, "stale")

        # A hook that rewrites the commit leaves it uncovered, which is why ship runs after commit.
        start("hooked")
        source.write_text("before hook\n", encoding="utf-8")
        prove("hooked")
        git("add", "source.txt")
        expect_gate("hooked", "commit", True)
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_bytes(b"#!/bin/sh\necho rewritten > source.txt\ngit add source.txt\n")
        hook.chmod(0o755)
        git("commit", "-qm", "hooked")
        hook.unlink()
        expect_gate("hooked", "ship", False, "stale")

        # Proof-then-reset cannot launder a tree across unrelated history.
        start("rewound", "explicit-merge")
        rewound_head = require_git_root(root)
        (root / "rewound.txt").write_text("rewound\n", encoding="utf-8")
        prove("rewound")
        commit_all("rewound")
        expect_gate("rewound", "ship", True)
        git("reset", "--hard", git("rev-parse", f"{rewound_head}~1"))
        (root / "other.txt").write_text("other history\n", encoding="utf-8")
        commit_all("other history")
        git("checkout", rewound_head, "--", ".")
        (root / "other.txt").unlink()
        (root / "rewound.txt").write_text("rewound\n", encoding="utf-8")
        commit_all("same tree on other history")
        expect_gate("rewound", "ship", False, "stale")

        # Partial staging is refused; unrelated dirty files need a clean worktree and a new run.
        start("partial", "explicit-merge")
        source.write_text("in scope\n", encoding="utf-8")
        unrelated = root / "unrelated.txt"
        unrelated.write_text("not in scope\n", encoding="utf-8")
        prove("partial")
        git("add", "source.txt")
        expect_gate("partial", "commit", False, "does not hold exactly")
        git("commit", "-qm", "in scope")
        scoped_head = require_git_root(root)
        expect_gate("partial", "ship", False, "differs from HEAD")
        ready_provider("partial")
        expect_gate("partial", "merge", False, "differs from HEAD", base_head=scoped_head)
        clean = Path(evidence_directory).resolve() / "clean"
        git("worktree", "add", "-q", "--detach", str(clean), scoped_head)
        start("exact", "explicit-merge", repository=clean)
        prove("exact", repository=clean)
        expect_gate("exact", "ship", True, repository=clean)
        transition(clean, "exact", "REPORT")
        ready_provider("exact", repository=clean)
        expect_gate("exact", "merge", True, repository=clean, base_head=scoped_head)
        git("worktree", "remove", "--force", str(clean))
        unrelated.unlink()

        # A head behind its base has an unproven merged result, and a missing base proves nothing.
        start("behind", "explicit-merge")
        source.write_text("behind\n", encoding="utf-8")
        behind_base = require_git_root(root)
        branch_point = git("rev-parse", "HEAD~1")
        prove("behind")
        behind_head = commit_all("behind")
        ready_provider("behind")
        expect_gate("behind", "merge", True, base_head=behind_base)
        git("checkout", "-q", "--detach", branch_point)
        (root / "sibling.txt").write_text("sibling landed\n", encoding="utf-8")
        landed_base = commit_all("sibling landed")
        git("checkout", "-q", "--detach", behind_head)
        expect_gate("behind", "ship", True)
        expect_gate("behind", "merge", False, "does not contain base", base_head=landed_base)
        expect_gate("behind", "merge", False, "not a local commit", base_head="0" * 40)
        git("merge", "-q", "--no-edit", landed_base)
        expect_gate("behind", "ship", False, "stale")
        start("rebased", "explicit-merge")
        prove("rebased")
        ready_provider("rebased")
        expect_gate("rebased", "merge", True, base_head=landed_base)

        # A late land request starts a new run rather than editing a terminal one.
        start("late-land")
        source.write_text("late land\n", encoding="utf-8")
        prove("late-land")
        transition(root, "late-land", "REPORT")
        git("add", "source.txt")
        expect_gate("late-land", "commit", True)
        late_head = commit_all("late land")
        ready_provider("late-land")
        expect_gate("late-land", "ship", True)
        expect_gate("late-land", "merge", False, "explicit-merge", base_head=late_head)
        start("late-land-2", "explicit-merge")
        prove("late-land-2")
        ready_provider("late-land-2")
        expect_gate("late-land-2", "merge", True, base_head=late_head)

        # Files hidden from status still void proof; assume-unchanged cannot launder an edit.
        start("hidden")
        prove("hidden")
        expect_gate("hidden", "ship", True)
        git("update-index", "--assume-unchanged", "source.txt")
        source.write_text("hidden edit\n", encoding="utf-8")
        expect_gate("hidden", "ship", False, "stale")
        start("hidden-proof")
        prove("hidden-proof")
        expect_gate("hidden-proof", "ship", False, "differs from HEAD")
        git("update-index", "--no-assume-unchanged", "source.txt")
        git("checkout", "--", "source.txt")

        # A receipt recorded before trees existed keeps the exact-snapshot rule.
        start("legacy")
        prove("legacy")
        legacy = load_state(root, "legacy")
        for kind in ("verification", "review"):
            legacy[kind].pop("tree")
        atomic_write_json(state_path(root, "legacy"), legacy)
        expect_gate("legacy", "ship", True)
        (root / "legacy.txt").write_text("legacy\n", encoding="utf-8")
        expect_gate("legacy", "commit", False, "stale")
        (root / "legacy.txt").unlink()

        # A gitlink cannot bind to a tree, so proof-first refuses and only commit-first remains.
        start("embedded")
        nested = root / "nested"
        nested.mkdir()
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        git("config", "user.email", "patpat@example.invalid", repository=nested)
        git("config", "user.name", "Patpat Test", repository=nested)
        (nested / "inner.txt").write_text("inner\n", encoding="utf-8")
        commit_all("inner", repository=nested)
        if current_candidate(root)["tree"] is not None:
            raise AssertionError("an embedded repository was bound to a tree")
        prove("embedded")
        expect_gate("embedded", "commit", False, "cannot bind")
        expect_gate("embedded", "ship", False, "differs from HEAD")

        start("gitlink-first")
        commit_all("commit the gitlink")
        prove("gitlink-first")
        expect_gate("gitlink-first", "ship", True)
        (nested / "inner.txt").write_text("dirty inner\n", encoding="utf-8")
        expect_gate("gitlink-first", "ship", False, "stale")
        git("checkout", "--", "inner.txt", repository=nested)
        expect_gate("gitlink-first", "ship", True)

        # The parent holds only a pointer, so proof taken on nested bytes no commit holds is refused.
        start("nested-dirty")
        (nested / "inner.txt").write_text("dirty at proof\n", encoding="utf-8")
        prove("nested-dirty")
        expect_gate("nested-dirty", "ship", False, "differs from HEAD")
        git("checkout", "--", "inner.txt", repository=nested)
        start("nested-hidden")
        git("update-index", "--assume-unchanged", "inner.txt", repository=nested)
        (nested / "inner.txt").write_text("hidden at proof\n", encoding="utf-8")
        prove("nested-hidden")
        expect_gate("nested-hidden", "ship", False, "differs from HEAD")
        git("update-index", "--no-assume-unchanged", "inner.txt", repository=nested)
        git("checkout", "--", "inner.txt", repository=nested)
        git("config", "status.showUntrackedFiles", "no", repository=nested)
        start("nested-untracked")
        (nested / "untracked-inner.txt").write_text("input\n", encoding="utf-8")
        prove("nested-untracked")
        expect_gate("nested-untracked", "ship", False, "differs from HEAD")
        (nested / "untracked-inner.txt").unlink()

        # Tree-less proof still cannot cover a hidden edit or an untracked input.
        start("gitlink-hidden")
        git("update-index", "--assume-unchanged", "source.txt")
        source.write_text("hidden beside a gitlink\n", encoding="utf-8")
        prove("gitlink-hidden")
        expect_gate("gitlink-hidden", "ship", False, "differs from HEAD")
        git("update-index", "--no-assume-unchanged", "source.txt")
        git("checkout", "--", "source.txt")
        git("config", "status.showUntrackedFiles", "no")
        start("gitlink-untracked")
        (root / "untracked-input.txt").write_text("input\n", encoding="utf-8")
        prove("gitlink-untracked")
        expect_gate("gitlink-untracked", "ship", False, "differs from HEAD")


def run_self_test() -> bool:
    run_delivery_self_test()
    with (
        tempfile.TemporaryDirectory(prefix="patpat-run-state-") as directory,
        tempfile.TemporaryDirectory(prefix="patpat-run-evidence-") as evidence_directory,
    ):
        root = Path(directory)
        evidence_root = Path(evidence_directory)
        symlink_probe_target = evidence_root / "symlink-probe-target"
        symlink_probe_target.mkdir()
        symlink_probe = evidence_root / "symlink-probe"
        try:
            symlink_probe.symlink_to(symlink_probe_target, target_is_directory=True)
        except NotImplementedError:
            symlink_supported = False
        except OSError as error:
            if not symlink_creation_is_unsupported(error):
                raise
            symlink_supported = False
        else:
            symlink_probe.unlink()
            symlink_supported = True
        symlink_probe_target.rmdir()
        if not symlink_creation_is_unsupported(OSError(errno.EPERM, "not permitted")):
            raise AssertionError("symlink capability errors must permit platform-specific skip")
        if symlink_creation_is_unsupported(OSError(errno.EIO, "I/O failure")):
            raise AssertionError("unexpected symlink probe failures must not skip safety assertions")

        bounded = evidence_root / "bounded.txt"
        bounded.write_bytes(b"1234")
        assert bounded_file_binding(
            bounded.resolve(), max_bytes=4, error_type=RunStateError, label="test evidence"
        )["size"] == 4
        bounded.write_bytes(b"12345")
        try:
            bounded_file_binding(
                bounded.resolve(), max_bytes=4, error_type=RunStateError, label="test evidence"
            )
        except RunStateError as error:
            assert "exceeds" in str(error)
        else:
            raise AssertionError("oversized evidence was accepted")
        bounded.write_bytes(b"1234")
        hardlink = evidence_root / "bounded-hardlink.txt"
        os.link(bounded, hardlink)
        try:
            bounded_file_binding(
                bounded.resolve(), max_bytes=4, error_type=RunStateError, label="test evidence"
            )
        except RunStateError as error:
            assert "unique regular file" in str(error)
        else:
            raise AssertionError("hard-linked evidence was accepted")
        hardlink.unlink()
        try:
            bounded_file_binding(
                evidence_root.resolve(), max_bytes=4, error_type=RunStateError, label="test evidence"
            )
        except RunStateError as error:
            assert "unique regular file" in str(error)
        else:
            raise AssertionError("evidence directory was accepted")

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

        def prepare_review_run(run_id: str) -> tuple[Path, str]:
            verification = evidence(f"{run_id}-verification")
            review = evidence(f"{run_id}-review")
            initialize(root, run_id, "Reject stale verification", "integration-owner", [], [], [], [])
            transition(root, run_id, "INSPECT")
            transition(root, run_id, "PROOF_CONTRACT")
            record_proof_contract(
                root,
                run_id,
                {
                    "claim": "The verified receipt remains current",
                    "surface": "test fixture",
                    "action": "inspect the receipt",
                    "expected": "stale evidence is rejected",
                    "cleanup": "remove temporary evidence",
                },
            )
            transition(root, run_id, "ACT")
            transition(root, run_id, "VERIFY")
            record_receipt(
                root,
                run_id,
                "verification",
                "Behavior observed",
                verification,
                "verifier",
                "verified",
            )
            transition(root, run_id, "REVIEW")
            return Path(verification.removeprefix("file:")), review

        def expect_atomic_rejection(run_id: str, action: Any, label: str) -> None:
            before = state_path(root, run_id).read_bytes()
            try:
                action()
            except RunStateError:
                pass
            else:
                raise AssertionError(f"{label} was accepted")
            if state_path(root, run_id).read_bytes() != before:
                raise AssertionError(f"{label} changed state before failing")

        for failure_mode in ("modified", "missing", "snapshot-stale"):
            review_run = f"review-{failure_mode}"
            verification_path, review = prepare_review_run(review_run)
            if failure_mode == "modified":
                verification_path.write_text("modified verification\n", encoding="utf-8")
            elif failure_mode == "missing":
                verification_path.unlink()
            else:
                (root / "source.txt").write_text("stale review snapshot\n", encoding="utf-8")
            expect_atomic_rejection(
                review_run,
                lambda current_run=review_run, current_review=review: record_receipt(
                    root,
                    current_run,
                    "review",
                    "Review passed",
                    current_review,
                    "reviewer",
                    "pass",
                ),
                f"{failure_mode} verification review admission",
            )
            if failure_mode == "snapshot-stale":
                (root / "source.txt").write_text("one\n", encoding="utf-8")

            learn_run = f"learn-{failure_mode}"
            verification_path, review = prepare_review_run(learn_run)
            record_receipt(
                root,
                learn_run,
                "review",
                "Review passed",
                review,
                "reviewer",
                "pass",
            )
            if failure_mode == "modified":
                verification_path.write_text("modified verification\n", encoding="utf-8")
            elif failure_mode == "missing":
                verification_path.unlink()
            else:
                (root / "source.txt").write_text("stale learn snapshot\n", encoding="utf-8")
            expect_atomic_rejection(
                learn_run,
                lambda current_run=learn_run: transition(root, current_run, "LEARN"),
                f"{failure_mode} verification LEARN admission",
            )
            expect_atomic_rejection(
                learn_run,
                lambda current_run=learn_run: transition(root, current_run, "REPORT"),
                f"{failure_mode} verification REPORT admission",
            )
            if failure_mode == "snapshot-stale":
                (root / "source.txt").write_text("one\n", encoding="utf-8")

        fresh_verification_path, fresh_review = prepare_review_run("fresh-admission")
        assert fresh_verification_path.is_file()
        record_receipt(
            root,
            "fresh-admission",
            "review",
            "Review passed",
            fresh_review,
            "reviewer",
            "pass",
        )
        transition(root, "fresh-admission", "LEARN")
        transition(root, "fresh-admission", "REPORT")
        assert status(root, "fresh-admission")["node"] == "REPORT"

        for source in ("VERIFY", "REVIEW"):
            for destination in ("INSPECT", "PROOF_CONTRACT"):
                run_id = f"feedback-{source}-{destination}".lower().replace("_", "-")
                verification_path, review = prepare_review_run(run_id)
                if source == "VERIFY":
                    transition(root, run_id, "VERIFY")
                    record_receipt(root, run_id, "verification", "Observed", f"file:{verification_path}", "integration-owner", "verified")
                else:
                    record_receipt(root, run_id, "review", "Reviewed", review, "reviewer", "pass")
                before = load_state(root, run_id)
                transition(root, run_id, destination)
                after = load_state(root, run_id)
                assert after["epoch"] > before["epoch"], "feedback retained the old evidence epoch"
                assert after["proof_contract"] is None, "feedback retained the invalid proof contract"
                assert after["verification"] is None and after["review"] is None
                assert after["authorities"] == before["authorities"]
                assert after["prohibitions"] == before["prohibitions"]
                for gate in ("pre-edit", "verify", "ship", "merge"):
                    assert not check_gate(root, run_id, gate)[0], f"feedback left {gate} open"
                for terminal in ("LEARN", "REPORT"):
                    expect_atomic_rejection(run_id, lambda node=terminal: transition(root, run_id, node), "feedback completion without proof")
                if destination == "INSPECT":
                    transition(root, run_id, "PROOF_CONTRACT")
                expect_atomic_rejection(run_id, lambda: transition(root, run_id, "ACT"), "feedback ACT without a revised contract")
                record_proof_contract(root, run_id, {
                    "claim": "R1: requested output; R2: rejected input leaves data unchanged",
                    "surface": "R1, R2: public interface",
                    "action": "R1: valid input; R2: invalid input",
                    "expect": "R1: requested value; R2: rejection and unchanged data",
                    "cleanup": "R1, R2: remove fixtures",
                })
                assert not check_gate(root, run_id, "verify")[0], "old receipt certified a revised claim"
                transition(root, run_id, "ACT")
                transition(root, run_id, "VERIFY")
                expect_atomic_rejection(run_id, lambda: transition(root, run_id, "REVIEW"), "feedback reused verification")
                record_receipt(root, run_id, "verification", "R1 and R2 observed", f"file:{verification_path}", "integration-owner", "verified")
                transition(root, run_id, "REVIEW")
                record_receipt(root, run_id, "review", "Coverage reviewed", review, "reviewer", "pass")
                transition(root, run_id, "REPORT")

        verification_path, _ = prepare_review_run("stale-feedback")
        verification_path.write_text("contradictory evidence\n", encoding="utf-8")
        transition(root, "stale-feedback", "INSPECT")
        assert load_state(root, "stale-feedback")["proof_contract"] is None

        initialize(root, "forward-contract", "Preserve initial proof", "owner", [], [], [], [])
        transition(root, "forward-contract", "INSPECT")
        record_proof_contract(root, "forward-contract", {
            "claim": "Local edit preserves behavior", "surface": "artifact",
            "action": "inspect artifact", "expect": "only requested text changes", "cleanup": "none",
        })
        original = load_state(root, "forward-contract")["proof_contract"]
        transition(root, "forward-contract", "PROOF_CONTRACT")
        assert load_state(root, "forward-contract")["proof_contract"] == original
        transition(root, "forward-contract", "ACT")

        initialize(root, "main-run", "Prove state transitions", "integration-owner", ["open-pr"], ["deploy"], ["source.txt"], [])
        initial_status = status(root, "main-run")
        if (
            initial_status["declared_authorities"] != ["open-pr"]
            or initial_status["declared_prohibitions"] != ["deploy"]
        ):
            raise AssertionError("status omitted declared authority boundaries")
        if initial_status["verification_present"] or initial_status["review_present"]:
            raise AssertionError("status reported absent evidence as present")
        if os.name != "nt":
            assert run_directory(root, "main-run").stat().st_mode & 0o777 == 0o700
            assert state_path(root, "main-run").stat().st_mode & 0o777 == 0o600
        try:
            transition(root, "main-run", "ACT")
        except RunStateError:
            pass
        else:
            raise AssertionError("ACT was accepted without a proof contract")
        transition(root, "main-run", "INSPECT")
        transition(root, "main-run", "PROOF_CONTRACT")
        pre_edit_pass, _ = check_gate(root, "main-run", "pre-edit")
        if pre_edit_pass:
            raise AssertionError("pre-edit gate passed without a proof contract")
        try:
            record_proof_contract(
                root,
                "main-run",
                {
                    "claim": "Incomplete",
                    "surface": "test",
                    "action": "test",
                },
            )
        except RunStateError:
            pass
        else:
            raise AssertionError("incomplete proof contract was accepted")
        record_proof_contract(
            root,
            "main-run",
            {
                "claim": "The changed behavior is observable",
                "surface": "test fixture",
                "action": "exercise fixture",
                "expect": "expected value appears",
                "cleanup": "remove temporary evidence",
            },
        )
        pre_edit_pass, _ = check_gate(root, "main-run", "pre-edit")
        if not pre_edit_pass:
            raise AssertionError("pre-edit gate failed with valid proof contract")
        verify_pass, _ = check_gate(root, "main-run", "verify")
        if verify_pass:
            raise AssertionError("verify gate passed before verification receipt")
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
        verify_pass, _ = check_gate(root, "main-run", "verify")
        if not verify_pass:
            raise AssertionError("verify gate failed with fresh verification receipt")
        ship_pass, _ = check_gate(root, "main-run", "ship")
        if ship_pass:
            raise AssertionError("ship gate passed before independent review")
        verified_status = status(root, "main-run")
        if (
            not verified_status["verification_present"]
            or verified_status["verification_verdict"] != "verified"
            or verified_status["verification_actor"] != "integration-owner"
        ):
            raise AssertionError("status omitted verification evidence identity")
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
        ship_pass, _ = check_gate(root, "main-run", "ship")
        if not ship_pass:
            raise AssertionError("ship gate failed with fresh verification and review")
        integer_state = load_state(root, "main-run")
        malformed_epoch = json.loads(json.dumps(integer_state))
        malformed_epoch["epoch"] = True
        if "epoch must be a non-negative integer" not in schema_errors(
            malformed_epoch, root, "main-run"
        ):
            raise AssertionError("boolean run epoch was accepted as an integer")
        malformed_sequence = json.loads(json.dumps(integer_state))
        malformed_sequence["sequence"] = True
        if "sequence must be a positive integer" not in schema_errors(
            malformed_sequence, root, "main-run"
        ):
            raise AssertionError("boolean run sequence was accepted as an integer")
        malformed_event_sequence = json.loads(json.dumps(integer_state))
        malformed_event_sequence["events"][0]["sequence"] = True
        if "event sequence is invalid" not in schema_errors(
            malformed_event_sequence, root, "main-run"
        ):
            raise AssertionError("boolean event sequence was accepted as an integer")
        merge_pass, _ = check_gate(root, "main-run", "merge")
        if merge_pass:
            raise AssertionError("merge gate passed without explicit-merge authority")
        main_state_path = state_path(root, "main-run")
        untampered_authorities = main_state_path.read_bytes()
        granted = load_state(root, "main-run")
        granted["authorities"] = ["open-pr", "explicit-merge"]
        atomic_write_json(main_state_path, granted)
        merge_gate_pass, merge_reason = check_gate(root, "main-run", "merge")
        provider_receipt_present = provider_receipt_path(root, "main-run").is_file()
        if merge_gate_pass or provider_receipt_present:
            raise AssertionError("merge gate passed without a bound pr_watch ready receipt")
        if "green evidence confirmed" in merge_reason:
            raise AssertionError("merge gate claimed green evidence without provider receipt")
        if "unattested" not in merge_reason:
            raise AssertionError("merge gate did not report authority-unattested without provider receipt")

        def write_provider_receipt(**observation_overrides: Any) -> Path:
            receipt = provider_receipt_path(root, "main-run")
            write_test_provider_receipt(receipt, require_git_root(root), **observation_overrides)
            return receipt

        write_provider_receipt(draft=True)
        merge_gate_pass, merge_reason = check_gate(root, "main-run", "merge")
        if merge_gate_pass:
            raise AssertionError("merge gate passed a draft provider receipt")
        write_provider_receipt(review_decision="changes_requested")
        merge_gate_pass, merge_reason = check_gate(root, "main-run", "merge")
        if merge_gate_pass:
            raise AssertionError("merge gate passed a changes_requested provider receipt")
        write_provider_receipt()
        merge_gate_pass, merge_reason = check_gate(
            root, "main-run", "merge", require_git_root(root)
        )
        provider_receipt_present = provider_receipt_path(root, "main-run").is_file()
        if not merge_gate_pass or not provider_receipt_present:
            raise AssertionError(f"merge gate failed with a bound pr_watch ready receipt: {merge_reason}")
        if "green evidence confirmed" in merge_reason:
            raise AssertionError("merge success text claimed green evidence without naming the receipt")
        provider_receipt_path(root, "main-run").unlink()
        atomic_write(main_state_path, untampered_authorities)
        reviewed_status = status(root, "main-run")
        if (
            not reviewed_status["review_present"]
            or reviewed_status["review_verdict"] != "pass"
            or reviewed_status["review_actor"] != "reviewer"
        ):
            raise AssertionError("status omitted independent review identity")
        transition(root, "main-run", "LEARN")
        transition(root, "main-run", "VERIFY")
        try:
            transition(root, "main-run", "REVIEW")
        except RunStateError:
            pass
        else:
            raise AssertionError("old verification crossed an epoch boundary")
        record_receipt(root, "main-run", "verification", "Learning verified", learning_verification_receipt, "verifier", "verified")
        transition(root, "main-run", "REVIEW")
        try:
            record_receipt(
                root,
                "main-run",
                "review",
                "Verifier self review",
                learning_review_receipt,
                "VERIFIER",
                "pass",
            )
        except RunStateError:
            pass
        else:
            raise AssertionError("verification actor was accepted as independent reviewer")
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
        if not validation_errors(root, "main-run") or not status(root, "main-run")["review_stale"]:
            raise AssertionError("receipt URI diverged from its content binding")
        atomic_write(main_state_path, untampered_main)
        tampered_reviewer = load_state(root, "main-run")
        tampered_reviewer["review"]["actor"] = "integration-owner"
        atomic_write_json(main_state_path, tampered_reviewer)
        if not validation_errors(root, "main-run"):
            raise AssertionError("tampered reviewer identity was accepted")
        atomic_write(main_state_path, untampered_main)
        tampered_reviewer = load_state(root, "main-run")
        tampered_reviewer["review"]["actor"] = "VERIFIER"
        atomic_write_json(main_state_path, tampered_reviewer)
        if not validation_errors(root, "main-run"):
            raise AssertionError("tampered verifier self-review was accepted")
        atomic_write(main_state_path, untampered_main)

        malformed_evidence = load_state(root, "main-run")
        malformed_evidence["verification"] = {}
        malformed_evidence["review"] = None
        atomic_write_json(main_state_path, malformed_evidence)
        malformed_status = status(root, "main-run")
        if not (
            malformed_status["verification_present"]
            and malformed_status["verification_stale"]
            and not malformed_status["review_present"]
            and not malformed_status["review_stale"]
        ):
            raise AssertionError("malformed present evidence was not reported stale")
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
        symlink_targets = (nested / "target-a", nested / "target-b")
        for target in symlink_targets:
            target.mkdir()
            (target / "payload.txt").write_text("same nested content\n", encoding="utf-8")
        if symlink_supported:
            nested_link = nested / "directory-link"
            nested_link.symlink_to(symlink_targets[0].name, target_is_directory=True)
            before_nested_symlink_change = current_snapshot(root)
            nested_link.unlink()
            nested_link.symlink_to(symlink_targets[1].name, target_is_directory=True)
            if current_snapshot(root) == before_nested_symlink_change:
                raise AssertionError("embedded Git repository symlink change bypassed the snapshot")

        before_nested_change = current_snapshot(root)
        (nested / "source.txt").write_text("nested dirty state\n", encoding="utf-8")
        if current_snapshot(root) == before_nested_change:
            raise AssertionError("embedded Git repository content bypassed the snapshot")

        escaped_target = evidence_root / "escaped-run-store"
        escaped_target.mkdir()
        if symlink_supported:
            linked_store = git_store_root(root) / "linked-run"
            linked_store.parent.mkdir(parents=True, exist_ok=True)
            linked_store.symlink_to(escaped_target)
            try:
                initialize(root, "linked-run", "Reject escaped stores", "owner", [], [], [], [])
            except RunStateError:
                pass
            else:
                raise AssertionError("symlinked run store escaped Git metadata")
            if (escaped_target / "state.json").exists():
                raise AssertionError("symlinked run store wrote outside Git metadata")

            guard_directory = run_directory(root, "guard-run")
            guard_directory.mkdir(parents=True)
            guard_target = evidence_root / "guard-target"
            guard_target.write_text("unchanged\n", encoding="utf-8")
            (guard_directory / ".lock.guard").symlink_to(guard_target)
            try:
                initialize(root, "guard-run", "Reject linked guard", "owner", [], [], [], [])
            except RunStateError:
                pass
            else:
                raise AssertionError("symlinked lock guard was accepted")
            if guard_target.read_text(encoding="utf-8") != "unchanged\n":
                raise AssertionError("symlinked lock guard target was modified")

        initialize(root, "blocked-run", "Bound retries", "owner", [], [], [], [])
        transition(root, "blocked-run", "INSPECT")
        try:
            record_failure(root, "blocked-run", "Invalid class", "key", failure_class="unknown")
        except RunStateError:
            pass
        else:
            raise AssertionError("invalid failure class was accepted")
        record_failure(root, "blocked-run", "Same blocker", "missing-runtime", failure_class="environment")
        (root / "new.txt").write_text("new evidence\n", encoding="utf-8")
        changed_snapshot = current_snapshot(root)
        changed_state = record_failure(
            root, "blocked-run", "Same blocker after snapshot change", "missing-runtime", failure_class="environment"
        )
        if changed_state["last_failure"]["count"] != 2:
            raise AssertionError("same blocker count did not continue after snapshot change")
        if (
            changed_state["last_failure"]["snapshot"] != changed_snapshot
            or changed_state["events"][-1]["snapshot"] != changed_snapshot
        ):
            raise AssertionError("failure did not retain its current snapshot evidence")
        record_failure(root, "blocked-run", "Third same blocker", "missing-runtime", failure_class="environment")
        blocked_state = load_state(root, "blocked-run")
        if blocked_state["node"] != "BLOCKED":
            raise AssertionError("third same blocker did not stop the run")
        if blocked_state["last_failure"]["count"] != 3:
            raise AssertionError("blocked streak did not retain its failure count")
        if "[environment]" not in str(blocked_state.get("blocked_reason")):
            raise AssertionError("blocked reason omitted failure class")

        initialize(root, "streak-boundaries-run", "Reset changed failure identity", "owner", [], [], [], [])
        transition(root, "streak-boundaries-run", "INSPECT")
        record_failure(root, "streak-boundaries-run", "First failure", "shared-key", failure_class="environment")
        changed_class = record_failure(
            root, "streak-boundaries-run", "Changed failure class", "shared-key", failure_class="implementation"
        )
        if changed_class["last_failure"]["count"] != 1:
            raise AssertionError("blocker count did not reset after failure class changed")
        transition(root, "streak-boundaries-run", "PROOF_CONTRACT")
        changed_node = record_failure(
            root, "streak-boundaries-run", "Changed graph node", "shared-key", failure_class="implementation"
        )
        if changed_node["last_failure"]["count"] != 1:
            raise AssertionError("blocker count did not reset after graph node changed")
        changed_blocker = record_failure(
            root, "streak-boundaries-run", "Changed blocker key", "different-key", failure_class="implementation"
        )
        if changed_blocker["last_failure"]["count"] != 1:
            raise AssertionError("blocker count did not reset after blocker changed")

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

        if symlink_supported:
            linked_state_target = atomic_path.with_name("state.real.json")
            os.replace(atomic_path, linked_state_target)
            atomic_path.symlink_to(linked_state_target)
            try:
                try:
                    load_state(root, "atomic-run")
                except RunStateError:
                    pass
                else:
                    raise AssertionError("symlinked run state was accepted")
            finally:
                atomic_path.unlink()
                os.replace(linked_state_target, atomic_path)

        oversized_state_target = atomic_path.with_name("state.oversized.json")
        os.replace(atomic_path, oversized_state_target)
        atomic_path.write_bytes(b"{" + b" " * MAX_STATE_BYTES + b"}")
        try:
            try:
                load_state(root, "atomic-run")
            except RunStateError:
                pass
            else:
                raise AssertionError("oversized run state was accepted")
        finally:
            atomic_path.unlink()
            os.replace(oversized_state_target, atomic_path)

        lock_path = run_directory(root, "atomic-run") / ".lock"
        lock_path.write_text(
            json.dumps({"pid": os.getpid(), "host": socket.gethostname(), "created_at": now(), "token": "a" * 32}),
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
            lock_path.write_text(
                json.dumps({"pid": True, "host": socket.gethostname(), "created_at": now(), "token": "a" * 32}),
                encoding="utf-8",
            )
            try:
                recover_stale_lock(root, "atomic-run")
            except RunStateError as error:
                if "lock identity is invalid" not in str(error):
                    raise
            else:
                raise AssertionError("boolean lock pid was accepted as an integer")
        finally:
            lock_path.write_text(
                json.dumps({"pid": 99999999, "host": socket.gethostname(), "created_at": now(), "token": "b" * 32}),
                encoding="utf-8",
            )
        recover_stale_lock(root, "atomic-run")
        if lock_path.exists():
            raise AssertionError("stale run lock was not recovered")

        replacement_path = run_directory(root, "replacement-run") / ".lock"
        with run_lock(root, "replacement-run"):
            replacement_path.write_text(
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
        if not replacement_path.exists():
            raise AssertionError("run owner removed a replacement lock it did not own")
        recover_stale_lock(root, "replacement-run")

        oversized_path = run_directory(root, "oversized-lock-run") / ".lock"
        with run_lock(root, "oversized-lock-run"):
            oversized_path.write_bytes(b"x" * (MAX_LOCK_BYTES + 1))
        if not oversized_path.exists():
            raise AssertionError("run owner removed an oversized replacement lock")
        oversized_path.unlink()

        if symlink_supported:
            linked_lock_path = run_directory(root, "linked-lock-run") / ".lock"
            linked_lock_target = evidence_root / "linked-lock-target"
            linked_lock_target.write_text("unchanged\n", encoding="utf-8")
            with run_lock(root, "linked-lock-run"):
                linked_lock_path.unlink()
                linked_lock_path.symlink_to(linked_lock_target)
            if not linked_lock_path.is_symlink():
                raise AssertionError("run owner removed a symlinked replacement lock")
            if linked_lock_target.read_text(encoding="utf-8") != "unchanged\n":
                raise AssertionError("run owner read or modified a symlinked lock target")
            linked_lock_path.unlink()

        malformed = load_state(root, "atomic-run")
        malformed["authorities"] = [{}]
        atomic_write_json(state_path(root, "atomic-run"), malformed)
        if not validation_errors(root, "atomic-run"):
            raise AssertionError("non-string authority was accepted")

        receipt_source = load_state(root, "main-run")
        receipt_source["events"] *= 100
        compact = compact_state_receipt(root, receipt_source, "self-test")
        if len(json.dumps(compact)) > 1024 or "events" in compact or "objective" in compact:
            raise AssertionError("compact mutation receipt grew with the state ledger")

        tampered = load_state(root, "main-run")
        tampered["run_id"] = "other-run"
        atomic_write_json(state_path(root, "main-run"), tampered)
        if not validation_errors(root, "main-run"):
            raise AssertionError("identity tamper was accepted")
        return symlink_supported


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
    init_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")

    for command in (
        "transition",
        "record",
        "checkpoint",
        "status",
        "validate",
        "unlock",
        "check-gate",
    ):
        command_parser = subparsers.add_parser(command)
        command_parser.add_argument("--root", type=Path, default=Path.cwd())
        command_parser.add_argument("--run-id", required=True)
        if command == "check-gate":
            command_parser.add_argument(
                "--gate", required=True, choices=("pre-edit", "verify", "commit", "ship", "merge")
            )
            command_parser.add_argument(
                "--base-head",
                help="Freshly fetched commit of the merge target; required by the merge gate",
            )
        elif command == "transition":
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
            command_parser.add_argument(
                "--failure-class", choices=("implementation", "verifier", "environment")
            )
            command_parser.add_argument("--claim")
            command_parser.add_argument("--surface")
            command_parser.add_argument("--action")
            command_parser.add_argument("--expect")
            command_parser.add_argument("--expected")
            command_parser.add_argument("--cleanup")
            command_parser.add_argument("--hypothesis")
            command_parser.add_argument("--metric")
            command_parser.add_argument("--value")
            command_parser.add_argument("--unit")
            command_parser.add_argument("--next-decision")
        if command in {"transition", "record"}:
            command_parser.add_argument("--full", action="store_true", help="Print the complete state ledger")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.self_test:
        symlink_checks_passed = run_self_test()
        symlink_status = "passed" if symlink_checks_passed else "skipped (creation unsupported)"
        print(f"Patpat run-state self-test passed; symlink assertions {symlink_status}.")
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
            if args.full:
                print(json.dumps({"store": str(run_directory(root, args.run_id)), "state": state}, indent=2))
            else:
                print_state_result(root, state, "init", False)
        elif args.command == "transition":
            print_state_result(root, transition(root, args.run_id, args.to), "transition", args.full)
        elif args.command == "check-gate":
            passed, reason = check_gate(root, args.run_id, args.gate, args.base_head)
            payload = {
                "run_id": args.run_id,
                "gate": args.gate,
                "pass": passed,
                "reason": reason,
                "node": load_state(root, args.run_id).get("node"),
            }
            print(json.dumps(payload, indent=2))
            return 0 if passed else 1
        elif args.command == "record":
            if args.kind == "proof-contract":
                expect_val = args.expect or args.expected
                state = record_proof_contract(
                    root,
                    args.run_id,
                    {
                        "claim": args.claim,
                        "surface": args.surface,
                        "action": args.action,
                        "expect": expect_val,
                        "cleanup": args.cleanup,
                    },
                )
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
                state = record_failure(
                    root,
                    args.run_id,
                    args.summary,
                    args.blocker_key,
                    failure_class=args.failure_class or "implementation",
                )
            else:
                if not args.summary:
                    raise RunStateError("decision requires summary")
                state = record_decision(root, args.run_id, args.summary)
            print_state_result(root, state, f"record:{args.kind}", args.full)
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
