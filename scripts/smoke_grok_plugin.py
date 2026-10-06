#!/usr/bin/env python3
"""Smoke-test Patpat installation and hook execution in an isolated Grok home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from stage_plugin import stage
from validate import validate_root


class SmokeError(RuntimeError):
    """Raised when the isolated Grok installation contract fails."""


def run(
    command: list[str],
    environment: dict[str, str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
        input=input_text,
        timeout=30,
    )
    if result.returncode != 0:
        raise SmokeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def run_json(command: list[str], environment: dict[str, str], *, cwd: Path | None = None) -> Any:
    result = run(command, environment, cwd=cwd)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SmokeError(f"command returned invalid JSON: {' '.join(command)}") from error


def plugin_entries(listing: Any) -> list[dict[str, Any]]:
    if isinstance(listing, list):
        entries = listing
    elif isinstance(listing, dict) and isinstance(listing.get("plugins"), list):
        entries = listing["plugins"]
    else:
        raise SmokeError("Grok plugin list returned an unsupported shape")
    if not all(isinstance(item, dict) for item in entries):
        raise SmokeError("Grok plugin list contains a malformed entry")
    return entries


def installed_plugin(listing: Any) -> dict[str, Any]:
    entries = plugin_entries(listing)
    for item in entries:
        if item.get("name") == "patpat":
            return item
    raise SmokeError("installed Patpat plugin was absent from Grok plugin list")


def hook_command(plugin_root: Path) -> str:
    try:
        manifest = json.loads((plugin_root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        command = manifest["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise SmokeError("installed Grok hook manifest is not executable") from error
    if not isinstance(command, str) or not command:
        raise SmokeError("installed Grok hook command is empty")
    return command


def invoke_hook(
    command: str,
    environment: dict[str, str],
    payload: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", "-c", command],
        capture_output=True,
        text=True,
        env=environment,
        input=json.dumps(payload),
        timeout=30,
        check=False,
    )


def execute_hook(command: str, environment: dict[str, str], payload: dict[str, Any]) -> str:
    result = invoke_hook(command, environment, payload)
    if result.returncode != 0:
        raise SmokeError(
            f"hook failed ({result.returncode})\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def cursor_hook_command(plugin_root: Path) -> str:
    try:
        manifest = json.loads((plugin_root / "hooks" / "cursor.json").read_text(encoding="utf-8"))
        command = manifest["hooks"]["beforeSubmitPrompt"][0]["command"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
        raise SmokeError("Cursor hook manifest is not executable") from error
    if not isinstance(command, str) or not command:
        raise SmokeError("Cursor hook command is empty")
    return command


def smoke_manifest_commands(source: Path) -> None:
    payload = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "manifest-command-smoke",
        "cwd": str(source),
        "prompt": "/patpat verify this change",
    }
    codex_manifest = json.loads((source / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    codex_command = codex_manifest["hooks"]["UserPromptSubmit"][0]["hooks"][0]["command"]
    commands = (
        ("codex", codex_command, "PLUGIN_ROOT", "PLUGIN_DATA"),
        ("grok", hook_command(source), "GROK_PLUGIN_ROOT", "GROK_PLUGIN_DATA"),
        ("cursor", cursor_hook_command(source), "CURSOR_PLUGIN_ROOT", "PLUGIN_DATA"),
    )
    with tempfile.TemporaryDirectory(prefix="patpat-hook-command-smoke-") as directory:
        root = Path(directory)
        for host, command, root_key, data_key in commands:
            data = root / host
            environment = os.environ.copy()
            for key in (
                "PLUGIN_ROOT",
                "PLUGIN_DATA",
                "GROK_PLUGIN_ROOT",
                "GROK_PLUGIN_DATA",
                "CLAUDE_PLUGIN_ROOT",
                "CLAUDE_PLUGIN_DATA",
                "CURSOR_PLUGIN_ROOT",
            ):
                environment.pop(key, None)
            environment.update({root_key: str(source), data_key: str(data)})
            activated = execute_hook(command, environment, {**payload, "session_id": f"{host}-session"})
            if "sticky receipt" not in activated:
                raise SmokeError(f"{host} manifest command did not activate Patpat")
            session_id = f"{host}-session"
            if host in {"codex", "grok"}:
                startup = execute_hook(
                    command,
                    environment,
                    {
                        "hook_event_name": "SessionStart",
                        "session_id": session_id,
                        "cwd": str(source),
                        "source": "startup",
                    },
                )
                missing_resume = execute_hook(
                    command,
                    environment,
                    {
                        "hook_event_name": "SessionStart",
                        "session_id": f"{host}-missing-resume",
                        "cwd": str(source),
                        "source": "resume",
                    },
                )
                if startup or missing_resume:
                    raise SmokeError(f"{host} healthy SessionStart no-op emitted context")
                for source_name in ("resume", "compact"):
                    resumed = execute_hook(
                        command,
                        environment,
                        {
                            "hook_event_name": "SessionStart",
                            "session_id": session_id,
                            "cwd": str(source),
                            "source": source_name,
                        },
                    )
                    if "Patpat Loop is active" not in resumed:
                        raise SmokeError(f"{host} SessionStart {source_name} did not restore context")
                ended = execute_hook(
                    command,
                    environment,
                    {
                        "hook_event_name": "SessionEnd",
                        "session_id": session_id,
                        "cwd": str(source),
                    },
                )
                if ended:
                    raise SmokeError(f"{host} SessionEnd unexpectedly emitted output")
            execute_hook(
                command,
                environment,
                {**payload, "session_id": session_id, "prompt": "disable /patpat"},
            )
            if list(data.rglob("*.json")):
                raise SmokeError(f"{host} manifest command left state after disable")
            if host in {"codex", "grok"}:
                missing_data_environment = environment.copy()
                missing_data_environment.pop(data_key, None)
                missing_data = invoke_hook(command, missing_data_environment, payload)
                if missing_data.returncode != 2 or "PLUGIN_DATA is missing" not in missing_data.stderr:
                    raise SmokeError(f"{host} hook did not diagnose missing plugin data")

                missing_root_environment = environment.copy()
                missing_root_environment.pop(root_key, None)
                missing_root = invoke_hook(command, missing_root_environment, payload)
                if missing_root.returncode != 2 or "PLUGIN_ROOT is missing" not in missing_root.stderr:
                    raise SmokeError(f"{host} hook did not diagnose missing plugin root")


def main() -> int:
    source = Path(__file__).resolve().parents[1]
    if "--commands-only" in sys.argv:
        smoke_manifest_commands(source)
        print("Patpat hook manifest command smoke test passed.")
        return 0

    grok = shutil.which("grok")
    if not grok:
        print("Grok smoke test skipped: grok CLI is unavailable.", file=sys.stderr)
        return 2

    source_errors = validate_root(source)
    if source_errors:
        raise SmokeError(f"source validation failed: {'; '.join(source_errors)}")

    with tempfile.TemporaryDirectory(prefix="patpat-grok-smoke-") as directory:
        root = Path(directory)
        isolated_home = root / "home"
        isolated_home.mkdir()
        staged_source = root / "patpat-dist"
        stage(source, staged_source)

        environment = os.environ.copy()
        environment["HOME"] = str(isolated_home)
        run([grok, "plugin", "install", str(staged_source), "--trust"], environment)
        run([grok, "plugin", "update", "patpat"], environment)

        plugin = installed_plugin(run_json([grok, "plugin", "list", "--json"], environment))
        raw_path = plugin.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            raise SmokeError("Grok did not report the installed plugin path")
        installed_path = Path(raw_path)
        try:
            installed_path.resolve().relative_to(isolated_home.resolve())
        except ValueError as error:
            raise SmokeError("Grok installed Patpat outside the isolated home") from error
        installed_errors = validate_root(installed_path)
        if installed_errors:
            raise SmokeError(f"installed artifact validation failed: {'; '.join(installed_errors)}")

        inspection = run_json([grok, "inspect", "--json"], environment, cwd=root)
        if not isinstance(inspection, dict) or not inspection.get("hooks"):
            raise SmokeError("Grok did not discover the installed Patpat hooks")

        command = hook_command(installed_path)
        plugin_data = root / "plugin-data"
        hook_environment = environment.copy()
        for key in ("PLUGIN_ROOT", "PLUGIN_DATA", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA"):
            hook_environment.pop(key, None)
        hook_environment.update(
            {
                "GROK_PLUGIN_ROOT": str(installed_path),
                "GROK_PLUGIN_DATA": str(plugin_data),
            }
        )
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "grok-smoke-session",
            "cwd": str(root / "project"),
            "prompt": "/patpat verify this change",
        }
        activated = execute_hook(command, hook_environment, payload)
        if "sticky receipt" not in activated:
            raise SmokeError("Grok native hook environment did not activate Patpat Loop")
        if len(list(plugin_data.rglob("*.json"))) != 2:
            raise SmokeError("activation did not persist both state and receipt")

        continued = execute_hook(command, hook_environment, {**payload, "prompt": "continue"})
        if "Patpat Loop is active" not in continued:
            raise SmokeError("subsequent Grok turn did not retain Patpat Loop")

        for source_name in ("resume", "compact"):
            resumed = execute_hook(
                command,
                hook_environment,
                {
                    "hook_event_name": "SessionStart",
                    "session_id": payload["session_id"],
                    "cwd": payload["cwd"],
                    "source": source_name,
                },
            )
            if "Patpat Loop is active" not in resumed:
                raise SmokeError(f"Grok SessionStart {source_name} did not restore Patpat Loop")
        ended = execute_hook(
            command,
            hook_environment,
            {
                "hook_event_name": "SessionEnd",
                "session_id": payload["session_id"],
                "cwd": payload["cwd"],
            },
        )
        if ended or len(list(plugin_data.rglob("*.json"))) != 2:
            raise SmokeError("Grok SessionEnd failed or cleared resumable state")

        disabled = execute_hook(command, hook_environment, {**payload, "prompt": "disable /patpat"})
        if disabled:
            raise SmokeError("disable unexpectedly emitted sticky context")
        if list(plugin_data.rglob("*.json")):
            raise SmokeError("disable left Patpat Loop state or receipt behind")

        compatibility_data = root / "compatibility-data"
        compatibility_environment = environment.copy()
        for key in ("PLUGIN_ROOT", "PLUGIN_DATA", "GROK_PLUGIN_ROOT", "GROK_PLUGIN_DATA"):
            compatibility_environment.pop(key, None)
        compatibility_environment.update(
            {
                "CLAUDE_PLUGIN_ROOT": str(installed_path),
                "CLAUDE_PLUGIN_DATA": str(compatibility_data),
            }
        )
        compatible = execute_hook(command, compatibility_environment, payload)
        if "sticky receipt" not in compatible or len(list(compatibility_data.rglob("*.json"))) != 2:
            raise SmokeError("Grok compatibility hook environment did not activate Patpat Loop")
        execute_hook(command, compatibility_environment, {**payload, "prompt": "disable /patpat"})

        fail_closed_environment = hook_environment.copy()
        fail_closed_environment.pop("GROK_PLUGIN_DATA", None)
        fail_closed = invoke_hook(command, fail_closed_environment, payload)
        if fail_closed.returncode != 2 or "PLUGIN_DATA is missing" not in fail_closed.stderr:
            raise SmokeError("missing plugin data was not diagnosed")
        if list(plugin_data.rglob("*.json")):
            raise SmokeError("missing plugin data execution persisted state")

        rootless_environment = fail_closed_environment.copy()
        rootless_environment.pop("GROK_PLUGIN_ROOT", None)
        rootless = invoke_hook(command, rootless_environment, payload)
        if rootless.returncode != 2 or "PLUGIN_ROOT is missing" not in rootless.stderr:
            raise SmokeError("missing plugin root was not diagnosed")

        run([grok, "plugin", "uninstall", "patpat"], environment)
        remaining = plugin_entries(run_json([grok, "plugin", "list", "--json"], environment))
        if any(item.get("name") == "patpat" for item in remaining):
            raise SmokeError("Grok uninstall left a plugin registry entry")

    print("Patpat Grok plugin and hook smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, subprocess.TimeoutExpired) as error:
        print(f"Patpat Grok smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1)
