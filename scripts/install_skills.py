#!/usr/bin/env python3
"""Install Patpat skills into an explicit agent skill directory."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from update_skills import (
    INVENTORY_NAME,
    SCHEMA,
    inventory,
    load_recorded_inventory,
    write_json,
)
from validate import validate_root


def skill_directories(source: Path) -> list[Path]:
    return sorted(
        path for path in source.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def paths_overlap(source: Path, target: Path) -> bool:
    source = source.resolve()
    target = target.resolve()
    return target == source or source in target.parents or target in source.parents


def rollback(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for destination in reversed(paths):
        try:
            if destination.is_symlink():
                destination.unlink()
            elif destination.is_dir():
                shutil.rmtree(destination)
            elif destination.is_file():
                destination.unlink()
        except Exception as error:
            errors.append(f"{destination}: {error}")
    return errors


def install_paths(source: Path, target: Path, skills: list[Path], mode: str, dry_run: bool) -> int:
    if paths_overlap(source, target):
        print("Refusing an install target that overlaps the canonical skills directory.", file=sys.stderr)
        return 2

    conflicts = [
        target / skill.name
        for skill in skills
        if (target / skill.name).exists() or (target / skill.name).is_symlink()
    ]
    marker = target / INVENTORY_NAME
    if marker.exists() or marker.is_symlink():
        conflicts.append(marker)
    if conflicts:
        print("Refusing to overwrite existing skills:", file=sys.stderr)
        for conflict in conflicts:
            print(f"- {conflict}", file=sys.stderr)
        return 2

    for skill in skills:
        destination = target / skill.name
        print(f"{mode}: {skill} -> {destination}")

    if dry_run:
        return 0

    target.mkdir(parents=True, exist_ok=True)
    installed: list[Path] = []
    try:
        for skill in skills:
            destination = target / skill.name
            if mode == "copy":
                destination.mkdir()
                installed.append(destination)
                shutil.copytree(skill, destination, dirs_exist_ok=True)
            else:
                destination.symlink_to(skill, target_is_directory=True)
                installed.append(destination)
        marker = target / INVENTORY_NAME
        installed.append(marker)
        write_json(
            marker,
            {
                "plugin": "patpat",
                "schema": SCHEMA,
                "mode": mode,
                "skills": {
                    skill.name: (
                        inventory(target / skill.name)
                        if mode == "copy"
                        else {"target": str(skill.resolve())}
                    )
                    for skill in skills
                },
            },
        )
    except BaseException as error:
        cleanup_errors = rollback(installed)
        if cleanup_errors:
            print("Rollback was incomplete:", file=sys.stderr)
            for cleanup_error in cleanup_errors:
                print(f"- {cleanup_error}", file=sys.stderr)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"Install failed; owned paths were rolled back: {error}", file=sys.stderr)
        return 3

    print(f"Installed {len(skills)} skills into {target}")
    return 0


def trees_match(source: Path, target: Path) -> bool:
    source_files = sorted(path.relative_to(source) for path in source.rglob("*") if path.is_file())
    target_files = sorted(path.relative_to(target) for path in target.rglob("*") if path.is_file())
    return source_files == target_files and all(
        (source / relative).read_bytes() == (target / relative).read_bytes()
        for relative in source_files
    )


def run_self_test(source: Path, skills: list[Path]) -> int:
    with tempfile.TemporaryDirectory(prefix="patpat-installer-") as temp_directory:
        root = Path(temp_directory)
        copy_target = root / "copy"
        link_target = root / "links"
        interrupt_target = root / "interrupt"

        statuses = {
            "copy": install_paths(source, copy_target, skills, "copy", False),
            "symlink": install_paths(source, link_target, skills, "symlink", False),
            "conflict": install_paths(source, copy_target, skills, "copy", False),
            "nested overlap": install_paths(source, source / "nested", skills, "copy", True),
            "ancestor overlap": install_paths(source, source.parent, skills, "copy", True),
        }
        checks = {
            "copy install": statuses["copy"] == 0,
            "symlink install": statuses["symlink"] == 0,
            "conflict refusal": statuses["conflict"] == 2,
            "nested overlap refusal": statuses["nested overlap"] == 2,
            "ancestor overlap refusal": statuses["ancestor overlap"] == 2,
            "copy fidelity": all(trees_match(skill, copy_target / skill.name) for skill in skills),
            "symlink fidelity": all((link_target / skill.name).is_symlink() for skill in skills),
        }
        recorded = load_recorded_inventory(copy_target)
        checks["copy ownership inventory"] = recorded == {
            skill.name: inventory(copy_target / skill.name)
            for skill in skills
        }
        checks["symlink ownership inventory"] = (link_target / INVENTORY_NAME).is_file()

        original_copytree = shutil.copytree

        def interrupt_copy(source_path: Path, destination: Path, dirs_exist_ok: bool = False) -> None:
            del source_path, dirs_exist_ok
            (destination / "partial").write_text("partial", encoding="utf-8")
            raise KeyboardInterrupt

        shutil.copytree = interrupt_copy
        try:
            try:
                install_paths(source, interrupt_target, skills, "copy", False)
            except KeyboardInterrupt:
                interrupted = True
            else:
                interrupted = False
        finally:
            shutil.copytree = original_copytree

        checks["interrupt propagation"] = interrupted
        checks["interrupt rollback"] = not interrupt_target.exists() or not any(interrupt_target.iterdir())
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            print(f"Installer self-test failed: {', '.join(failed)}", file=sys.stderr)
            return 1

    print("Patpat installer self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install Patpat skills without overwriting existing skills."
    )
    parser.add_argument(
        "--target",
        type=Path,
        help="Explicit .agents/skills or other agent skill directory.",
    )
    parser.add_argument(
        "--mode",
        choices=("copy", "symlink"),
        default="copy",
        help="Copy skills or create absolute directory symlinks.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument(
        "--verify-ready",
        action="store_true",
        help="Verify host, /patpat discovery, hook status, and core route presence.",
    )
    parser.add_argument("--json", action="store_true", help="Print verification as JSON.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    if args.verify_ready:
        from verify_ready import verify_ready
        return verify_ready(root, target=args.target, as_json=args.json)

    source = root / "skills"
    validation_errors = validate_root(root)
    if validation_errors:
        print("Refusing to install an invalid Patpat source:", file=sys.stderr)
        for error in validation_errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    skills = skill_directories(source)
    if not skills:
        print("No valid skills found.", file=sys.stderr)
        return 1

    if args.self_test:
        return run_self_test(source, skills)

    if args.target is None:
        parser.error("--target is required unless --self-test or --verify-ready is used")

    target = args.target.expanduser().resolve()
    return install_paths(source, target, skills, args.mode, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
