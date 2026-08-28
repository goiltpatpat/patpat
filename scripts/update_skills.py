#!/usr/bin/env python3
"""Safely update an existing portable Patpat copy installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

from validate import validate_root


INVENTORY_NAME = ".patpat-inventory.json"
BACKUP_MANIFEST_NAME = ".patpat-backup.json"
SCHEMA = 1
IGNORED_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
NAME_LINE = re.compile(r"^name:\s*['\"]?([^'\"\s]+)['\"]?\s*$")
SKILL_NAME = re.compile(r"^patpat(?:-[a-z0-9]+)*$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(RuntimeError):
    """Raised when an update cannot preserve the installation contract."""


def skill_directories(source: Path) -> list[Path]:
    return sorted(
        path
        for path in source.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def paths_overlap(first: Path, second: Path) -> bool:
    first = first.resolve()
    second = second.resolve()
    return first == second or first in second.parents or second in first.parents


def is_ignored(path: Path) -> bool:
    return any(part in IGNORED_NAMES for part in path.parts) or path.suffix in {".pyc", ".pyo"}


def inventory(root: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if is_ignored(relative):
            continue
        if path.is_symlink():
            raise UpdateError(f"owned skill contains a symlink: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise UpdateError(f"owned skill contains an unsupported entry: {path}")
        files[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def declared_skill_name(skill: Path) -> str | None:
    try:
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    for line in text[4:end].splitlines():
        match = NAME_LINE.fullmatch(line.strip())
        if match:
            return match.group(1)
    return None


def validate_owned_skill(path: Path, expected_name: str) -> dict[str, str]:
    if path.is_symlink():
        raise UpdateError(f"copy installation contains an unexpected symlink: {path}")
    if not path.is_dir():
        raise UpdateError(f"installed Patpat skill is missing: {path}")
    actual_name = declared_skill_name(path)
    if actual_name != expected_name:
        raise UpdateError(
            f"refusing to replace unowned skill {path}: "
            f"frontmatter name is {actual_name!r}, expected {expected_name!r}"
        )
    return inventory(path)


def load_recorded_inventory(target: Path) -> dict[str, dict[str, str]] | None:
    marker = target / INVENTORY_NAME
    if not marker.exists():
        return None
    if marker.is_symlink() or not marker.is_file():
        raise UpdateError(f"inventory marker is not a regular file: {marker}")
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise UpdateError(f"inventory marker is unreadable: {marker}") from error
    if not isinstance(value, dict) or value.get("schema") != SCHEMA or value.get("plugin") != "patpat":
        raise UpdateError(f"inventory marker has an unsupported contract: {marker}")
    skills = value.get("skills")
    if not isinstance(skills, dict):
        raise UpdateError(f"inventory marker has no skill inventory: {marker}")
    normalized: dict[str, dict[str, str]] = {}
    for name, files in skills.items():
        if not isinstance(name, str) or SKILL_NAME.fullmatch(name) is None or not isinstance(files, dict):
            raise UpdateError(f"inventory marker has an invalid skill entry: {marker}")
        if not all(
            isinstance(path, str)
            and path
            and not Path(path).is_absolute()
            and ".." not in Path(path).parts
            and isinstance(digest, str)
            and DIGEST.fullmatch(digest) is not None
            for path, digest in files.items()
        ):
            raise UpdateError(f"inventory marker has an invalid file entry: {marker}")
        normalized[name] = dict(files)
    return normalized


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def copy_skill(source: Path, destination: Path) -> None:
    if source.is_symlink():
        raise UpdateError(f"canonical skill cannot be a symlink: {source}")
    shutil.copytree(
        source,
        destination,
        copy_function=shutil.copy2,
        ignore=shutil.ignore_patterns(*IGNORED_NAMES, "*.pyc", "*.pyo"),
    )


def validate_paths(source: Path, target: Path, backup: Path) -> None:
    if not target.is_dir() or target.is_symlink():
        raise UpdateError(f"target must be an existing real directory: {target}")
    if backup.exists() or backup.is_symlink():
        raise UpdateError(f"backup path already exists: {backup}")
    if not backup.parent.is_dir():
        raise UpdateError(f"backup parent must already exist: {backup.parent}")
    for first, second, label in (
        (source, target, "target overlaps the canonical skills directory"),
        (source, backup, "backup overlaps the canonical skills directory"),
        (target, backup, "backup overlaps the target skills directory"),
    ):
        if paths_overlap(first, second):
            raise UpdateError(label)
    if target.parent.stat().st_dev != backup.parent.stat().st_dev:
        raise UpdateError("backup and target must be on the same filesystem for atomic rename")


def classify_installation(source: Path, target: Path, skills: list[Path]) -> str:
    existing = [target / skill.name for skill in skills if (target / skill.name).exists() or (target / skill.name).is_symlink()]
    if not existing:
        raise UpdateError("target contains no recognizable Patpat skills")
    symlinks = [path.is_symlink() for path in existing]
    if any(symlinks):
        if not all(symlinks):
            raise UpdateError("mixed copy and symlink Patpat installations are not supported")
        sources = {skill.name: skill for skill in skills}
        for destination in existing:
            if destination.resolve() != sources[destination.name].resolve():
                raise UpdateError(f"refusing an unowned skill symlink: {destination}")
        return "symlink"
    return "copy"


def validate_copy_installation(
    target: Path,
    skills: list[Path],
) -> dict[str, dict[str, str]]:
    source_names = {skill.name for skill in skills}
    recorded = load_recorded_inventory(target)
    if recorded is not None:
        installed = {
            name: validate_owned_skill(target / name, name)
            for name in recorded
        }
        changed = [name for name in sorted(recorded) if recorded[name] != installed[name]]
        if changed:
            raise UpdateError(
                "installed Patpat skills changed since the last update: " + ", ".join(changed)
            )
        collisions = [
            name for name in sorted(source_names - set(recorded))
            if (target / name).exists() or (target / name).is_symlink()
        ]
        if collisions:
            raise UpdateError(
                "new Patpat skill names collide with unowned target paths: " + ", ".join(collisions)
            )
        return installed

    installed = {
        name: validate_owned_skill(target / name, name)
        for name in sorted(source_names)
        if (target / name).exists() or (target / name).is_symlink()
    }
    if not installed:
        raise UpdateError("target contains no recognizable Patpat copy installation")
    return installed


def rollback(
    target: Path,
    backup_work: Path,
    moved: list[str],
    promoted: list[str],
    marker_moved: bool,
) -> list[str]:
    errors: list[str] = []
    for name in reversed(promoted):
        destination = target / name
        try:
            if destination.is_symlink():
                destination.unlink()
            elif destination.exists():
                shutil.rmtree(destination)
        except Exception as error:
            errors.append(f"remove replacement {destination}: {error}")
    for name in reversed(moved):
        original = backup_work / name
        destination = target / name
        try:
            if original.exists() and not destination.exists() and not destination.is_symlink():
                os.replace(original, destination)
        except Exception as error:
            errors.append(f"restore {destination}: {error}")
    marker = target / INVENTORY_NAME
    old_marker = backup_work / INVENTORY_NAME
    try:
        if marker_moved and old_marker.exists():
            if marker.exists():
                marker.unlink()
            os.replace(old_marker, marker)
        elif not marker_moved and marker.exists():
            marker.unlink()
    except Exception as error:
        errors.append(f"restore inventory marker: {error}")
    return errors


def update_copy_installation(
    source: Path,
    target: Path,
    backup: Path,
    skills: list[Path],
    dry_run: bool,
    *,
    fail_after: int | None = None,
) -> None:
    old_inventory = validate_copy_installation(target, skills)
    source_inventory = {skill.name: inventory(skill) for skill in skills}
    for skill in skills:
        print(f"update: {target / skill.name} <- {skill}")
    print(f"backup: {backup}")
    if dry_run:
        return

    transaction = Path(tempfile.mkdtemp(prefix=f".{target.name}.patpat-update-", dir=target.parent))
    staged = transaction / "staged"
    backup_work = transaction / "backup"
    staged.mkdir()
    backup_work.mkdir()
    moved: list[str] = []
    promoted: list[str] = []
    marker = target / INVENTORY_NAME
    marker_moved = False
    try:
        for skill in skills:
            destination = staged / skill.name
            copy_skill(skill, destination)
            if inventory(destination) != source_inventory[skill.name]:
                raise UpdateError(f"staged inventory differs for {skill.name}")

        write_json(
            staged / INVENTORY_NAME,
            {"plugin": "patpat", "schema": SCHEMA, "skills": source_inventory},
        )
        for name in old_inventory:
            os.replace(target / name, backup_work / name)
            moved.append(name)
        for skill in skills:
            name = skill.name
            os.replace(staged / name, target / name)
            promoted.append(name)
            if fail_after is not None and len(promoted) >= fail_after:
                raise UpdateError("injected update failure")

        if marker.exists():
            os.replace(marker, backup_work / INVENTORY_NAME)
            marker_moved = True
        os.replace(staged / INVENTORY_NAME, marker)
        write_json(
            backup_work / BACKUP_MANIFEST_NAME,
            {
                "plugin": "patpat",
                "schema": SCHEMA,
                "skills": old_inventory,
                "restoreTarget": str(target),
            },
        )
        os.replace(backup_work, backup)
    except BaseException:
        errors = rollback(target, backup_work, moved, promoted, marker_moved)
        if errors:
            raise UpdateError("rollback was incomplete: " + "; ".join(errors))
        raise
    finally:
        if transaction.exists():
            shutil.rmtree(transaction)


def update(source: Path, target: Path, backup: Path, dry_run: bool, *, fail_after: int | None = None) -> None:
    if target.is_symlink():
        raise UpdateError(f"target must not be a symlink: {target}")
    if backup.is_symlink():
        raise UpdateError(f"backup path must not be a symlink: {backup}")
    source = source.resolve()
    target = target.resolve()
    backup = backup.resolve()
    validate_paths(source, target, backup)
    skills = skill_directories(source)
    if not skills:
        raise UpdateError("canonical skills directory contains no skills")
    installation = classify_installation(source, target, skills)
    if installation == "symlink":
        missing = [skill for skill in skills if not (target / skill.name).is_symlink()]
        for skill in missing:
            print(f"link: {target / skill.name} -> {skill}")
        if not dry_run:
            created: list[Path] = []
            try:
                for skill in missing:
                    destination = target / skill.name
                    destination.symlink_to(skill, target_is_directory=True)
                    created.append(destination)
            except BaseException:
                for destination in reversed(created):
                    destination.unlink(missing_ok=True)
                raise
        if missing:
            print("Patpat symlink catalog updated; source content already follows the checkout.")
        else:
            print("Patpat symlink installation already follows the canonical source; no update needed.")
        return
    update_copy_installation(source, target, backup, skills, dry_run, fail_after=fail_after)


def create_test_skill(root: Path, name: str, version: str) -> None:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Test skill.\n---\n\n# {name}\n\n{version}\n",
        encoding="utf-8",
    )
    (skill / "payload.txt").write_text(version + "\n", encoding="utf-8")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="patpat-updater-test-") as directory:
        root = Path(directory)
        source = root / "source"
        target = root / "skills"
        source.mkdir()
        target.mkdir()
        for name in ("patpat-alpha", "patpat-beta"):
            create_test_skill(source, name, "new")
            create_test_skill(target, name, "old")
        create_test_skill(target, "unrelated-skill", "keep")
        unrelated_before = inventory(target / "unrelated-skill")

        dry_backup = root / "dry-backup"
        update(source, target, dry_backup, True)
        if dry_backup.exists() or (target / "patpat-alpha" / "payload.txt").read_text() != "old\n":
            raise UpdateError("dry-run changed the installation")

        backup = root / "backup"
        update(source, target, backup, False)
        if inventory(target / "patpat-alpha") != inventory(source / "patpat-alpha"):
            raise UpdateError("updated skill differs from the source")
        if (backup / "patpat-alpha" / "payload.txt").read_text() != "old\n":
            raise UpdateError("backup does not contain the previous skill")
        if inventory(target / "unrelated-skill") != unrelated_before:
            raise UpdateError("update changed an unrelated skill")
        if not (target / INVENTORY_NAME).is_file() or not (backup / BACKUP_MANIFEST_NAME).is_file():
            raise UpdateError("update did not write ownership inventories")

        shutil.rmtree(source / "patpat-beta")
        create_test_skill(source, "patpat-gamma", "new")
        catalog_backup = root / "catalog-backup"
        update(source, target, catalog_backup, False)
        if (target / "patpat-beta").exists() or not (target / "patpat-gamma").is_dir():
            raise UpdateError("update did not reconcile the recorded skill catalog")
        if not (catalog_backup / "patpat-beta").is_dir():
            raise UpdateError("catalog update did not back up a retired skill")

        (target / "patpat-alpha" / "payload.txt").write_text("modified\n", encoding="utf-8")
        try:
            update(source, target, root / "tampered-backup", False)
        except UpdateError:
            pass
        else:
            raise UpdateError("update accepted a modified owned skill")

        rollback_target = root / "rollback-skills"
        rollback_target.mkdir()
        for name in ("patpat-alpha", "patpat-beta"):
            create_test_skill(rollback_target, name, "old")
        create_test_skill(rollback_target, "unrelated-skill", "keep")
        try:
            update(source, rollback_target, root / "rollback-backup", False, fail_after=1)
        except UpdateError as error:
            if str(error) != "injected update failure":
                raise
        else:
            raise UpdateError("failure injection did not fail")
        for name in ("patpat-alpha", "patpat-beta"):
            if (rollback_target / name / "payload.txt").read_text() != "old\n":
                raise UpdateError("automatic rollback did not restore the old installation")
        if (root / "rollback-backup").exists():
            raise UpdateError("failed update promoted a backup")

        wrong_target = root / "wrong-skills"
        wrong_target.mkdir()
        create_test_skill(wrong_target, "patpat-alpha", "old")
        create_test_skill(wrong_target, "patpat-beta", "old")
        (wrong_target / "patpat-alpha" / "SKILL.md").write_text(
            "---\nname: someone-else\ndescription: Not Patpat.\n---\n",
            encoding="utf-8",
        )
        try:
            update(source, wrong_target, root / "wrong-backup", False)
        except UpdateError:
            pass
        else:
            raise UpdateError("update accepted an unowned destination")

        poisoned_target = root / "poisoned-skills"
        poisoned_target.mkdir()
        for skill in skill_directories(source):
            copy_skill(skill, poisoned_target / skill.name)
        write_json(
            poisoned_target / INVENTORY_NAME,
            {"plugin": "patpat", "schema": SCHEMA, "skills": {"../outside": {}}},
        )
        try:
            update(source, poisoned_target, root / "poisoned-backup", False)
        except UpdateError:
            pass
        else:
            raise UpdateError("update accepted a path-traversing inventory marker")

        linked_target = root / "linked-target"
        linked_target.symlink_to(target, target_is_directory=True)
        try:
            update(source, linked_target, root / "linked-target-backup", False)
        except UpdateError:
            pass
        else:
            raise UpdateError("update accepted a symlink target root")

        link_target = root / "link-skills"
        link_target.mkdir()
        alpha = source / "patpat-alpha"
        (link_target / alpha.name).symlink_to(alpha, target_is_directory=True)
        update(source, link_target, root / "link-backup", False)
        if not (link_target / "patpat-gamma").is_symlink():
            raise UpdateError("symlink update did not add a new skill")
        if (root / "link-backup").exists():
            raise UpdateError("symlink no-op created a backup")

    print("Patpat skill updater self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, help="Explicit existing agent skills directory.")
    parser.add_argument("--backup", type=Path, help="Explicit new backup directory on the target filesystem.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return 0
    if args.target is None or args.backup is None:
        parser.error("--target and --backup are required unless --self-test is used")

    root = Path(__file__).resolve().parents[1]
    errors = validate_root(root)
    if errors:
        print("Refusing to update from an invalid Patpat source:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    try:
        update(root / "skills", args.target.expanduser(), args.backup.expanduser(), args.dry_run)
    except UpdateError as error:
        print(f"Patpat skill update refused: {error}", file=sys.stderr)
        return 2
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as error:
        print(f"Patpat skill update failed after rollback: {error}", file=sys.stderr)
        return 3
    if args.dry_run:
        print("Patpat skill update dry-run passed; no files changed.")
    else:
        print("Patpat skill update completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
