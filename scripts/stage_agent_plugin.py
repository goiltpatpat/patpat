#!/usr/bin/env python3
"""Stage Patpat as a portable Agent Plugins 1.0 package."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from stage_plugin import (
    StageError,
    copy_entry,
    file_inventory,
    paths_overlap,
    reject_link_entries,
    stage as stage_native_plugin,
)
from validate import (
    AGENT_PLUGIN_FIELDS,
    AGENT_PLUGIN_SCHEMA,
    validate_agent_plugin_package,
    validate_root,
)


AGENT_METADATA_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)
IGNORED_SKILL_PATH_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def build_manifest(source: Path) -> dict[str, object]:
    codex_manifest_path = source / ".codex-plugin" / "plugin.json"
    try:
        codex_manifest = json.loads(codex_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise StageError(f"cannot read canonical Codex metadata: {error}") from error
    if not isinstance(codex_manifest, dict):
        raise StageError("canonical Codex metadata must be a JSON object")

    manifest: dict[str, object] = {"$schema": AGENT_PLUGIN_SCHEMA}
    for field in AGENT_METADATA_FIELDS:
        if field in codex_manifest:
            manifest[field] = codex_manifest[field]
    return manifest


def git_skill_files(source: Path) -> list[Path] | None:
    """Return tracked and non-ignored skill files for a Git-backed source tree."""
    try:
        repository = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if (
        repository.returncode != 0
        or Path(repository.stdout.strip()).resolve() != source.resolve()
    ):
        return None

    result = subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "skills/",
        ],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace")
        raise StageError(f"cannot inventory Git-backed skill files: {detail}")
    return [Path(os.fsdecode(raw)) for raw in result.stdout.split(b"\0") if raw]


def copy_skills(source: Path, destination: Path) -> None:
    """Copy skills, excluding Git-ignored local files when Git metadata exists."""
    skill_root = source / "skills"
    reject_link_entries(skill_root, package_root=source)
    files = git_skill_files(source)
    if files is None:
        copy_entry(skill_root, destination, package_root=source)
        return

    destination.mkdir(parents=True)
    for relative in files:
        if not relative.parts or relative.parts[0] != "skills":
            raise StageError(f"Git returned a path outside skills/: {relative}")
        if (
            any(part in IGNORED_SKILL_PATH_PARTS for part in relative.parts)
            or relative.suffix.lower() in {".pyc", ".pyo"}
        ):
            continue
        original = source / relative
        if not original.exists():
            continue
        target = destination.joinpath(*relative.parts[1:])
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_entry(original, target, package_root=source)


def stage(source: Path, target: Path) -> dict[str, str]:
    requested_target = target.expanduser()
    if requested_target.exists() or requested_target.is_symlink():
        raise StageError(f"stage target already exists: {requested_target}")

    source = source.resolve()
    target = requested_target.resolve()
    if paths_overlap(source, target):
        raise StageError("stage target must not overlap the source repository")
    if target.exists() or target.is_symlink():
        raise StageError(f"stage target already exists: {target}")

    errors = validate_root(source)
    if errors:
        raise StageError(f"source validation failed: {'; '.join(errors)}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    )
    try:
        copy_entry(source / "LICENSE", temporary / "LICENSE", package_root=source)
        copy_skills(source, temporary / "skills")

        (temporary / "plugin.json").write_text(
            json.dumps(build_manifest(source), indent=2) + "\n",
            encoding="utf-8",
        )
        staged_errors = validate_agent_plugin_package(temporary)
        if staged_errors:
            raise StageError(
                f"staged Agent Plugins package validation failed: {'; '.join(staged_errors)}"
            )

        inventory = file_inventory(temporary)
        if target.exists() or target.is_symlink():
            raise StageError(f"stage target already exists: {target}")
        os.replace(temporary, target)
        return inventory
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def skill_files(root: Path) -> dict[str, str]:
    prefix = "skills/"
    return {
        path: digest
        for path, digest in file_inventory(root).items()
        if path.startswith(prefix)
    }


def run_self_test(source: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="patpat-agent-plugin-test-") as directory:
        root = Path(directory)
        package_source = root / "source"
        package_target = root / "agent-plugin"
        stage_native_plugin(source, package_source)

        (package_source / "memory-bank").mkdir()
        (package_source / "memory-bank" / "local.md").write_text(
            "local context\n", encoding="utf-8"
        )
        (package_source / "docs" / "diagrams").mkdir()
        (package_source / "docs" / "diagrams" / "local.html").write_text(
            "local render\n", encoding="utf-8"
        )
        (package_source / "scripts" / "__pycache__").mkdir()
        (package_source / "scripts" / "__pycache__" / "local.pyc").write_bytes(
            b"local bytecode"
        )
        (package_source / ".agents" / "skills" / "local-skill").mkdir(parents=True)
        (package_source / ".agents" / "skills" / "local-skill" / "SKILL.md").write_text(
            "local skill\n", encoding="utf-8"
        )

        expected_skill_files = skill_files(package_source)
        expected_skill_names = {
            skill.name
            for skill in (package_source / "skills").iterdir()
            if skill.is_dir() and (skill / "SKILL.md").is_file()
        }

        git_init = subprocess.run(
            ["git", "init", "--quiet"],
            cwd=package_source,
            check=False,
            capture_output=True,
            text=True,
        )
        if git_init.returncode != 0:
            raise StageError(f"self-test could not initialize Git fixture: {git_init.stderr}")
        git_add = subprocess.run(
            ["git", "add", "--all", "--force", "--", ".gitignore", "LICENSE", "skills"],
            cwd=package_source,
            check=False,
            capture_output=True,
            text=True,
        )
        if git_add.returncode != 0:
            raise StageError(f"self-test could not index canonical skill files: {git_add.stderr}")
        ignored_skill_file = package_source / "skills" / "patpat-setup" / "local.jsonl"
        ignored_skill_file.write_text("local evaluation receipt\n", encoding="utf-8")
        ignore_check = subprocess.run(
            ["git", "check-ignore", "--quiet", "skills/patpat-setup/local.jsonl"],
            cwd=package_source,
            check=False,
        )
        if ignore_check.returncode != 0:
            raise StageError("self-test fixture file is not covered by the repository ignore rules")
        source_before_stage = file_inventory(package_source)
        inventory = stage(package_source, package_target)
        if file_inventory(package_source) != source_before_stage:
            raise StageError("self-test modified its source package while staging")
        generated = json.loads((package_target / "plugin.json").read_text(encoding="utf-8"))
        codex_manifest = json.loads(
            (package_source / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        expected_manifest: dict[str, object] = {"$schema": AGENT_PLUGIN_SCHEMA}
        expected_manifest.update(
            {
                field: codex_manifest[field]
                for field in AGENT_METADATA_FIELDS
                if field in codex_manifest
            }
        )
        if generated != expected_manifest:
            raise StageError("self-test output does not preserve canonical Patpat metadata")
        if (
            set(generated) - AGENT_PLUGIN_FIELDS
            or not {"$schema", "name"}.issubset(generated)
        ):
            raise StageError("self-test output does not use the closed Agent Plugins manifest fields")
        if generated.get("$schema") != AGENT_PLUGIN_SCHEMA or generated.get("name") != "patpat":
            raise StageError("self-test output has an unexpected Agent Plugins schema or name")
        if "interface" in generated or "skills" in generated or "hooks" in generated:
            raise StageError("self-test output contains host-specific or unsupported root fields")
        if inventory != file_inventory(package_target):
            raise StageError("self-test package changed after atomic promotion")
        if skill_files(package_target) != expected_skill_files:
            raise StageError("self-test package did not preserve skill files and resources")
        if (package_target / "skills" / "patpat-setup" / "local.jsonl").exists():
            raise StageError("self-test package included a Git-ignored local skill artifact")
        actual_skill_names = {
            skill.name
            for skill in (package_target / "skills").iterdir()
            if skill.is_dir() and (skill / "SKILL.md").is_file()
        }
        if actual_skill_names != expected_skill_names:
            raise StageError("self-test package changed the discovered skill set")
        if (
            (package_target / "memory-bank").exists()
            or (package_target / "docs" / "diagrams").exists()
            or (package_target / "scripts" / "__pycache__").exists()
            or (package_target / ".agents" / "skills").exists()
        ):
            raise StageError("self-test package included local artifacts")
        if any(path.is_symlink() for path in package_target.rglob("*")):
            raise StageError("self-test package contains a symlink")

        package_errors = validate_agent_plugin_package(package_target)
        if package_errors:
            raise StageError(
                f"self-test package has unresolved skill links or invalid resources: {'; '.join(package_errors)}"
            )

        extra_root_file = package_target / "unexpected.txt"
        extra_root_file.write_text("unexpected package entry\n", encoding="utf-8")
        extra_root_errors = validate_agent_plugin_package(package_target)
        extra_root_file.unlink()
        if not any("must contain exactly" in error for error in extra_root_errors):
            raise StageError("self-test validator accepted an extra Agent Plugins package entry")

        marker = package_target / "keep.txt"
        marker.write_text("existing target\n", encoding="utf-8")
        before_refusal = file_inventory(package_target)
        try:
            stage(package_source, package_target)
        except StageError:
            pass
        else:
            raise StageError("self-test overwrote an existing target")
        if file_inventory(package_target) != before_refusal:
            raise StageError("self-test modified an existing target after refusing it")

        overlap_target = package_source / "nested-target"
        try:
            stage(package_source, overlap_target)
        except StageError as error:
            if "overlap" not in str(error):
                raise StageError("self-test rejected source-target overlap for the wrong reason")
        else:
            raise StageError("self-test accepted a target nested under its source")
        if overlap_target.exists():
            raise StageError("self-test created an overlapping output")

        symlink_source = root / "symlink-source"
        shutil.copytree(package_source, symlink_source)
        symlink_path = symlink_source / "skills" / "patpat-setup" / "local-link.md"
        try:
            symlink_path.symlink_to(symlink_source / "skills" / "patpat-setup" / "SKILL.md")
        except (NotImplementedError, OSError) as error:
            if os.name != "nt":
                raise StageError(f"self-test cannot create a symlink fixture: {error}") from error
        else:
            symlink_target = root / "symlink-output"
            try:
                stage(symlink_source, symlink_target)
            except StageError as error:
                if "symlink" not in str(error).lower():
                    raise StageError("self-test refused the symlink fixture for the wrong reason")
            else:
                raise StageError("self-test accepted a package source symlink")
            if symlink_target.exists() or any(root.glob(".symlink-output.*.tmp")):
                raise StageError("self-test left output or a temporary directory after symlink refusal")

        print(
            "Patpat Agent Plugins staging self-test passed: "
            f"{len(actual_skill_names)} skills, links/resources, package boundary, and refusal cases."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[1]
    if args.self_test:
        run_self_test(source)
        return 0
    if args.target is None:
        parser.error("--target is required unless --self-test is used")
    if git_skill_files(source) is None:
        print(
            "Warning: source is not a Git worktree; inspect the staged skills for ignored local files.",
            file=sys.stderr,
        )
    inventory = stage(source, args.target)
    print(f"Staged {len(inventory)} files into {args.target.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except StageError as error:
        print(f"Agent Plugins staging failed: {error}", file=sys.stderr)
        raise SystemExit(1)
