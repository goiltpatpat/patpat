#!/usr/bin/env python3
"""Stage an allowlisted Patpat distribution without local state or diagram artifacts."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
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
IGNORED_PACKAGE_PATHS = {"docs/diagrams"}


class StageError(RuntimeError):
    """Raised when a distribution cannot be staged safely."""


def paths_overlap(source: Path, target: Path) -> bool:
    source = source.resolve()
    target = target.resolve()
    return target == source or source in target.parents or target in source.parents


def is_ignored_package_path(path: Path, package_root: Path) -> bool:
    try:
        relative = path.relative_to(package_root).as_posix().casefold()
    except ValueError:
        return False
    return any(
        relative == excluded.casefold()
        or relative.startswith(f"{excluded.casefold()}/")
        for excluded in IGNORED_PACKAGE_PATHS
    )


def link_entry_kind(path: Path) -> str | None:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise StageError(f"unable to inspect package source: {error}") from error

    if stat.S_ISLNK(metadata.st_mode):
        return "symlink"
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    if os.name == "nt" and getattr(metadata, "st_file_attributes", 0) & reparse_flag:
        return "Windows reparse point"
    return None


def reject_link_entries(path: Path, *, package_root: Path) -> None:
    kind = link_entry_kind(path)
    if kind:
        raise StageError(f"package source contains a {kind}: {path}")
    if not path.is_dir():
        return

    def raise_walk_error(error: OSError) -> None:
        raise StageError(f"unable to inspect package source: {error}") from error

    for directory, dirnames, filenames in os.walk(
        path,
        topdown=True,
        onerror=raise_walk_error,
    ):
        current = Path(directory)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if not is_ignored_package_path(current / name, package_root)
        )
        filenames[:] = sorted(
            name
            for name in filenames
            if not is_ignored_package_path(current / name, package_root)
        )
        for name in (*dirnames, *filenames):
            candidate = current / name
            kind = link_entry_kind(candidate)
            if kind:
                raise StageError(f"package source contains a {kind}: {candidate}")


def copy_entry(source: Path, destination: Path, *, package_root: Path) -> None:
    package_root = package_root.resolve()
    reject_link_entries(source, package_root=package_root)
    if source.is_dir():
        pattern_ignore = shutil.ignore_patterns(*IGNORED_NAMES, "*.pyc", "*.pyo")

        def ignore(directory: str, names: list[str]) -> list[str]:
            ignored = set(pattern_ignore(directory, names))
            ignored.update(
                name for name in names
                if is_ignored_package_path(Path(directory) / name, package_root)
            )
            return sorted(ignored)

        shutil.copytree(source, destination, ignore=ignore)
    elif source.is_file():
        shutil.copy2(source, destination)
    else:
        raise StageError(f"missing package entry: {source}")


def file_inventory(root: Path) -> dict[str, str]:
    inventory: dict[str, str] = {}

    kind = link_entry_kind(root)
    if kind:
        raise StageError(f"staged artifact contains a {kind}: {root}")

    def raise_walk_error(error: OSError) -> None:
        raise StageError(f"unable to inspect staged artifact: {error}") from error

    for directory, dirnames, filenames in os.walk(
        root,
        topdown=True,
        onerror=raise_walk_error,
    ):
        current = Path(directory)
        dirnames[:] = sorted(dirnames)
        for name in (*dirnames, *sorted(filenames)):
            path = current / name
            kind = link_entry_kind(path)
            if kind:
                raise StageError(f"staged artifact contains a {kind}: {path}")
            if path.is_file():
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
            copy_entry(source / relative, temporary / relative, package_root=source)
        if (temporary / "memory-bank").exists():
            raise StageError("local Memory Bank entered the staged artifact")
        if (temporary / "docs" / "diagrams").exists():
            raise StageError("local docs/diagrams artifacts entered the staged package")
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
    def expect_copy_refusal(
        candidate: Path,
        destination: Path,
        *,
        package_root: Path,
        expected_kind: str,
    ) -> None:
        try:
            copy_entry(candidate, destination, package_root=package_root)
        except StageError as error:
            if expected_kind not in str(error).lower():
                raise StageError(
                    f"stage self-test refused {expected_kind} for the wrong reason: {error}"
                ) from error
        else:
            raise StageError(f"stage self-test copied a {expected_kind} package source")
        if destination.exists():
            raise StageError(f"stage self-test created output after refusing a {expected_kind}")

    def expect_inventory_refusal(candidate: Path, *, expected_kind: str) -> None:
        try:
            file_inventory(candidate)
        except StageError as error:
            if expected_kind not in str(error).lower():
                raise StageError(
                    f"stage self-test inventory refused {expected_kind} for the wrong reason: {error}"
                ) from error
        else:
            raise StageError(f"stage self-test inventory accepted a {expected_kind}")

    def create_windows_junction(link: Path, target: Path) -> bool:
        if os.name != "nt" or not hasattr(os.stat_result, "st_file_attributes"):
            return False
        command = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if command is None:
            return False
        environment = os.environ.copy()
        environment["PATPAT_TEST_JUNCTION_LINK"] = str(link)
        environment["PATPAT_TEST_JUNCTION_TARGET"] = str(target)
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
        if result.returncode != 0 or not link.exists():
            raise StageError(
                "stage self-test could not create a Windows junction fixture: "
                f"{result.stdout}{result.stderr}"
            )
        if link_entry_kind(link) != "Windows reparse point":
            raise StageError("stage self-test junction fixture is not reported as a reparse point")
        return True

    with tempfile.TemporaryDirectory(prefix="patpat-stage-filter-test-") as directory:
        root = Path(directory)
        package_root = (root / "source").resolve()
        docs = package_root / "docs"
        (docs / "guide").mkdir(parents=True)
        (docs / "Diagrams").mkdir()
        (docs / "guide" / "installing.md").write_text("install guide\n", encoding="utf-8")
        (docs / "Diagrams" / "local.html").write_text("local render\n", encoding="utf-8")
        (docs / "diagrams-reference").mkdir()
        (docs / "diagrams-reference" / "guide.md").write_text("reference\n", encoding="utf-8")
        copied_docs = root / "distribution" / "docs"
        copy_entry(docs, copied_docs, package_root=package_root)
        if (
            (copied_docs / "Diagrams").exists()
            or not (copied_docs / "guide" / "installing.md").is_file()
            or not (copied_docs / "diagrams-reference" / "guide.md").is_file()
        ):
            raise StageError("stage self-test did not exclude diagram artifacts while preserving package docs")

    with tempfile.TemporaryDirectory(prefix="patpat-stage-links-test-") as directory:
        root = Path(directory)
        package_root = root / "source"
        nested = package_root / "nested"
        nested.mkdir(parents=True)
        outside = root / "outside"
        outside.mkdir()
        outside_file = outside / "payload.txt"
        outside_file.write_text("outside package root\n", encoding="utf-8")

        symlink = nested / "outside-link.txt"
        try:
            symlink.symlink_to(outside_file)
        except (NotImplementedError, OSError) as error:
            if os.name != "nt":
                raise StageError(f"stage self-test cannot create a symlink fixture: {error}") from error
        else:
            expect_copy_refusal(
                package_root,
                root / "symlink-descendant-output",
                package_root=package_root,
                expected_kind="symlink",
            )
            expect_inventory_refusal(package_root, expected_kind="symlink")

            root_symlink = root / "source-link"
            try:
                root_symlink.symlink_to(package_root, target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                if os.name != "nt":
                    raise StageError(
                        f"stage self-test cannot create a root symlink fixture: {error}"
                    ) from error
            else:
                expect_copy_refusal(
                    root_symlink,
                    root / "symlink-root-output",
                    package_root=package_root,
                    expected_kind="symlink",
                )
                expect_inventory_refusal(root_symlink, expected_kind="symlink")

        if os.name == "nt" and hasattr(os.stat_result, "st_file_attributes"):
            junction_target = root / "junction target โปรเจกต์"
            junction_target.mkdir()
            (junction_target / "payload.txt").write_text("outside package root\n", encoding="utf-8")

            junction_source = root / "junction source"
            junction_source.mkdir()
            if create_windows_junction(junction_source / "outside link", junction_target):
                expect_copy_refusal(
                    junction_source,
                    root / "junction-descendant-output",
                    package_root=junction_source,
                    expected_kind="reparse point",
                )
                expect_inventory_refusal(junction_source, expected_kind="reparse point")

                junction_root = root / "junction root"
                if create_windows_junction(junction_root, junction_target):
                    expect_copy_refusal(
                        junction_root,
                        root / "junction-root-output",
                        package_root=root,
                        expected_kind="reparse point",
                    )
                    expect_inventory_refusal(junction_root, expected_kind="reparse point")

    with tempfile.TemporaryDirectory(prefix="patpat-stage-test-") as directory:
        root = Path(directory)
        target = root / "patpat-dist"
        inventory = stage(source, target)
        if not inventory or (target / "memory-bank").exists() or (target / "docs" / "diagrams").exists():
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
