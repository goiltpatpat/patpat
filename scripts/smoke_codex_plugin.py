#!/usr/bin/env python3
"""Smoke-test Patpat marketplace installation in an isolated Codex home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from stage_plugin import file_inventory, stage
from validate import validate_root


PLUGIN_ID = "patpat@patpat"


class SmokeError(RuntimeError):
    """Raised when the isolated Codex installation contract fails."""


def run_json(command: list[str], environment: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if result.returncode != 0:
        raise SmokeError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SmokeError(f"command returned invalid JSON: {' '.join(command)}") from error
    if not isinstance(value, dict):
        raise SmokeError(f"command JSON root must be an object: {' '.join(command)}")
    return value


def skill_names(root: Path) -> set[str]:
    skills = root / "skills"
    return {
        path.name
        for path in skills.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


def main() -> int:
    codex = shutil.which("codex")
    if not codex:
        print("Codex smoke test skipped: codex CLI is unavailable.", file=sys.stderr)
        return 2

    source = Path(__file__).resolve().parents[1]
    source_errors = validate_root(source)
    if source_errors:
        raise SmokeError(f"source validation failed: {'; '.join(source_errors)}")

    with tempfile.TemporaryDirectory(prefix="patpat-codex-smoke-") as directory:
        root = Path(directory)
        codex_home = root / "codex-home"
        isolated_home = root / "home"
        codex_home.mkdir()
        isolated_home.mkdir()
        staged_source = root / "patpat-dist"
        staged_inventory = stage(source, staged_source)
        environment = os.environ.copy()
        environment.update({"CODEX_HOME": str(codex_home), "HOME": str(isolated_home)})

        added_marketplace = run_json(
            [codex, "plugin", "marketplace", "add", str(staged_source), "--json"],
            environment,
        )
        if added_marketplace.get("marketplaceName") != "patpat":
            raise SmokeError("Codex registered the wrong marketplace name")

        available = run_json(
            [codex, "plugin", "list", "--available", "--json"],
            environment,
        )
        available_ids = {
            item.get("pluginId")
            for item in available.get("available", [])
            if isinstance(item, dict)
        }
        if PLUGIN_ID not in available_ids:
            raise SmokeError("Patpat was not discoverable in the isolated marketplace")

        installed = run_json(
            [codex, "plugin", "add", PLUGIN_ID, "--json"],
            environment,
        )
        raw_installed_path = installed.get("installedPath")
        if not isinstance(raw_installed_path, str) or not raw_installed_path:
            raise SmokeError("Codex did not return an installed artifact path")
        installed_path = Path(raw_installed_path)
        cache_root = codex_home / "plugins" / "cache" / "patpat"
        try:
            installed_path.resolve().relative_to(cache_root.resolve())
        except ValueError as error:
            raise SmokeError("Codex installed the artifact outside the isolated cache") from error
        if not installed_path.is_absolute() or not installed_path.is_dir():
            raise SmokeError("Codex did not return an installed artifact directory")
        installed_errors = validate_root(installed_path)
        if installed_errors:
            raise SmokeError(f"installed artifact validation failed: {'; '.join(installed_errors)}")
        if skill_names(installed_path) != skill_names(staged_source):
            raise SmokeError("installed skill catalog differs from the source catalog")
        if file_inventory(installed_path) != staged_inventory:
            raise SmokeError("installed artifact inventory differs from the staged distribution")

        listed = run_json([codex, "plugin", "list", "--json"], environment)
        installed_ids = {
            item.get("pluginId")
            for item in listed.get("installed", [])
            if isinstance(item, dict)
        }
        if PLUGIN_ID not in installed_ids:
            raise SmokeError("installed Patpat plugin was absent from Codex plugin list")

        run_json([codex, "plugin", "remove", PLUGIN_ID, "--json"], environment)
        if installed_path.exists():
            raise SmokeError("Codex plugin removal left the installed artifact behind")

        reinstalled = run_json(
            [codex, "plugin", "add", PLUGIN_ID, "--json"],
            environment,
        )
        raw_reinstalled_path = reinstalled.get("installedPath")
        if not isinstance(raw_reinstalled_path, str) or not raw_reinstalled_path:
            raise SmokeError("Codex reinstall did not return an artifact path")
        reinstalled_path = Path(raw_reinstalled_path)
        if file_inventory(reinstalled_path) != staged_inventory:
            raise SmokeError("Codex reinstall did not refresh the staged distribution")
        run_json([codex, "plugin", "remove", PLUGIN_ID, "--json"], environment)
        if reinstalled_path.exists():
            raise SmokeError("Codex reinstall removal left the artifact behind")

        run_json([codex, "plugin", "marketplace", "remove", "patpat", "--json"], environment)
        remaining_cache_files = list(cache_root.rglob("*")) if cache_root.exists() else []
        if any(path.is_file() or path.is_symlink() for path in remaining_cache_files):
            raise SmokeError("Codex removal left cached plugin files behind")

    print("Patpat Codex marketplace smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as error:
        print(f"Patpat Codex smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1)
