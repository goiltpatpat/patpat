#!/usr/bin/env python3
"""Stage an allowlisted Patpat distribution without local continuity state."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from validate import validate_root


PACKAGE_ENTRIES = (
    ".agents/plugins",
    ".codex-plugin",
    ".cursor-plugin",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "adapters",
    "agents",
    "assets",
    "docs",
    "hooks",
    "hooks.json",
    "plugin.json",
    "scripts",
    "skills",
)
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


class StageError(RuntimeError):
    """Raised when a distribution cannot be staged safely."""


def paths_overlap(source: Path, target: Path) -> bool:
    source = source.resolve()
    target = target.resolve()
    return target == source or source in target.parents or target in source.parents


def reject_symlinks(path: Path) -> None:
    candidates = [path, *path.rglob("*")] if path.is_dir() else [path]
    for candidate in candidates:
        if candidate.is_symlink():
            raise StageError(f"package source contains a symlink: {candidate}")


def copy_entry(source: Path, destination: Path) -> None:
    reject_symlinks(source)
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(*IGNORED_NAMES, "*.pyc", "*.pyo"),
        )
    elif source.is_file():
        shutil.copy2(source, destination)
    else:
        raise StageError(f"missing package entry: {source}")


def file_inventory(root: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise StageError(f"staged artifact contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        inventory[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return inventory


def stage(source: Path, target: Path) -> dict[str, str]:
    source = source.resolve()
    target = target.resolve()
    if paths_overlap(source, target):
        raise StageError("stage target must not overlap the source repository")
    if target.exists() or target.is_symlink():
        raise StageError(f"stage target already exists: {target}")
    errors = validate_root(source)
    if errors:
        raise StageError(f"source validation failed: {'; '.join(errors)}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.mkdir()
    try:
        for relative in PACKAGE_ENTRIES:
            copy_entry(source / relative, temporary / relative)
        if (temporary / "memory-bank").exists():
            raise StageError("local Memory Bank entered the staged artifact")
        staged_errors = validate_root(temporary)
        if staged_errors:
            raise StageError(f"staged artifact validation failed: {'; '.join(staged_errors)}")
        inventory = file_inventory(temporary)
        os.replace(temporary, target)
        return inventory
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def run_self_test(source: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="patpat-stage-test-") as directory:
        root = Path(directory)
        target = root / "patpat-dist"
        inventory = stage(source, target)
        if not inventory or (target / "memory-bank").exists():
            raise StageError("stage self-test produced an invalid distribution")
        if inventory != file_inventory(target):
            raise StageError("stage self-test inventory changed after atomic promotion")
        staged_agent_entries = {
            path for path in inventory if path.startswith(".agents/")
        }
        if staged_agent_entries != {".agents/plugins/marketplace.json"}:
            raise StageError(
                f"stage self-test found unexpected .agents entries: {sorted(staged_agent_entries)}"
            )
        try:
            stage(source, target)
        except StageError:
            pass
        else:
            raise StageError("stage self-test overwrote an existing target")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    if args.self_test:
        run_self_test(source)
        print("Patpat staging self-test passed.")
        return 0
    if args.target is None:
        parser.error("--target is required unless --self-test is used")
    inventory = stage(source, args.target.expanduser())
    print(f"Staged {len(inventory)} files into {args.target.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StageError as error:
        print(f"Patpat staging failed: {error}")
        raise SystemExit(1)
