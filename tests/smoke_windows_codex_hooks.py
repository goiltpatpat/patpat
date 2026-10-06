#!/usr/bin/env python3
"""Exercise the Codex plugin hook launcher through native Windows cmd.exe."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


class SmokeError(RuntimeError):
    pass


def main() -> int:
    if os.name != "nt":
        raise SmokeError("this smoke test must run on native Windows")

    source = Path(__file__).resolve().parents[1]
    source_manifest = source / "hooks" / "hooks.json"
    root_mirror = source / "hooks.json"
    if source_manifest.read_bytes() != root_mirror.read_bytes():
        raise SmokeError("root and plugin hook manifests differ")
    manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    windows_commands: list[str] = []
    for event in ("SessionStart", "UserPromptSubmit", "SessionEnd"):
        groups = manifest.get("hooks", {}).get(event)
        if not isinstance(groups, list) or not groups:
            raise SmokeError(f"manifest has no {event} hook groups")
        for group in groups:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list) or not entries:
                raise SmokeError(f"manifest has no {event} commands")
            for entry in entries:
                command = entry.get("commandWindows") if isinstance(entry, dict) else None
                if not isinstance(command, str) or not command:
                    raise SmokeError(f"manifest has no Windows command for {event}")
                windows_commands.append(command)
    if len(set(windows_commands)) != 1:
        raise SmokeError("Codex hook events must share one Windows launcher")

    comspec = os.environ.get("COMSPEC")
    if not comspec or not Path(comspec).is_file():
        raise SmokeError("COMSPEC is unavailable")

    with tempfile.TemporaryDirectory(prefix="Patpat Test User โปรเจกต์ ") as temporary:
        base = Path(temporary)
        plugin_root = base / "Nested Plugin Cache" / "Patpat 0.7.0"
        hooks = plugin_root / "hooks"
        hook_scripts = hooks / "scripts"
        hook_scripts.mkdir(parents=True)
        shutil.copy2(source_manifest, hooks / "hooks.json")
        shutil.copy2(source / "hooks" / "scripts" / "patpat_loop_state.py", hook_scripts)
        staged_script = hook_scripts / "patpat_loop_state.py"
        shutil.copy2(source / "hooks" / "scripts" / "patpat_loop_state.cmd", hook_scripts)
        project = base / "Test User" / "My Project" / "โปรเจกต์ Patpat"
        project.mkdir(parents=True)
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        system32 = system_root / "System32"
        whoami = system32 / "whoami.exe"
        if not whoami.is_file():
            raise SmokeError(r"System32\whoami.exe is required for the cwd-shadowing regression test")
        for executable_name in ("where.exe", "py.exe", "python.exe"):
            shutil.copy2(whoami, project / executable_name)
        plugin_data = base / "User Data Ω" / "Patpat"
        command = windows_commands[0].replace("${PLUGIN_ROOT}", str(plugin_root))
        if "${PLUGIN_ROOT}" in command or not command.startswith('"') or not command.endswith('"'):
            raise SmokeError("PLUGIN_ROOT did not resolve to one quoted launcher path")

        environment = os.environ.copy()
        for key in (
            "PLUGIN_ROOT",
            "PLUGIN_DATA",
            "GROK_PLUGIN_ROOT",
            "GROK_PLUGIN_DATA",
            "CLAUDE_PLUGIN_ROOT",
            "CLAUDE_PLUGIN_DATA",
        ):
            environment.pop(key, None)
        environment.update({"PLUGIN_ROOT": str(plugin_root), "PLUGIN_DATA": str(plugin_data)})
        invocation_seconds: list[float] = []

        def payload(
            event: str,
            session: str,
            *,
            cwd: Path = project,
            prompt: str | None = None,
            source_name: str | None = None,
        ) -> dict[str, Any]:
            value: dict[str, Any] = {"hook_event_name": event, "session_id": session, "cwd": str(cwd)}
            if prompt is not None:
                value["prompt"] = prompt
            if source_name is not None:
                value["source"] = source_name
            return value

        def invoke(
            request: dict[str, Any] | None,
            *,
            env: dict[str, str] | None = None,
            raw_input: bytes | None = None,
        ) -> subprocess.CompletedProcess[bytes]:
            if request is None and raw_input is None:
                raise SmokeError("hook invocation needs JSON or raw stdin")
            input_bytes = raw_input
            if input_bytes is None:
                input_bytes = json.dumps(request, ensure_ascii=False).encode("utf-8")
            # Codex wraps the selected command when invoking COMSPEC /C on Windows.
            command_line = f'"{comspec}" /C "{command}"'
            started = time.perf_counter()
            result = subprocess.run(
                command_line,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=project,
                env=environment if env is None else env,
                timeout=5,
                check=False,
            )
            invocation_seconds.append(time.perf_counter() - started)
            return result

        def successful(request: dict[str, Any]) -> subprocess.CompletedProcess[bytes]:
            result = invoke(request)
            if result.returncode != 0:
                raise SmokeError(
                    f"Windows hook exited {result.returncode}: "
                    f"{result.stderr.decode('utf-8', errors='replace')}"
                )
            return result

        def output(result: subprocess.CompletedProcess[bytes]) -> str:
            return result.stdout.decode("utf-8", errors="replace")

        for request in (
            payload("SessionStart", "normal-start", source_name="startup"),
            payload("SessionStart", "missing-resume", source_name="resume"),
            payload("UserPromptSubmit", "inactive", prompt="run the tests"),
            payload("SessionEnd", "inactive-end"),
        ):
            if successful(request).stdout.strip():
                raise SmokeError("healthy no-op emitted output")

        session = "sticky-session"
        shadowed = successful(
            payload("UserPromptSubmit", "cwd-shadow", prompt="/patpat verify trusted runtime lookup")
        )
        if "sticky receipt" not in output(shadowed):
            raise SmokeError("workspace executable shadowing interfered with trusted hook runtime lookup")
        shadow_binding = hashlib.sha256(b"cwd-shadow").hexdigest()
        (plugin_data / "patpat-loop" / "sessions" / f"{shadow_binding}.json").unlink()
        (plugin_data / "patpat-loop" / "receipts" / f"{shadow_binding}.json").unlink()

        py_launcher = shutil.which("py.exe", path=environment.get("PATH"))
        if py_launcher:
            py_environment = environment.copy()
            py_environment["PATH"] = os.pathsep.join((str(Path(py_launcher).resolve().parent), str(system32)))
            py_result = invoke(
                payload("UserPromptSubmit", "python-launcher", prompt="/patpat verify py launcher"),
                env=py_environment,
            )
            if py_result.returncode != 0 or "sticky receipt" not in output(py_result):
                raise SmokeError("py.exe -3 did not run the Windows hook")
            py_binding = hashlib.sha256(b"python-launcher").hexdigest()
            (plugin_data / "patpat-loop" / "sessions" / f"{py_binding}.json").unlink()
            (plugin_data / "patpat-loop" / "receipts" / f"{py_binding}.json").unlink()

        activation = successful(payload("UserPromptSubmit", session, prompt="/patpat verify Windows hooks"))
        if "sticky receipt" not in output(activation):
            raise SmokeError("activation context was not emitted")
        binding = hashlib.sha256(session.encode("utf-8")).hexdigest()
        state = plugin_data / "patpat-loop" / "sessions" / f"{binding}.json"
        receipt = plugin_data / "patpat-loop" / "receipts" / f"{binding}.json"
        if not state.is_file() or not receipt.is_file():
            raise SmokeError("activation did not create state and receipt")

        continuation = successful(payload("UserPromptSubmit", session, prompt="run the relevant tests"))
        if "Patpat Loop is active" not in output(continuation):
            raise SmokeError("sticky context was not emitted on the next turn")
        repeated = successful(payload("UserPromptSubmit", session, prompt="/patpat verify again"))
        if "sticky receipt" not in output(repeated) or len(list(plugin_data.rglob("*.json"))) != 2:
            raise SmokeError("repeated activation did not remain safe")
        for source_name in ("resume", "compact"):
            resumed = successful(payload("SessionStart", session, source_name=source_name))
            if "Patpat Loop is active" not in output(resumed):
                raise SmokeError(f"SessionStart {source_name} did not restore context")
        ended = successful(payload("SessionEnd", session))
        if ended.stdout.strip() or not state.is_file() or not receipt.is_file():
            raise SmokeError("SessionEnd did not finish cleanly with resumable state")
        session_end_seconds = invocation_seconds[-1]
        if session_end_seconds >= 1.0:
            raise SmokeError(f"SessionEnd launcher exceeded its 1-second budget: {session_end_seconds:.3f}s")

        isolated_session = successful(payload("UserPromptSubmit", "different-session", prompt="continue"))
        if isolated_session.stdout.strip():
            raise SmokeError("state leaked to a different session")
        if "Patpat Loop is active" not in output(successful(payload("UserPromptSubmit", session, prompt="continue"))):
            raise SmokeError("different session damaged the active session")

        project_session = "project-bound-session"
        successful(payload("UserPromptSubmit", project_session, prompt="/patpat check project scope"))
        other_project = base / "Other Project"
        other_project.mkdir()
        project_isolation = successful(
            payload("UserPromptSubmit", project_session, cwd=other_project, prompt="continue")
        )
        if project_isolation.stdout.strip():
            raise SmokeError("state leaked to a different project")

        corrupt_session = "corrupt-session"
        successful(payload("UserPromptSubmit", corrupt_session, prompt="/patpat check corrupt state"))
        corrupt_binding = hashlib.sha256(corrupt_session.encode("utf-8")).hexdigest()
        corrupt_state = plugin_data / "patpat-loop" / "sessions" / f"{corrupt_binding}.json"
        corrupt_receipt = plugin_data / "patpat-loop" / "receipts" / f"{corrupt_binding}.json"
        corrupt_state.write_bytes(b"not-json\n")
        corrupt = successful(payload("UserPromptSubmit", corrupt_session, prompt="continue"))
        if corrupt.stdout.strip() or corrupt_state.exists() or corrupt_receipt.exists():
            raise SmokeError("corrupt state was trusted or left behind")

        disabled = successful(payload("UserPromptSubmit", session, prompt="disable /patpat"))
        if disabled.stdout.strip() or state.exists() or receipt.exists():
            raise SmokeError("disable did not clear state and receipt")

        missing_root_environment = environment.copy()
        missing_root_environment.pop("PLUGIN_ROOT", None)
        missing_root = invoke(payload("UserPromptSubmit", "missing-root", prompt="/patpat"), env=missing_root_environment)
        if missing_root.returncode != 2 or b"PLUGIN_ROOT is missing" not in missing_root.stderr:
            raise SmokeError("missing PLUGIN_ROOT was not diagnosed")

        missing_data_environment = environment.copy()
        missing_data_environment.pop("PLUGIN_DATA", None)
        missing_data = invoke(payload("UserPromptSubmit", "missing-data", prompt="/patpat"), env=missing_data_environment)
        if missing_data.returncode != 2 or b"PLUGIN_DATA is missing" not in missing_data.stderr:
            raise SmokeError("missing PLUGIN_DATA was not diagnosed")

        missing_runtime_environment = environment.copy()
        missing_runtime_environment["PATH"] = str(system_root / "System32")
        missing_runtime = invoke(
            payload("UserPromptSubmit", "missing-runtime", prompt="/patpat"),
            env=missing_runtime_environment,
        )
        if missing_runtime.returncode != 127 or b"no supported Python 3.11+ runtime" not in missing_runtime.stderr:
            raise SmokeError("missing Python runtime was not diagnosed")

        system32 = str(system32)
        python_directory = str(Path(sys.executable).resolve().parent)
        fallback_environment = environment.copy()
        fallback_environment["PATH"] = os.pathsep.join((python_directory, system32))
        if shutil.which("py.exe", path=fallback_environment["PATH"]):
            raise SmokeError("could not isolate python.exe fallback from py.exe")
        if not shutil.which("python.exe", path=fallback_environment["PATH"]):
            raise SmokeError("native Python executable is absent from the fallback PATH")
        fallback = invoke(
            payload("UserPromptSubmit", "python-fallback", prompt="/patpat verify python fallback"),
            env=fallback_environment,
        )
        if fallback.returncode != 0 or "sticky receipt" not in output(fallback):
            raise SmokeError("python.exe fallback did not run the hook")

        malformed = invoke(None, raw_input=b"not-json\n")
        if malformed.returncode == 0 or b"JSON object" not in malformed.stderr:
            raise SmokeError("malformed hook input was hidden as success")

        staged_script.write_text("raise SystemExit(37)\n", encoding="utf-8", newline="\n")
        propagated = invoke(payload("UserPromptSubmit", "exit-code", prompt="continue"))
        if propagated.returncode != 37:
            raise SmokeError(f"launcher did not preserve child exit code: {propagated.returncode}")

    print(f"Native Windows Codex hook smoke test passed (SessionEnd {session_end_seconds:.3f}s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Windows Codex hook smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1)
