#!/usr/bin/env python3
"""Smoke-test Patpat installation in an isolated Antigravity home."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from stage_plugin import file_inventory, stage
from validate import validate_root


class SmokeError(RuntimeError):
    """Raised when the isolated Antigravity installation contract fails."""


def run(command: list[str], environment: dict[str, str]) -> str:
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
    return result.stdout


def main() -> int:
    agy = shutil.which("agy")
    if not agy:
        print("Antigravity smoke test skipped: agy CLI is unavailable.", file=sys.stderr)
        return 2

    source = Path(__file__).resolve().parents[1]
    source_errors = validate_root(source)
    if source_errors:
        raise SmokeError(f"source validation failed: {'; '.join(source_errors)}")

    with tempfile.TemporaryDirectory(prefix="patpat-antigravity-smoke-") as directory:
        isolated_home = Path(directory) / "home"
        isolated_home.mkdir()
        staged_source = Path(directory) / "patpat-dist"
        staged_inventory = stage(source, staged_source)
        environment = os.environ.copy()
        environment["HOME"] = str(isolated_home)

        run([agy, "plugin", "validate", str(staged_source)], environment)
        run([agy, "plugin", "install", str(staged_source)], environment)

        installed_path = isolated_home / ".gemini" / "config" / "plugins" / "patpat"
        if not installed_path.is_dir():
            raise SmokeError("Antigravity did not stage the Patpat artifact")
        installed_errors = validate_root(installed_path)
        if installed_errors:
            raise SmokeError(f"installed artifact validation failed: {'; '.join(installed_errors)}")
        if file_inventory(installed_path) != staged_inventory:
            raise SmokeError("installed artifact inventory differs from the staged distribution")

        listing = json.loads(run([agy, "plugin", "list"], environment))
        imports = listing.get("imports", []) if isinstance(listing, dict) else []
        if not any(isinstance(item, dict) and item.get("name") == "patpat" for item in imports):
            raise SmokeError("installed Patpat plugin was absent from Antigravity plugin list")

        run([agy, "plugin", "uninstall", "patpat"], environment)
        if installed_path.exists():
            raise SmokeError("Antigravity uninstall left the staged plugin behind")
        final_listing = run([agy, "plugin", "list"], environment).strip()
        if final_listing != "No imported plugins.":
            raise SmokeError("Antigravity uninstall left a plugin registry entry")

    print("Patpat Antigravity plugin smoke test passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, json.JSONDecodeError) as error:
        print(f"Patpat Antigravity smoke test failed: {error}", file=sys.stderr)
        raise SystemExit(1)
