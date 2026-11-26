#!/usr/bin/env python3
"""Tests for hooks/scripts/patpat_loop_state.py sticky session state and security invariants."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any

HOOK_PATH = Path(__file__).resolve().parents[1] / "hooks" / "scripts" / "patpat_loop_state.py"


def load_hook_module():
    spec = importlib.util.spec_from_file_location("patpat_loop_state", HOOK_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"missing hook script: {HOOK_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_self_test(hook: Any | None = None) -> None:
    m = hook if hook is not None else load_hook_module()

    affirmative = (
        "/patpat",
        "/patpat-loop fix this",
        "$patpat verify this",
        "$patpat-loop land this",
        "/patpat:patpat fix this",
        "/patpat:patpat-loop verify this",
        "Use patpat to inspect this repository",
        "Use /patpat:patpat to inspect this repository",
        "use /patpat-loop for this engineering task",
        "Hey, /patpat fix the auth bug",
        "Hi /patpat fix this",
        "Hello, $patpat verify the build",
        "Please /patpat fix the auth bug",
        "Please use patpat to debug X",
        "Hey, please use patpat to fix the auth bug",
        "Can you use patpat to inspect this repo?",
        "Could you please use /patpat-loop for this refactor?",
        "Ok, /patpat-loop ship this",
        "/patpat without editing, explain how auth works",
        # Universal language-agnostic explicit invocations
        "/patpat จัดตั้งทีมทำงานและแก้บั๊กนี้",
        "/patpat-loop ตรวจสอบโค้ดนี้",
        "/patpat 認証バグを修正して",
        "/patpat 修复超时问题",
        "$patpat 로그인 버그 수정",
    )
    for prompt in affirmative:
        if m.classify_prompt(prompt) != "activate":
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
        "/patpat:patpat-setup on this host",
        "/patpat:patpat-inspect how does routing work",
        "do not use patpat to modify this repository",
        "don't use patpat",
        "don't use patpat to fix this",
        "Please don't use patpat to modify this",
        "Hey, don't use /patpat here",
        "Hey, explain what /patpat does",
        "Explain how to disable /patpat",
        "Don't turn off patpat",
        '"disable /patpat"',
        "Leave patpat active",
        "Leave patpat on for this session",
        "Stop patpat from pushing to main",
        # Quoted/explanatory mentions in non-English text stay inactive
        "อธิบายว่า /patpat ทำงานยังไง",
        "อย่าใช้ /patpat แก้ไฟล์นี้",
    )
    for prompt in inactive:
        if m.classify_prompt(prompt) != "inactive":
            raise AssertionError(f"non-affirmative prompt activated Patpat: {prompt!r}")

    disable_prompts = (
        # Universal language-agnostic subcommands
        "/patpat off",
        "/patpat stop",
        "/patpat disable",
        "/patpat deactivate",
        "/patpat exit",
        "$patpat off",
        "/patpat-loop off",
        "/patpat:patpat off",
        "/patpat off สำหรับคำถามนี้",
        "/patpat stop ありがとう",
        "Hey, /patpat off",
        # Canonical English explicit opt-out
        "disable /patpat",
        "disable /patpat:patpat",
        "stop using patpat",
        "stop patpat",
        "turn off patpat",
        "exit patpat",
        "disable /patpat for this question",
        "Please turn off patpat for now.",
        "Hey, stop using /patpat-loop and just explain X",
        "Can you exit patpat?",
        "opt out of patpat for now",
    )
    for prompt in disable_prompts:
        if m.classify_prompt(prompt) != "disable":
            raise AssertionError(f"disable command was not recognized: {prompt!r}")

    with tempfile.TemporaryDirectory(prefix="patpat-hook-") as directory:
        plugin_data = str(Path(directory) / "plugin-data")
        payload = {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "session-1",
            "cwd": str(Path(directory) / "project"),
            "prompt": "/patpat reproduce this flake, then land the PR",
        }
        activated = m.handle_hook(payload, plugin_data=plugin_data, now_ms=1_000)
        if not activated or "sticky receipt" not in json.dumps(activated):
            raise AssertionError("activation did not persist a sticky receipt")
        targets = m.state_paths(plugin_data, payload["session_id"])
        if not targets:
            raise AssertionError("test session did not resolve state paths")
        state = m.read_json(targets["state"])
        receipt = m.read_json(targets["receipt"])
        if not state or not receipt or state.get("schema") != m.STATE_SCHEMA:
            raise AssertionError("activation did not persist schema-v2 state and receipt")
        if os.name != "nt" and stat.S_IMODE(targets["state"].stat().st_mode) != 0o600:
            raise AssertionError("state file mode is not restricted before publication")
        if state.get("activationId") != receipt.get("activationId"):
            raise AssertionError("activation receipt is not bound to state")
        continued = m.handle_hook(
            {**payload, "prompt": "continue with the failing test"},
            plugin_data=plugin_data,
            now_ms=2_000,
        )
        if not continued or "Patpat Loop is active" not in json.dumps(continued):
            raise AssertionError("later turn did not keep sticky mode")
        required_sticky_context = (
            "Use the Patpat Loop skill for this turn",
            "follow the operating protocol",
            "Activation authorizes the loop, proof, and verification",
            "default commit/PR needs delivery intent",
            "Higher-priority repository rules or opt-out block delivery",
            'Merge requires explicit "land" or "merge"',
            "Do not deploy, force-push, or publish packages by implication",
            "Re-classify each new task",
            "major-bumps a direct runtime dependency, SDK, or service provider",
            "cross-cutting work needs independent review before reporting",
            "A preview or staging deploy Patpat starts also needs",
        )
        if len(m.STICKY_CONTEXT) > 1200:
            raise AssertionError("sticky context exceeds the 1200-character hook context limit")
        hook_output = continued.get("hookSpecificOutput")
        if not isinstance(hook_output, dict) or hook_output.get("hookEventName") != "UserPromptSubmit":
            raise AssertionError("sticky mode did not populate host-facing hook output")
        sticky_text = hook_output.get("additionalContext")
        if continued.get("additional_context") != sticky_text:
            raise AssertionError("host-facing and compatibility context diverged")
        if not isinstance(sticky_text, str) or any(
            requirement not in sticky_text for requirement in required_sticky_context
        ):
            raise AssertionError("sticky mode dropped an activation or delivery boundary")

        # KV-cache prefix stability: repeated sticky renderings across turns and
        # resume/compact events must emit byte-identical STICKY_CONTEXT with no dynamic state.
        continued_again = m.handle_hook(
            {**payload, "prompt": "run the next verification step"},
            plugin_data=plugin_data,
            now_ms=2_500,
        )
        resumed = m.handle_hook(
            {
                "hook_event_name": "SessionStart",
                "source": "resume",
                "session_id": payload["session_id"],
                "cwd": payload["cwd"],
            },
            plugin_data=plugin_data,
            now_ms=2_750,
        )
        if not continued_again or not resumed:
            raise AssertionError("sticky context failed to render on repeated turn or resume")
        if json.dumps(continued, sort_keys=True).encode("utf-8") != json.dumps(
            continued_again, sort_keys=True
        ).encode("utf-8"):
            raise AssertionError("sticky hook JSON output drifted across turns (KV-cache regression)")
        ctx_bytes_1 = continued["hookSpecificOutput"]["additionalContext"].encode("utf-8")
        ctx_bytes_2 = continued_again["hookSpecificOutput"]["additionalContext"].encode("utf-8")
        ctx_bytes_resume = resumed["hookSpecificOutput"]["additionalContext"].encode("utf-8")
        if not (ctx_bytes_1 == ctx_bytes_2 == ctx_bytes_resume == m.STICKY_CONTEXT.encode("utf-8")):
            raise AssertionError("STICKY_CONTEXT bytes are not identical across turns and resume")

        setup = m.handle_hook(
            {**payload, "prompt": "use $patpat-setup on this host"},
            plugin_data=plugin_data,
            now_ms=3_000,
        )
        if setup is None:
            raise AssertionError("unrelated later prompt should still be sticky")
        disabled = m.handle_hook(
            {**payload, "prompt": "/patpat off"},
            plugin_data=plugin_data,
            now_ms=4_000,
        )
        if disabled is not None:
            raise AssertionError("disable must clear sticky context")
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=5_000) is not None:
            raise AssertionError("sticky mode survived disable")

        def activate(now_ms: int) -> dict[str, Path]:
            result = m.handle_hook(payload, plugin_data=plugin_data, now_ms=now_ms)
            if not result:
                raise AssertionError("test activation failed")
            resolved = m.state_paths(plugin_data, payload["session_id"])
            if not resolved:
                raise AssertionError("test state path resolution failed")
            return resolved

        forged = activate(10_000)
        m.remove_state_path(forged["receipt"])
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=11_000):
            raise AssertionError("state without an activation receipt was trusted")

        mismatches = (
            (20_000, "projectFingerprint", "0" * 64, "project"),
            (22_000, "sessionBinding", "0" * 64, "session"),
            (24_000, "activationId", "0" * 64, "activation"),
        )
        for activated_at, field, forged_value, label in mismatches:
            mismatched = activate(activated_at)
            mismatched_receipt = m.read_json(mismatched["receipt"])
            if not mismatched_receipt:
                raise AssertionError("test receipt was unreadable")
            mismatched_receipt[field] = forged_value
            m.atomic_write(mismatched["receipt"], mismatched_receipt)
            if m.handle_hook(
                {**payload, "prompt": "continue"},
                plugin_data=plugin_data,
                now_ms=activated_at + 1_000,
            ):
                raise AssertionError(f"{label}-mismatched activation receipt was trusted")

        legacy = activate(30_000)
        legacy_state = m.read_json(legacy["state"])
        legacy_receipt = m.read_json(legacy["receipt"])
        if not legacy_state or not legacy_receipt:
            raise AssertionError("legacy-state fixture was unreadable")
        legacy_state["schema"] = 1
        legacy_receipt["schema"] = 1
        m.atomic_write(legacy["state"], legacy_state)
        m.atomic_write(legacy["receipt"], legacy_receipt)
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=31_000):
            raise AssertionError("legacy sticky state survived the schema bump")

        oversized = activate(40_000)
        oversized["state"].write_bytes(b"x" * (m.MAX_STATE_BYTES + 1))
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=41_000):
            raise AssertionError("oversized state was trusted")

        linked = activate(50_000)
        external = Path(directory) / "external.json"
        external.write_text('{"protected": true}\n', encoding="utf-8")
        m.remove_state_path(linked["state"])
        linked["state"].symlink_to(external)
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=51_000):
            raise AssertionError("symlinked state was trusted")
        if external.read_text(encoding="utf-8") != '{"protected": true}\n':
            raise AssertionError("symlink rejection modified its target")

        unowned = targets["state"].parent / "unowned.json"
        unowned.write_text("{}\n", encoding="utf-8")
        m.handle_hook(
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

            os.replace = replace_then_redirect
            os.chmod = reject_path_chmod
            try:
                m.atomic_write(targets["state"], {"race": True})
            finally:
                os.replace = original_replace
                os.chmod = original_chmod
            if stat.S_IMODE(protected_mode.stat().st_mode) != 0o644:
                raise AssertionError("atomic state publication changed a redirected target's permissions")
            m.remove_state_path(targets["state"])

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
                    raise AssertionError(f"Windows junction fixture could not be created: {result.stderr}")
            else:
                link.symlink_to(destination, target_is_directory=True)
            try:
                metadata = link.lstat()
            except OSError as error:
                raise AssertionError(f"directory redirect fixture is missing: {link}") from error
            if not m._is_link_or_reparse_point(metadata):
                raise AssertionError(f"directory redirect fixture was not recognized: {link}")

        for redirected_directory in ("patpat-loop", "sessions", "receipts"):
            with tempfile.TemporaryDirectory(prefix="patpat-hook-redirect-") as redirect_root:
                redirect_base = Path(redirect_root) / "plugin-data"
                redirect_base.mkdir()
                state_root = redirect_base / "patpat-loop"
                outside = Path(redirect_root) / "outside"
                outside.mkdir()
                redirect_session = f"redirect-{redirected_directory}"
                redirect_key = m.session_key(redirect_session)
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
                m.collect_expired(str(redirect_base), 100_000, m.DEFAULT_TTL_MS)
                if victim.read_text(encoding="utf-8") != "{}\n":
                    raise AssertionError(f"cleanup followed redirected {redirected_directory} directory")
                redirect_result = m.handle_hook(
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
        if m.handle_hook(
            {**payload, "cwd": str(Path(directory) / "other-project"), "prompt": "continue"},
            plugin_data=plugin_data,
            now_ms=61_000,
        ):
            raise AssertionError("state was accepted for a different project")

        nonregular = activate(70_000)
        m.remove_state_path(nonregular["state"])
        nonregular["state"].mkdir()
        if m.handle_hook({**payload, "prompt": "continue"}, plugin_data=plugin_data, now_ms=71_000):
            raise AssertionError("non-regular state was trusted")

        if m.decode_payload(b"{}") != {}:
            raise AssertionError("bounded payload decoder rejected a valid object")
        if m.decode_payload(b"[]") is not None:
            raise AssertionError("bounded payload decoder accepted a non-object")
        if m.decode_payload(b"x" * (m.MAX_STDIN_BYTES + 1)) is not None:
            raise AssertionError("oversized hook input was accepted")
        if m.handle_hook(payload, plugin_data="", now_ms=6_000) is not None:
            raise AssertionError("missing plugin data must fail closed")
        if m.resolve_plugin_data({"PLUGIN_DATA": "/primary", "GROK_PLUGIN_DATA": "/grok"}) != "/primary":
            raise AssertionError("PLUGIN_DATA must take precedence")
        if m.resolve_plugin_data({"GROK_PLUGIN_DATA": "/grok"}) != "/grok":
            raise AssertionError("GROK_PLUGIN_DATA was not recognized")
        if m.resolve_plugin_data({"CLAUDE_PLUGIN_DATA": "/compat"}) != "/compat":
            raise AssertionError("CLAUDE_PLUGIN_DATA compatibility alias was not recognized")
        if m.resolve_plugin_data({}) is not None:
            raise AssertionError("missing plugin data environment must fail closed")

        expired_payload = {**payload, "session_id": "expired-session"}
        expired = m.handle_hook(expired_payload, plugin_data=plugin_data, now_ms=80_000)
        expired_targets = m.state_paths(plugin_data, "expired-session")
        if not expired or not expired_targets:
            raise AssertionError("expired-state fixture could not be activated")
        if m.handle_hook(
            {**expired_payload, "prompt": "continue"},
            plugin_data=plugin_data,
            now_ms=80_000 + m.DEFAULT_TTL_MS + 1,
        ):
            raise AssertionError("expired sticky state was trusted")
        if expired_targets["state"].exists() or expired_targets["receipt"].exists():
            raise AssertionError("expired sticky state was not cleared")

        skew_payload = {**payload, "session_id": "clock-skew-session"}
        skew_activated = m.handle_hook(skew_payload, plugin_data=plugin_data, now_ms=200_000)
        skew_targets = m.state_paths(plugin_data, "clock-skew-session")
        if not skew_activated or not skew_targets:
            raise AssertionError("clock-skew fixture could not be activated")
        m.collect_expired(plugin_data, 170_000, m.DEFAULT_TTL_MS)
        if not skew_targets["state"].exists() or not skew_targets["receipt"].exists():
            raise AssertionError("collect_expired wiped state on bounded backward NTP skew")
        skew_turn_1 = m.handle_hook(
            {**skew_payload, "prompt": "continue under backward skew"},
            plugin_data=plugin_data,
            now_ms=170_000,
        )
        if not skew_turn_1 or "Patpat Loop is active" not in json.dumps(skew_turn_1):
            raise AssertionError("bounded backward NTP skew (30s) wiped active sticky state")
        skew_turn_2 = m.handle_hook(
            {**skew_payload, "prompt": "continue again under backward skew"},
            plugin_data=plugin_data,
            now_ms=175_000,
        )
        if not skew_turn_2 or "Patpat Loop is active" not in json.dumps(skew_turn_2):
            raise AssertionError("sticky state did not survive a second turn under backward NTP skew")
        if m.handle_hook(
            {**skew_payload, "prompt": "continue beyond skew limit"},
            plugin_data=plugin_data,
            now_ms=200_000 - m.MAX_BACKWARD_CLOCK_SKEW_MS - 1,
        ):
            raise AssertionError("backward clock skew exceeding tolerance was trusted")
        if skew_targets["state"].exists() or skew_targets["receipt"].exists():
            raise AssertionError("excessive backward clock skew state was not cleared")
    print("Patpat loop sticky-hook self-test passed.")


if __name__ == "__main__":
    run_self_test()
