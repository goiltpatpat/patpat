#!/usr/bin/env python3
"""Install Patpat skills into an explicit agent skill directory."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path

from update_skills import (
    INVENTORY_NAME,
    SCHEMA,
    inventory,
    load_recorded_inventory,
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


def stat_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, stat.S_IFMT(metadata.st_mode)


def rollback(paths: list[tuple[Path, tuple[int, int, int]]]) -> list[str]:
    errors: list[str] = []
    for destination, expected_identity in reversed(paths):
        try:
            metadata = destination.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            errors.append(f"{destination}: could not inspect install-owned path: {error}")
            continue
        try:
            if stat_identity(metadata) != expected_identity:
                errors.append(f"{destination}: ownership changed during install; left untouched")
            elif stat.S_ISLNK(metadata.st_mode):
                destination.unlink()
            elif stat.S_ISDIR(metadata.st_mode):
                shutil.rmtree(destination)
            elif stat.S_ISREG(metadata.st_mode):
                destination.unlink()
            else:
                errors.append(f"{destination}: unsupported entry type during rollback; left untouched")
        except Exception as error:
            errors.append(f"{destination}: {error}")
    return errors


def remove_staging_directory(path: Path) -> str | None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        return f"Could not remove installer staging directory {path}: {error}"
    return None


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
    transaction = Path(tempfile.mkdtemp(prefix=".patpat-install-", dir=target))
    installed: list[tuple[Path, tuple[int, int, int]]] = []
    try:
        staged_paths: dict[str, Path] = {}
        for skill in skills:
            destination = transaction / skill.name
            if mode == "copy":
                shutil.copytree(skill, destination)
            else:
                destination.symlink_to(skill, target_is_directory=True)
            staged_paths[skill.name] = destination

        marker_contents = (
            json.dumps(
                {
                    "plugin": "patpat",
                    "schema": SCHEMA,
                    "mode": mode,
                    "skills": {
                        skill.name: (
                            inventory(staged_paths[skill.name])
                            if mode == "copy"
                            else {"target": str(skill.resolve())}
                        )
                        for skill in skills
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")

        for skill in skills:
            staged = staged_paths[skill.name]
            destination = target / skill.name
            if destination.exists() or destination.is_symlink():
                raise FileExistsError(f"install target appeared during staging: {destination}")
            expected_identity = stat_identity(staged.lstat())
            os.rename(staged, destination)
            installed.append((destination, expected_identity))
            if stat_identity(destination.lstat()) != expected_identity:
                raise OSError(f"installed path changed during promotion: {destination}")

        marker = target / INVENTORY_NAME
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(marker, flags, 0o666)
        try:
            installed.append((marker, stat_identity(os.fstat(descriptor))))
            with os.fdopen(descriptor, "wb") as stream:
                descriptor = -1
                stream.write(marker_contents)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except BaseException as error:
        cleanup_errors = rollback(installed)
        if cleanup_errors:
            print("Rollback was incomplete:", file=sys.stderr)
            for cleanup_error in cleanup_errors:
                print(f"- {cleanup_error}", file=sys.stderr)
        staging_error = remove_staging_directory(transaction)
        if staging_error:
            print(staging_error, file=sys.stderr)
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"Install failed; owned paths were rolled back: {error}", file=sys.stderr)
        return 3

    staging_error = remove_staging_directory(transaction)
    if staging_error:
        print(staging_error, file=sys.stderr)
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
        marker_race_target = root / "marker-race"
        copy_race_target = root / "copy-race"
        rollback_race_target = root / "rollback-race"

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
            destination.mkdir()
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

        copy_victim = root / "copy-victim"
        copy_victim.mkdir()
        copy_victim_marker = copy_victim / "preserve.txt"
        copy_victim_marker.write_text("preserve-copy-victim", encoding="utf-8")
        final_skill_path = copy_race_target / skills[0].name
        original_copytree = shutil.copytree
        redirected = False

        def redirect_final_path_before_copy(
            source_path: Path,
            destination: Path,
            *args: object,
            **kwargs: object,
        ) -> Path:
            nonlocal redirected
            if not redirected:
                if final_skill_path.exists() and final_skill_path.is_dir():
                    shutil.rmtree(final_skill_path)
                final_skill_path.symlink_to(copy_victim, target_is_directory=True)
                redirected = True
            return original_copytree(source_path, destination, *args, **kwargs)

        shutil.copytree = redirect_final_path_before_copy
        try:
            copy_race_status = install_paths(source, copy_race_target, skills, "copy", False)
        finally:
            shutil.copytree = original_copytree
        checks["copy stages before final path promotion"] = (
            copy_race_status == 3
            and final_skill_path.is_symlink()
            and copy_victim_marker.read_text(encoding="utf-8") == "preserve-copy-victim"
            and sorted(path.name for path in copy_victim.iterdir()) == ["preserve.txt"]
        )

        marker_victim = root / "marker-victim.txt"
        marker_victim.write_text("preserve-marker-victim", encoding="utf-8")
        marker_path = marker_race_target / INVENTORY_NAME
        original_open = os.open

        def replace_marker_before_create(path: str | os.PathLike[str], *args: object, **kwargs: object) -> int:
            if Path(path) == marker_path:
                marker_path.symlink_to(marker_victim)
            return original_open(path, *args, **kwargs)

        os.open = replace_marker_before_create
        try:
            marker_race_status = install_paths(source, marker_race_target, skills, "copy", False)
        finally:
            os.open = original_open
        checks["marker symlink race refusal"] = (
            marker_race_status == 3
            and marker_path.is_symlink()
            and marker_victim.read_text(encoding="utf-8") == "preserve-marker-victim"
        )

        replacement = root / "replacement"
        replacement.mkdir()
        replacement_marker = replacement / "foreign.txt"
        replacement_marker.write_text("preserve-replacement", encoding="utf-8")
        rollback_destination = rollback_race_target / skills[0].name
        rollback_marker = rollback_race_target / INVENTORY_NAME
        original_open = os.open

        def replace_installed_path_before_marker(
            path: str | os.PathLike[str], *args: object, **kwargs: object
        ) -> int:
            if Path(path) == rollback_marker:
                shutil.rmtree(rollback_destination)
                os.replace(replacement, rollback_destination)
                raise OSError("injected marker creation failure")
            return original_open(path, *args, **kwargs)

        os.open = replace_installed_path_before_marker
        rollback_stderr = io.StringIO()
        try:
            with contextlib.redirect_stderr(rollback_stderr):
                rollback_status = install_paths(source, rollback_race_target, skills, "copy", False)
        finally:
            os.open = original_open
        checks["rollback preserves replaced path"] = (
            rollback_status == 3
            and (rollback_destination / "foreign.txt").read_text(encoding="utf-8") == "preserve-replacement"
            and "ownership changed during install" in rollback_stderr.getvalue()
        )

        blocked = root / "blocked-cleanup"
        remaining = root / "remaining-cleanup"
        blocked.mkdir()
        remaining.mkdir()
        blocked_identity = stat_identity(blocked.lstat())
        remaining_identity = stat_identity(remaining.lstat())
        original_lstat = Path.lstat

        def deny_one_lstat(path: Path, *args: object, **kwargs: object) -> os.stat_result:
            if path == blocked:
                raise PermissionError("injected inspection denial")
            return original_lstat(path, *args, **kwargs)

        Path.lstat = deny_one_lstat
        try:
            cleanup_errors = rollback(
                [(remaining, remaining_identity), (blocked, blocked_identity)]
            )
        finally:
            Path.lstat = original_lstat
        checks["rollback continues after inspection error"] = (
            len(cleanup_errors) == 1
            and "could not inspect install-owned path" in cleanup_errors[0]
            and blocked.exists()
            and not remaining.exists()
        )

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
