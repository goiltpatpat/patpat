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
MAX_BACKWARD_CLOCK_SKEW_MS = 60 * 1000
MAX_SESSION_ID_LENGTH = 512
MAX_STATE_BYTES = 16 * 1024
MAX_STDIN_BYTES = 256 * 1024
ACTIVATION_ID = re.compile(r"^[0-9a-f]{64}$")
STATE_FILENAME = re.compile(r"^[0-9a-f]{64}\.json$")
# Two-layer language-agnostic design: this deterministic hook matches universal
# explicit syntax (`/` or `$` tokens + canonical English triggers) across all
# languages, while pure natural-language semantic opt-out is interpreted by the LLM
# per operating-protocol.md.
_POLITE_PREFIX = (
    r"(?:(?:hey|hi|hello|yo|ok|okay|alright|sure|thanks|thank\s+you)\b[\s,!:;-]*)*"
    r"(?:(?:please|plz|pls)\b[\s,]*|"
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?))*"
)
_PATPAT_TOKEN = r"(?:/|\$)(?:patpat:)?patpat(?:-loop)?"
DIRECT_ACTIVATION = re.compile(
    rf"^\s*{_POLITE_PREFIX}"
    rf"{_PATPAT_TOKEN}"
    r"(?:[.!?]*\s*$|\s+(?!(?:do\s+not|don't|dont|never|not|without\s+(?:activating|enabling|using|turning\s+on))\b)\S)",
    re.IGNORECASE,
)
USE_ACTIVATION = re.compile(
    rf"^\s*{_POLITE_PREFIX}"
    r"use\s+(?:(?:/|\$)?(?:patpat:)?patpat(?:-loop)?)\s+(?:to|for)\s+"
    r"(?!(?:not|never|avoid|without|docs?|document|documentation|examples?|quote)\b)\S",
    re.IGNORECASE,
)
DISABLE = re.compile(
    rf"^\s*{_POLITE_PREFIX}"
    r"(?:"
    rf"{_PATPAT_TOKEN}\s+(?:off|stop|disable|deactivate|exit)(?=$|[\s.,!?;:])"
    r"|"
    r"(?:(?:disable|deactivate|exit)\s+|"
    r"leave\s+(?!(?:the\s+)?(?:/|\$)?(?:patpat:)?patpat(?:-loop)?\s+(?:active|on|enabled|alone|running|in\s+place)\b)|"
    r"stop(?:\s+using)?\s+|"
    r"(?:turn|switch)\s+off\s+|"
    r"opt\s+out(?:\s+of)?\s+)"
    r"(?:the\s+)?(?:/|\$)?(?:patpat:)?patpat(?:-loop)?(?=$|[\s.,!?;:])(?!\s+from\b)"
    r")",
    re.IGNORECASE,
)
STICKY_CONTEXT = (
    "Patpat Loop is active this session. Use the Patpat Loop skill for this turn; follow the operating protocol. "
    "Re-classify each new task; read the matched playbook for any route not yet read this session instead of recalling it. "
    "A task is design-gated when it adds, removes, swaps, or major-bumps a direct runtime dependency, SDK, or service provider, "
    "or changes auth, permissions, secrets, billing, a persisted schema, a public contract, or CI, release, or deploy definitions: "
    "read the operating protocol and resolve design through patpat-architect. "
    "Auth, billing, secrets, architecture, or cross-cutting work needs independent review before reporting. "
    "Activation authorizes the loop, proof, and verification; default commit/PR needs delivery intent. "
    "Higher-priority repository rules or opt-out block delivery. Merge requires explicit \"land\" or \"merge\". "
    "Do not deploy, force-push, or publish packages by implication. "
    "A preview or staging deploy Patpat starts also needs a named request, fresh verify, independent review, and a stated rollback."
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
    if DISABLE.match(prompt.strip()):
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
    fingerprint: str, session_binding: str, activation_id: str, now_ms: int, created_at: str | None
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
    fingerprint: str, session_binding: str, activation_id: str, event: str, now_ms: int
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
    state_keys = {"schema", "active", "createdAt", "updatedAt", "projectFingerprint", "sessionBinding", "activationId"}
    receipt_keys = {"schema", "event", "lastHookAt", "projectFingerprint", "sessionBinding", "activationId"}
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
        and created_ms <= updated_ms == receipt_ms <= now_ms + MAX_BACKWARD_CLOCK_SKEW_MS
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
                or parsed > now_ms + MAX_BACKWARD_CLOCK_SKEW_MS
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


def _monotonic_now_ms(current: dict[str, Any] | None, now_ms: int) -> int:
    if not current:
        return now_ms
    prev_ms = timestamp_ms(current.get("updatedAt"))
    if prev_ms is not None and prev_ms > now_ms:
        return int(prev_ms)
    return now_ms


def persist(targets: dict[str, Path], state: dict[str, Any], receipt: dict[str, Any]) -> None:
    atomic_write(targets["state"], state)
    atomic_write(targets["receipt"], receipt)


def _refresh_state(
    targets: dict[str, Path],
    fingerprint: str,
    binding: str,
    activation_id: str,
    effective_ms: int,
    event: str,
    created_at: str | None,
) -> None:
    persist(
        targets,
        state_value(fingerprint, binding, activation_id, effective_ms, created_at),
        receipt_value(fingerprint, binding, activation_id, event, effective_ms),
    )


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
            _refresh_state(targets, fingerprint, binding, str(current["activationId"]), _monotonic_now_ms(current, now_ms), event, str(current.get("createdAt")))
        return None
    if event == "SessionStart":
        if payload.get("source") not in {"resume", "compact"}:
            return None
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        if not current:
            return None
        _refresh_state(targets, fingerprint, binding, str(current["activationId"]), _monotonic_now_ms(current, now_ms), event, str(current.get("createdAt")))
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
        _refresh_state(targets, fingerprint, binding, secrets.token_hex(32), _monotonic_now_ms(current, now_ms), event, None if not current else str(current.get("createdAt")))
        return context_output(
            event,
            "Patpat sticky receipt: trusted session hook persisted /patpat. "
            "The skill supplies activation-turn behavior. After proof, keep local reversible work light without delivery intent; default commit-and-PR only when delivery intent exists. "
            "A higher-priority repository rule or opt-out still blocks delivery. Merge requires explicit land or merge language.",
        )
    current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
    if not current:
        return None
    _refresh_state(targets, fingerprint, binding, str(current["activationId"]), _monotonic_now_ms(current, now_ms), event, str(current.get("createdAt")))
    return context_output(event, STICKY_CONTEXT)


def run_self_test() -> None:
    test_suite = Path(__file__).resolve().parents[2] / "tests" / "test_patpat_loop_state.py"
    if test_suite.is_file():
        import importlib.util

        spec = importlib.util.spec_from_file_location("test_patpat_loop_state", test_suite)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {test_suite}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.run_self_test(sys.modules.get(__name__))
        return

    # Standalone smoke check when staged without tests/
    assert classify_prompt("/patpat fix bug") == "activate"
    assert classify_prompt("/patpat off") == "disable"
    assert classify_prompt("Explain /patpat") == "inactive"
    assert len(STICKY_CONTEXT) <= 1200
    with tempfile.TemporaryDirectory(prefix="patpat-hook-smoke-") as directory:
        base = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "s1",
            "cwd": str(Path(directory) / "proj"),
        }
        assert "sticky receipt" in json.dumps(handle_hook({**base, "prompt": "/patpat run"}, plugin_data=directory, now_ms=1000))
        assert "Patpat Loop is active" in json.dumps(handle_hook({**base, "prompt": "next"}, plugin_data=directory, now_ms=2000))
        assert handle_hook({**base, "prompt": "/patpat off"}, plugin_data=directory, now_ms=3000) is None
    print("Patpat loop sticky-hook smoke self-test passed.")


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
