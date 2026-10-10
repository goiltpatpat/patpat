#!/usr/bin/env python3
"""Persist Patpat Loop across later turns when the host trusts plugin hooks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

STATE_SCHEMA = 2
DEFAULT_TTL_MS = 30 * 24 * 60 * 60 * 1000
MAX_SESSION_ID_LENGTH = 512
MAX_STATE_BYTES = 16 * 1024
MAX_STDIN_BYTES = 256 * 1024
ACTIVATION_ID = re.compile(r"^[0-9a-f]{64}$")
STATE_FILENAME = re.compile(r"^[0-9a-f]{64}\.json$")
DIRECT_ACTIVATION = re.compile(
    r"^\s*(?:/|\$)patpat(?:-loop)?(?:$|\s+(?!(?:do\s+not|don't|dont|never|not|without)\b)\S)",
    re.IGNORECASE,
)
USE_ACTIVATION = re.compile(
    r"^\s*use\s+(?:(?:/|\$)?patpat(?:-loop)?)\s+(?:to|for)\s+"
    r"(?!(?:not|never|avoid|without|docs?|document|documentation|examples?|quote)\b)\S",
    re.IGNORECASE,
)
DISABLE = re.compile(
    r"^\s*(?:disable\s+(?:/|\$)?patpat(?:-loop)?|opt\s+out(?:\s+of)?\s+patpat(?:-loop)?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
STICKY_CONTEXT = (
    "Patpat Loop is active for this session. Apply /patpat (`patpat-loop`) for this turn. "
    "Follow the operating protocol. Explicit activation authorizes the loop, proof, and verify; default commit-and-PR still requires delivery intent. "
    "A higher-priority repository rule or opt-out still blocks delivery. Merge only on explicit land or merge language. "
    "Do not deploy, force-push, or publish a package by implication."
)
PLUGIN_DATA_ENV_KEYS = ("PLUGIN_DATA", "GROK_PLUGIN_DATA", "CLAUDE_PLUGIN_DATA")


def hash_value(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def resolve_plugin_data(environment: Mapping[str, str] | None = None) -> str | None:
    values = os.environ if environment is None else environment
    for key in PLUGIN_DATA_ENV_KEYS:
        value = values.get(key)
        if value:
            return value
    return None


def session_key(session_id: object) -> str | None:
    if not isinstance(session_id, str) or not session_id or len(session_id) > MAX_SESSION_ID_LENGTH:
        return None
    return hash_value(session_id)


def project_fingerprint(cwd: object) -> str | None:
    if not isinstance(cwd, str) or not cwd or len(cwd) > 4096 or "\0" in cwd:
        return None
    return hash_value(str(Path(cwd)))


def classify_prompt(prompt: object) -> str:
    if not isinstance(prompt, str):
        return "inactive"
    if DISABLE.fullmatch(prompt.strip()) or DISABLE.match(prompt.strip()):
        return "disable"
    if DIRECT_ACTIVATION.match(prompt) or USE_ACTIVATION.match(prompt):
        return "activate"
    return "inactive"


def state_paths(plugin_data: object, session_id: object) -> dict[str, Path] | None:
    key = session_key(session_id)
    if not key or not isinstance(plugin_data, str) or not plugin_data:
        return None
    try:
        root = Path(plugin_data).resolve() / "patpat-loop"
    except (OSError, RuntimeError, ValueError):
        return None
    return {
        "root": root,
        "state": root / "sessions" / f"{key}.json",
        "receipt": root / "receipts" / f"{key}.json",
    }


def _is_link_or_reparse_point(metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    )


def _real_directory_identity(path: Path) -> tuple[int, int] | None:
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return None
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or _is_link_or_reparse_point(metadata)
        or os.path.normcase(str(path)) != os.path.normcase(str(resolved))
    ):
        return None
    return metadata.st_dev, metadata.st_ino


def _state_directory_binding(directory: Path) -> tuple[tuple[int, int], ...] | None:
    """Reject static redirects and bind path identities.

    This does not provide a race-free directory handle.
    """
    if (
        directory.name not in {"sessions", "receipts"}
        or directory.parent.name != "patpat-loop"
    ):
        return None
    binding: list[tuple[int, int]] = []
    for path in (directory.parent.parent, directory.parent, directory):
        identity = _real_directory_identity(path)
        if identity is None:
            return None
        binding.append(identity)
    return tuple(binding)


def ensure_state_directories(plugin_data: str) -> bool:
    """Create the state layout only beneath the host's canonical data root."""
    try:
        base = Path(plugin_data)
        base.mkdir(parents=True, exist_ok=True)
        if _real_directory_identity(base) is None:
            return False
        root = base / "patpat-loop"
        for directory in (root, root / "sessions", root / "receipts"):
            try:
                directory.mkdir()
            except FileExistsError:
                pass
            if _real_directory_identity(directory) is None:
                return False
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def atomic_write(target: Path, value: dict[str, Any]) -> None:
    binding = _state_directory_binding(target.parent)
    if binding is None or STATE_FILENAME.fullmatch(target.name) is None:
        raise OSError("state path is outside a safe Patpat state directory")
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    path = Path(temporary)
    try:
        if _state_directory_binding(target.parent) != binding:
            raise OSError("state directory changed while creating a temporary file")
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = -1
        with handle:
            json.dump(value, handle)
            handle.write("\n")
        if _state_directory_binding(target.parent) != binding:
            raise OSError("state directory changed before publishing state")
        os.replace(path, target)
    except Exception:
        if fd >= 0:
            os.close(fd)
        if _state_directory_binding(target.parent) == binding and path.exists():
            path.unlink()
        raise


def read_json(target: Path, maximum: int = MAX_STATE_BYTES) -> dict[str, Any] | None:
    binding = _state_directory_binding(target.parent)
    if binding is None or STATE_FILENAME.fullmatch(target.name) is None:
        return None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        before = target.lstat()
    except (FileNotFoundError, OSError):
        return None
    if _state_directory_binding(target.parent) != binding:
        return None
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > maximum
    ):
        return None
    try:
        descriptor = os.open(target, flags)
    except (FileNotFoundError, OSError):
        return None
    try:
        metadata = os.fstat(descriptor)
        if (
            _state_directory_binding(target.parent) != binding
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > maximum
            or (metadata.st_dev, metadata.st_ino) != (before.st_dev, before.st_ino)
        ):
            return None
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    finally:
        os.close(descriptor)
    return value if isinstance(value, dict) else None


def remove_state_path(target: Path) -> None:
    """Remove only the state entry itself; never follow a replacement link."""
    binding = _state_directory_binding(target.parent)
    if binding is None or STATE_FILENAME.fullmatch(target.name) is None:
        return
    try:
        metadata = target.lstat()
    except (FileNotFoundError, OSError):
        return
    if _state_directory_binding(target.parent) != binding:
        return
    if stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        try:
            target.unlink()
        except OSError:
            pass


def normalize_event(payload: dict[str, Any]) -> str:
    raw = payload.get("hook_event_name") or payload.get("hookEventName") or payload.get("event") or ""
    if not isinstance(raw, str):
        return ""
    aliases = {
        "sessionstart": "SessionStart",
        "sessionend": "SessionEnd",
        "userpromptsubmit": "UserPromptSubmit",
        "beforesubmitprompt": "UserPromptSubmit",
        "beforeSubmitPrompt": "UserPromptSubmit",
    }
    return aliases.get(raw.replace("_", "").lower(), raw)


def extract_session_id(payload: dict[str, Any]) -> object:
    return payload.get("session_id") or payload.get("sessionId") or payload.get("conversation_id")


def extract_cwd(payload: dict[str, Any]) -> object:
    cwd = payload.get("cwd") or payload.get("workspace_root")
    if isinstance(cwd, str):
        return cwd
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str):
        return roots[0]
    return None


def extract_prompt(payload: dict[str, Any]) -> object:
    prompt = payload.get("prompt") or payload.get("prompt_text") or payload.get("user_prompt")
    if isinstance(prompt, str):
        return prompt
    message = payload.get("prompt")
    if isinstance(message, dict) and isinstance(message.get("text"), str):
        return message["text"]
    return None


def context_output(event: str, text: str) -> dict[str, Any]:
    return {
        "additional_context": text,
        "hookSpecificOutput": {"hookEventName": event, "additionalContext": text},
    }


def now_iso(now_ms: int) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).isoformat()


def state_value(
    fingerprint: str,
    session_binding: str,
    activation_id: str,
    now_ms: int,
    created_at: str | None,
) -> dict[str, Any]:
    timestamp = now_iso(now_ms)
    return {
        "schema": STATE_SCHEMA,
        "active": True,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        "projectFingerprint": fingerprint,
        "sessionBinding": session_binding,
        "activationId": activation_id,
    }


def receipt_value(
    fingerprint: str,
    session_binding: str,
    activation_id: str,
    event: str,
    now_ms: int,
) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "event": event,
        "lastHookAt": now_iso(now_ms),
        "projectFingerprint": fingerprint,
        "sessionBinding": session_binding,
        "activationId": activation_id,
    }


def timestamp_ms(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        from datetime import datetime, timedelta

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            return None
        return parsed.timestamp() * 1000
    except (ValueError, OverflowError):
        return None


def state_pair_is_valid(
    state: dict[str, Any],
    receipt: dict[str, Any],
    fingerprint: str,
    session_binding: str,
    now_ms: int,
    ttl_ms: int,
) -> bool:
    state_keys = {
        "schema",
        "active",
        "createdAt",
        "updatedAt",
        "projectFingerprint",
        "sessionBinding",
        "activationId",
    }
    receipt_keys = {
        "schema",
        "event",
        "lastHookAt",
        "projectFingerprint",
        "sessionBinding",
        "activationId",
    }
    if set(state) != state_keys or set(receipt) != receipt_keys:
        return False
    activation_id = state.get("activationId")
    updated_ms = timestamp_ms(state.get("updatedAt"))
    created_ms = timestamp_ms(state.get("createdAt"))
    receipt_ms = timestamp_ms(receipt.get("lastHookAt"))
    return bool(
        state.get("schema") == STATE_SCHEMA
        and receipt.get("schema") == STATE_SCHEMA
        and state.get("active") is True
        and state.get("projectFingerprint") == fingerprint
        and receipt.get("projectFingerprint") == fingerprint
        and state.get("sessionBinding") == session_binding
        and receipt.get("sessionBinding") == session_binding
        and isinstance(activation_id, str)
        and ACTIVATION_ID.fullmatch(activation_id)
        and receipt.get("activationId") == activation_id
        and receipt.get("event") in {"UserPromptSubmit", "SessionStart", "SessionEnd"}
        and updated_ms is not None
        and created_ms is not None
        and receipt_ms is not None
        and created_ms <= updated_ms == receipt_ms <= now_ms
        and now_ms - updated_ms <= ttl_ms
    )


def collect_expired(plugin_data: str, now_ms: int, ttl_ms: int) -> None:
    root = Path(plugin_data) / "patpat-loop"
    for folder in ("sessions", "receipts"):
        directory = root / folder
        binding = _state_directory_binding(directory)
        if binding is None:
            continue
        try:
            paths = tuple(directory.iterdir())
        except OSError:
            continue
        if _state_directory_binding(directory) != binding:
            continue
        for path in paths:
            if (
                STATE_FILENAME.fullmatch(path.name) is None
                or _state_directory_binding(directory) != binding
            ):
                continue
            value = read_json(path)
            parsed = timestamp_ms(
                (value or {}).get("updatedAt") or (value or {}).get("lastHookAt")
            )
            if (
                not value
                or value.get("schema") != STATE_SCHEMA
                or parsed is None
                or parsed > now_ms
                or now_ms - parsed > ttl_ms
            ):
                remove_state_path(path)


def read_active_state(
    plugin_data: str,
    session_id: object,
    cwd: object,
    now_ms: int,
    ttl_ms: int,
) -> dict[str, Any] | None:
    targets = state_paths(plugin_data, session_id)
    fingerprint = project_fingerprint(cwd)
    binding = session_key(session_id)
    if not targets or not fingerprint or not binding:
        return None
    state = read_json(targets["state"])
    receipt = read_json(targets["receipt"])
    if not state or not receipt or not state_pair_is_valid(
        state, receipt, fingerprint, binding, now_ms, ttl_ms
    ):
        remove_state_path(targets["state"])
        remove_state_path(targets["receipt"])
        return None
    return state


def persist(targets: dict[str, Path], state: dict[str, Any], receipt: dict[str, Any]) -> None:
    atomic_write(targets["state"], state)
    atomic_write(targets["receipt"], receipt)


def handle_hook(payload: dict[str, Any], plugin_data: str | None = None, now_ms: int | None = None) -> dict[str, Any] | None:
    plugin_data = plugin_data if plugin_data is not None else resolve_plugin_data()
    now_ms = now_ms if now_ms is not None else int(__import__("time").time() * 1000)
    if not plugin_data:
        return None
    session_id = extract_session_id(payload)
    cwd = extract_cwd(payload)
    targets = state_paths(plugin_data, session_id)
    fingerprint = project_fingerprint(cwd)
    binding = session_key(session_id)
    if not targets or not fingerprint or not binding:
        return None
    plugin_data = str(targets["root"].parent)
    event = normalize_event(payload)
    ttl_ms = DEFAULT_TTL_MS
    if event == "SessionEnd":
        collect_expired(plugin_data, now_ms, ttl_ms)
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        if current:
            activation_id = str(current["activationId"])
            persist(
                targets,
                state_value(
                    fingerprint,
                    binding,
                    activation_id,
                    now_ms,
                    str(current.get("createdAt")),
                ),
                receipt_value(fingerprint, binding, activation_id, event, now_ms),
            )
        return None
    if event == "SessionStart":
        source = payload.get("source")
        if source not in {"resume", "compact"}:
            return None
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        if not current:
            return None
        activation_id = str(current["activationId"])
        persist(
            targets,
            state_value(
                fingerprint,
                binding,
                activation_id,
                now_ms,
                str(current.get("createdAt")),
            ),
            receipt_value(fingerprint, binding, activation_id, event, now_ms),
        )
        return context_output(event, STICKY_CONTEXT)
    if event != "UserPromptSubmit":
        return None
    action = classify_prompt(extract_prompt(payload))
    if action == "disable":
        remove_state_path(targets["state"])
        remove_state_path(targets["receipt"])
        return None
    if action == "activate":
        if not ensure_state_directories(plugin_data):
            return None
        collect_expired(plugin_data, now_ms, ttl_ms)
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        activation_id = secrets.token_hex(32)
        persist(
            targets,
            state_value(
                fingerprint,
                binding,
                activation_id,
                now_ms,
                None if not current else str(current.get("createdAt")),
            ),
            receipt_value(fingerprint, binding, activation_id, event, now_ms),
        )
        return context_output(
            event,
            "Patpat sticky receipt: trusted session hook persisted /patpat. "
            "The skill supplies activation-turn behavior. After proof, keep local reversible work light without delivery intent; default commit-and-PR only when delivery intent exists. "
            "A higher-priority repository rule or opt-out still blocks delivery. Merge requires explicit land or merge language.",
        )
    current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
    if not current:
        return None
    activation_id = str(current["activationId"])
    persist(
        targets,
        state_value(
            fingerprint,
            binding,
            activation_id,
            now_ms,
            str(current.get("createdAt")),
        ),
        receipt_value(fingerprint, binding, activation_id, event, now_ms),
    )
    return context_output(event, STICKY_CONTEXT)


def run_self_test() -> None:
    affirmative = (
        "/patpat",
        "/patpat-loop fix this",
        "$patpat verify this",
        "$patpat-loop land this",
        "Use patpat to inspect this repository",
        "use /patpat-loop for this engineering task",
    )
    for prompt in affirmative:
        if classify_prompt(prompt) != "activate":
            raise AssertionError(f"affirmative activation was rejected: {prompt!r}")
    inactive = (
        "Do not activate /patpat for this task.",
        "Explain what /patpat does without enabling it.",
        "The docs say /patpat starts the loop.",
        "Example: /patpat fix the bug",
        "`/patpat fix the bug`",
        '"/patpat fix the bug" is an example.',
        "- /patpat fix the bug",
        "use patpat as an example",
        "/patpat do not activate this mode",
        "use patpat to not activate this mode",
        "use patpat for documentation without activation",
        "use $patpat-setup on this host",
        "do not use patpat to modify this repository",
    )
    for prompt in inactive:
        if classify_prompt(prompt) != "inactive":
            raise AssertionError(f"non-affirmative prompt activated Patpat: {prompt!r}")
    if classify_prompt("disable /patpat") != "disable":
        raise AssertionError("disable command was not preserved")

    with tempfile.TemporaryDirectory(prefix="patpat-hook-") as directory:
        plugin_data = str(Path(directory) / "plugin-data")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "cwd": str(Path(directory) / "project"),
            "prompt": "/patpat reproduce this flake, then land the PR",
        }
        activated = handle_hook(payload, plugin_data=plugin_data, now_ms=1_000)
        if not activated or "sticky receipt" not in json.dumps(activated):
            raise AssertionError("activation did not persist a sticky receipt")
        targets = state_paths(plugin_data, payload["session_id"])
        if not targets:
            raise AssertionError("test session did not resolve state paths")
        state = read_json(targets["state"])
        receipt = read_json(targets["receipt"])
        if not state or not receipt or state.get("schema") != STATE_SCHEMA:
            raise AssertionError("activation did not persist schema-v2 state and receipt")
        if os.name != "nt" and stat.S_IMODE(targets["state"].stat().st_mode) != 0o600:
            raise AssertionError("state file mode is not restricted before publication")
        if state.get("activationId") != receipt.get("activationId"):
            raise AssertionError("activation receipt is not bound to state")
        continued = handle_hook(
            {**payload, "prompt": "continue with the failing test"},
            plugin_data=plugin_data,
            now_ms=2_000,
        )
        if not continued or "Patpat Loop is active" not in json.dumps(continued):
            raise AssertionError("later turn did not keep sticky mode")
        setup = handle_hook(
            {**payload, "prompt": "use $patpat-setup on this host"},
            plugin_data=plugin_data,
            now_ms=3_000,
        )
        if setup is None:
            raise AssertionError("unrelated later prompt should still be sticky")
        disabled = handle_hook(
            {**payload, "prompt": "disable /patpat"},
            plugin_data=plugin_data,
            now_ms=4_000,
        )
        if disabled is not None:
            raise AssertionError("disable must clear sticky context")
        after = handle_hook(
            {**payload, "prompt": "continue"},
            plugin_data=plugin_data,
            now_ms=5_000,
        )
        if after is not None:
            raise AssertionError("sticky mode survived disable")

        def activate(now_ms: int) -> dict[str, Path]:
            result = handle_hook(payload, plugin_data=plugin_data, now_ms=now_ms)
            if not result:
                raise AssertionError("test activation failed")
            resolved = state_paths(plugin_data, payload["session_id"])
            if not resolved:
                raise AssertionError("test state path resolution failed")
            return resolved

        forged = activate(10_000)
        remove_state_path(forged["receipt"])
        if handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=11_000):
            raise AssertionError("state without an activation receipt was trusted")

        mismatches = (
            (20_000, "projectFingerprint", "0" * 64, "project"),
            (22_000, "sessionBinding", "0" * 64, "session"),
            (24_000, "activationId", "0" * 64, "activation"),
        )
        for activated_at, field, forged_value, label in mismatches:
            mismatched = activate(activated_at)
            mismatched_receipt = read_json(mismatched["receipt"])
            if not mismatched_receipt:
                raise AssertionError("test receipt was unreadable")
            mismatched_receipt[field] = forged_value
            atomic_write(mismatched["receipt"], mismatched_receipt)
            if handle_hook(
                {**payload, "prompt": "continue"},
                plugin_data=plugin_data,
                now_ms=activated_at + 1_000,
            ):
                raise AssertionError(f"{label}-mismatched activation receipt was trusted")

        legacy = activate(30_000)
        legacy_state = read_json(legacy["state"])
        legacy_receipt = read_json(legacy["receipt"])
        if not legacy_state or not legacy_receipt:
            raise AssertionError("legacy-state fixture was unreadable")
        legacy_state["schema"] = 1
        legacy_receipt["schema"] = 1
        atomic_write(legacy["state"], legacy_state)
        atomic_write(legacy["receipt"], legacy_receipt)
        if handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=31_000):
            raise AssertionError("legacy sticky state survived the schema bump")

        oversized = activate(40_000)
        oversized["state"].write_bytes(b"x" * (MAX_STATE_BYTES + 1))
        if handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=41_000):
            raise AssertionError("oversized state was trusted")

        linked = activate(50_000)
        external = Path(directory) / "external.json"
        external.write_text('{"protected": true}\n', encoding="utf-8")
        remove_state_path(linked["state"])
        linked["state"].symlink_to(external)
        if handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=51_000):
            raise AssertionError("symlinked state was trusted")
        if external.read_text(encoding="utf-8") != '{"protected": true}\n':
            raise AssertionError("symlink rejection modified its target")

        unowned = targets["state"].parent / "unowned.json"
        unowned.write_text("{}\n", encoding="utf-8")
        handle_hook(
            {**payload, "session_id": "cleanup-owner-check", "prompt": "/patpat"},
            plugin_data=plugin_data,
            now_ms=52_000,
        )
        if unowned.read_text(encoding="utf-8") != "{}\n":
            raise AssertionError("expired-state cleanup removed a file outside its owned filename namespace")

        if os.name != "nt":
            protected_mode = Path(directory) / "chmod-race-target.json"
            protected_mode.write_text("protected\n", encoding="utf-8")
            protected_mode.chmod(0o644)
            original_replace = os.replace
            original_chmod = os.chmod

            def replace_then_redirect(
                source: str | os.PathLike[str], destination: str | os.PathLike[str]
            ) -> None:
                original_replace(source, destination)
                Path(destination).unlink()
                Path(destination).symlink_to(protected_mode)

            def reject_path_chmod(*args: Any, **kwargs: Any) -> None:
                raise AssertionError("atomic state publication must not chmod the destination path")

            os.replace = replace_then_redirect  # type: ignore[assignment]
            os.chmod = reject_path_chmod  # type: ignore[assignment]
            try:
                atomic_write(targets["state"], {"race": True})
            finally:
                os.replace = original_replace  # type: ignore[assignment]
                os.chmod = original_chmod  # type: ignore[assignment]
            if stat.S_IMODE(protected_mode.stat().st_mode) != 0o644:
                raise AssertionError("atomic state publication changed a redirected target's permissions")
            remove_state_path(targets["state"])

        def create_directory_redirect(link: Path, destination: Path) -> None:
            if os.name == "nt":
                import shutil
                import subprocess

                command = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
                if command is None:
                    raise AssertionError("Windows junction regression requires PowerShell")
                environment = os.environ.copy()
                environment["PATPAT_TEST_JUNCTION_LINK"] = str(link)
                environment["PATPAT_TEST_JUNCTION_TARGET"] = str(destination)
                result = subprocess.run(
                    [
                        command,
                        "-NoLogo",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "$ErrorActionPreference = 'Stop'; New-Item -ItemType Junction -Path $env:PATPAT_TEST_JUNCTION_LINK -Target $env:PATPAT_TEST_JUNCTION_TARGET | Out-Null",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    env=environment,
                )
                if result.returncode != 0:
                    raise AssertionError(
                        f"Windows junction fixture could not be created: {result.stderr}"
                    )
            else:
                link.symlink_to(destination, target_is_directory=True)
            try:
                metadata = link.lstat()
            except OSError as error:
                raise AssertionError(f"directory redirect fixture is missing: {link}") from error
            if not _is_link_or_reparse_point(metadata):
                raise AssertionError(f"directory redirect fixture was not recognized: {link}")

        for redirected_directory in ("patpat-loop", "sessions", "receipts"):
            with tempfile.TemporaryDirectory(prefix="patpat-hook-redirect-") as redirect_root:
                redirect_base = Path(redirect_root) / "plugin-data"
                redirect_base.mkdir()
                state_root = redirect_base / "patpat-loop"
                outside = Path(redirect_root) / "outside"
                outside.mkdir()
                redirect_session = f"redirect-{redirected_directory}"
                redirect_key = session_key(redirect_session)
                if not redirect_key:
                    raise AssertionError("redirect regression session id did not hash")

                if redirected_directory == "patpat-loop":
                    (outside / "sessions").mkdir()
                    (outside / "receipts").mkdir()
                    redirected_path = state_root
                    victim = outside / "sessions" / f"{redirect_key}.json"
                elif redirected_directory == "sessions":
                    state_root.mkdir()
                    (state_root / "receipts").mkdir()
                    redirected_path = state_root / "sessions"
                    victim = outside / f"{redirect_key}.json"
                else:
                    state_root.mkdir()
                    (state_root / "sessions").mkdir()
                    redirected_path = state_root / "receipts"
                    victim = outside / f"{redirect_key}.json"

                victim.write_text("{}\n", encoding="utf-8")
                create_directory_redirect(redirected_path, outside)
                collect_expired(str(redirect_base), 100_000, DEFAULT_TTL_MS)
                if victim.read_text(encoding="utf-8") != "{}\n":
                    raise AssertionError(f"cleanup followed redirected {redirected_directory} directory")
                redirect_result = handle_hook(
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "session_id": redirect_session,
                        "cwd": str(redirect_root),
                        "prompt": "/patpat verify redirect handling",
                    },
                    plugin_data=str(redirect_base),
                    now_ms=100_000,
                )
                if redirect_result is not None:
                    raise AssertionError(f"activation accepted redirected {redirected_directory} directory")
                if victim.read_text(encoding="utf-8") != "{}\n":
                    raise AssertionError(
                        "activation modified a file through redirected "
                        f"{redirected_directory} directory"
                    )

        wrong_project = activate(60_000)
        if not wrong_project["state"].exists():
            raise AssertionError("project-binding fixture was not created")
        if handle_hook(
            {**payload, "cwd": str(Path(directory) / "other-project"), "prompt": "continue"},
            plugin_data=plugin_data,
            now_ms=61_000,
        ):
            raise AssertionError("state was accepted for a different project")

        nonregular = activate(70_000)
        remove_state_path(nonregular["state"])
        nonregular["state"].mkdir()
        if handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=71_000):
            raise AssertionError("non-regular state was trusted")

        if decode_payload(b"{}") != {}:
            raise AssertionError("bounded payload decoder rejected a valid object")
        if decode_payload(b"[]") is not None:
            raise AssertionError("bounded payload decoder accepted a non-object")
        if decode_payload(b"x" * (MAX_STDIN_BYTES + 1)) is not None:
            raise AssertionError("oversized hook input was accepted")
        missing = handle_hook(payload, plugin_data="", now_ms=6_000)
        if missing is not None:
            raise AssertionError("missing plugin data must fail closed")
        if resolve_plugin_data({"PLUGIN_DATA": "/primary", "GROK_PLUGIN_DATA": "/grok"}) != "/primary":
            raise AssertionError("PLUGIN_DATA must take precedence")
        if resolve_plugin_data({"GROK_PLUGIN_DATA": "/grok"}) != "/grok":
            raise AssertionError("GROK_PLUGIN_DATA was not recognized")
        if resolve_plugin_data({"CLAUDE_PLUGIN_DATA": "/compat"}) != "/compat":
            raise AssertionError("CLAUDE_PLUGIN_DATA compatibility alias was not recognized")
        if resolve_plugin_data({}) is not None:
            raise AssertionError("missing plugin data environment must fail closed")
        expired_payload = {**payload, "session_id": "expired-session"}
        expired = handle_hook(expired_payload, plugin_data=plugin_data, now_ms=80_000)
        expired_targets = state_paths(plugin_data, "expired-session")
        if not expired or not expired_targets:
            raise AssertionError("expired-state fixture could not be activated")
        if handle_hook(
            {**expired_payload, "prompt": "continue"},
            plugin_data=plugin_data,
            now_ms=80_000 + DEFAULT_TTL_MS + 1,
        ):
            raise AssertionError("expired sticky state was trusted")
        if expired_targets["state"].exists() or expired_targets["receipt"].exists():
            raise AssertionError("expired sticky state was not cleared")
    print("Patpat loop sticky-hook self-test passed.")


def decode_payload(raw: bytes) -> dict[str, Any] | None:
    if not raw.strip() or len(raw) > MAX_STDIN_BYTES:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def main() -> int:
    if "--self-test" in sys.argv:
        run_self_test()
        return 0
    payload = decode_payload(sys.stdin.buffer.read(MAX_STDIN_BYTES + 1))
    if payload is None:
        raise ValueError("hook stdin must contain a UTF-8 JSON object within the size limit")
    output = handle_hook(payload)
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Patpat hook error: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1)
