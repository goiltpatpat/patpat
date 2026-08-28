#!/usr/bin/env python3
"""Persist Patpat Loop across later turns when the host trusts plugin hooks."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

STATE_SCHEMA = 1
DEFAULT_TTL_MS = 30 * 24 * 60 * 60 * 1000
MAX_SESSION_ID_LENGTH = 512
ACTIVATION = re.compile(
    r"(?:^|\s)(?:/|\$)patpat(?:-loop)?(?=$|\s)|(?:^|\s)use patpat(?:-loop)?(?=$|\s)",
    re.IGNORECASE,
)
DISABLE = re.compile(
    r"^\s*(?:disable\s+(?:/|\$)?patpat(?:-loop)?|opt\s+out(?:\s+of)?\s+patpat(?:-loop)?)\s*[.!?]?\s*$",
    re.IGNORECASE,
)
STICKY_CONTEXT = (
    "Patpat Loop is active for this session. Apply /patpat (`patpat-loop`) for this turn. "
    "Follow the operating protocol. Explicit activation authorizes commit-and-PR after proof unless "
    "a higher-priority repository rule or opt-out blocks it. Merge only on explicit land or merge language. "
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
    if ACTIVATION.search(prompt):
        return "activate"
    return "inactive"


def state_paths(plugin_data: object, session_id: object) -> dict[str, Path] | None:
    key = session_key(session_id)
    if not key or not isinstance(plugin_data, str) or not plugin_data:
        return None
    root = Path(plugin_data) / "patpat-loop"
    return {
        "root": root,
        "state": root / "sessions" / f"{key}.json",
        "receipt": root / "receipts" / f"{key}.json",
    }


def atomic_write(target: Path, value: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
            handle.write("\n")
        os.replace(path, target)
        os.chmod(target, 0o600)
    except Exception:
        if path.exists():
            path.unlink()
        raise


def read_json(target: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError):
        target.unlink(missing_ok=True)
        return None
    return value if isinstance(value, dict) else None


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


def state_value(fingerprint: str, now_ms: int, created_at: str | None) -> dict[str, Any]:
    timestamp = now_iso(now_ms)
    return {
        "schema": STATE_SCHEMA,
        "active": True,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        "projectFingerprint": fingerprint,
    }


def receipt_value(fingerprint: str, event: str, now_ms: int) -> dict[str, Any]:
    return {
        "schema": STATE_SCHEMA,
        "event": event,
        "lastHookAt": now_iso(now_ms),
        "projectFingerprint": fingerprint,
    }


def collect_expired(plugin_data: str, now_ms: int, ttl_ms: int) -> None:
    root = Path(plugin_data) / "patpat-loop"
    for folder in ("sessions", "receipts"):
        directory = root / folder
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            value = read_json(path)
            stamp = str((value or {}).get("updatedAt") or (value or {}).get("lastHookAt") or "")
            try:
                from datetime import datetime

                parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000
            except ValueError:
                path.unlink(missing_ok=True)
                continue
            if not value or value.get("schema") != STATE_SCHEMA or now_ms - parsed > ttl_ms:
                path.unlink(missing_ok=True)


def read_active_state(
    plugin_data: str,
    session_id: object,
    cwd: object,
    now_ms: int,
    ttl_ms: int,
) -> dict[str, Any] | None:
    targets = state_paths(plugin_data, session_id)
    fingerprint = project_fingerprint(cwd)
    if not targets or not fingerprint:
        return None
    state = read_json(targets["state"])
    if not state:
        return None
    stamp = str(state.get("updatedAt") or "")
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() * 1000
    except ValueError:
        targets["state"].unlink(missing_ok=True)
        return None
    if (
        state.get("schema") != STATE_SCHEMA
        or state.get("active") is not True
        or state.get("projectFingerprint") != fingerprint
        or now_ms - parsed > ttl_ms
    ):
        if state.get("schema") != STATE_SCHEMA or now_ms - parsed > ttl_ms:
            targets["state"].unlink(missing_ok=True)
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
    if not targets or not fingerprint:
        return None
    event = normalize_event(payload)
    ttl_ms = DEFAULT_TTL_MS
    if event == "SessionEnd":
        collect_expired(plugin_data, now_ms, ttl_ms)
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        if current:
            persist(
                targets,
                state_value(fingerprint, now_ms, str(current.get("createdAt"))),
                receipt_value(fingerprint, event, now_ms),
            )
        return None
    if event == "SessionStart":
        source = payload.get("source")
        if source not in {"resume", "compact"}:
            return None
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        if not current:
            return None
        persist(
            targets,
            state_value(fingerprint, now_ms, str(current.get("createdAt"))),
            receipt_value(fingerprint, event, now_ms),
        )
        return context_output(event, STICKY_CONTEXT)
    if event != "UserPromptSubmit":
        return None
    action = classify_prompt(extract_prompt(payload))
    if action == "disable":
        targets["state"].unlink(missing_ok=True)
        targets["receipt"].unlink(missing_ok=True)
        return None
    if action == "activate":
        collect_expired(plugin_data, now_ms, ttl_ms)
        current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
        persist(
            targets,
            state_value(fingerprint, now_ms, None if not current else str(current.get("createdAt"))),
            receipt_value(fingerprint, event, now_ms),
        )
        return context_output(
            event,
            "Patpat sticky receipt: trusted session hook persisted /patpat. "
            "The skill supplies activation-turn behavior. After proof, default to commit-and-PR unless "
            "a higher-priority repository rule or opt-out blocks it. Merge requires explicit land or merge language.",
        )
    current = read_active_state(plugin_data, session_id, cwd, now_ms, ttl_ms)
    if not current:
        return None
    persist(
        targets,
        state_value(fingerprint, now_ms, str(current.get("createdAt"))),
        receipt_value(fingerprint, event, now_ms),
    )
    return context_output(event, STICKY_CONTEXT)


def run_self_test() -> None:
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
        if classify_prompt("use $patpat-setup on this host") != "inactive":
            raise AssertionError("patpat-setup must not activate sticky mode")
        if classify_prompt("$patpat-loop fix this") != "activate":
            raise AssertionError("Codex $patpat-loop should activate")
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
    print("Patpat loop sticky-hook self-test passed.")


def main() -> int:
    if "--self-test" in sys.argv:
        run_self_test()
        return 0
    raw = sys.stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0
    output = handle_hook(payload)
    if output:
        json.dump(output, sys.stdout)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        raise SystemExit(main())
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(0)
