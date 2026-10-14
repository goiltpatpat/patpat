#!/usr/bin/env python3
"""Verify the shape and freshness of a Patpat workspace context graph."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


GRAPH_RELATIVE = ".patpat/context-graph.json"
ENTITY_GROUPS = ("entrypoints", "services", "databases", "test_runners", "build_scripts")
SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
MAX_GRAPH_BYTES = 32 * 1024
MAX_PATH_CHARS = 1024
MAX_EVIDENCE_PATHS = 80
MAX_ENTRIES_PER_GROUP = 40
MAX_UNKNOWNS = 20
MAX_UNKNOWN_CHARS = 240
MAX_COMMAND_CHARS = 512


class GraphError(ValueError):
    """The graph cannot establish a current workspace map."""


def relative_parts(value: Any) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise GraphError(f"path must be a nonempty workspace-relative POSIX path: {value!r}")
    if len(value) > MAX_PATH_CHARS:
        raise GraphError(f"path exceeds the {MAX_PATH_CHARS}-character limit")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise GraphError(f"absolute path is not allowed: {value!r}")
    parts = tuple(value.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise GraphError(f"path contains an unsafe component: {value!r}")
    if any(any(ord(character) < 32 for character in part) for part in parts):
        raise GraphError(f"path contains a control character: {value!r}")
    return parts


def is_link_or_reparse_point(path: Path, metadata: os.stat_result) -> bool:
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    is_junction = getattr(path, "is_junction", lambda: False)()
    return stat.S_ISLNK(metadata.st_mode) or bool(
        os.name == "nt" and getattr(metadata, "st_file_attributes", 0) & reparse_flag
    ) or is_junction


def checked_file(root: Path, value: Any) -> Path:
    parts = relative_parts(value)
    candidate = root
    for part in parts:
        candidate = candidate / part
        try:
            metadata = candidate.lstat()
        except OSError as error:
            raise GraphError(f"referenced path is unavailable: {value!r}: {error}") from error
        if is_link_or_reparse_point(candidate, metadata):
            raise GraphError(f"symlink or reparse path is not allowed: {value!r}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise GraphError(f"referenced path escapes the workspace: {value!r}") from error
    if not resolved.is_file():
        raise GraphError(f"referenced path is not a regular file: {value!r}")
    return resolved


def git_output(repository: Path, *arguments: str) -> bytes:
    environment = os.environ.copy()
    environment["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=", "-C", str(repository), *arguments],
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as error:
        raise GraphError(f"cannot run Git: {error}") from error
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise GraphError(f"Git {' '.join(arguments)} failed: {detail or result.returncode}")
    return result.stdout


def verify_git_snapshot(root: Path, source: dict[str, Any], referenced_paths: set[str]) -> None:
    repository = Path(os.fsdecode(git_output(root, "rev-parse", "--show-toplevel")).strip()).resolve()
    try:
        workspace_prefix = root.relative_to(repository).as_posix()
    except ValueError as error:
        raise GraphError("workspace root is outside the Git repository") from error

    revision = os.fsdecode(git_output(repository, "rev-parse", "--verify", "HEAD")).strip()
    if not SHA_PATTERN.fullmatch(revision) or source["revision"] != revision:
        raise GraphError("graph revision does not match the current Git HEAD")
    if source["worktree"] != "clean":
        raise GraphError("graph was not recorded from a clean Git worktree")

    status = git_output(repository, "status", "--porcelain=v1", "--untracked-files=all", "-z")
    allowed_graph = f"{workspace_prefix + '/' if workspace_prefix != '.' else ''}{GRAPH_RELATIVE}".encode()
    for record in status.split(b"\0"):
        if not record:
            continue
        if record[:2] == b"??" and record[3:] == allowed_graph:
            continue
        raise GraphError("Git worktree is dirty; only the generated graph itself may be untracked")

    for relative in sorted(referenced_paths):
        git_relative = f"{workspace_prefix}/{relative}" if workspace_prefix != "." else relative
        indexed = git_output(repository, "ls-files", "-v", "-z", "--", git_relative)
        if indexed != b"H " + os.fsencode(git_relative) + b"\0":
            raise GraphError(
                f"referenced path has assume-unchanged or skip-worktree index flags: {relative!r}"
            )


def verify(root_argument: str) -> None:
    try:
        root = Path(root_argument).expanduser().resolve(strict=True)
    except OSError as error:
        raise GraphError(f"workspace root is unavailable: {error}") from error
    if not root.is_dir():
        raise GraphError("workspace root is not a directory")

    graph_directory = root / ".patpat"
    graph_path = root / GRAPH_RELATIVE
    for path in (graph_directory, graph_path):
        try:
            metadata = path.lstat()
        except OSError as error:
            raise GraphError(f"graph path is unavailable: {error}") from error
        if is_link_or_reparse_point(path, metadata):
            raise GraphError(f"graph path must not contain symlinks or reparse points: {path.name}")
    if not graph_directory.is_dir() or not graph_path.is_file():
        raise GraphError("expected a regular .patpat/context-graph.json file")
    if graph_path.stat().st_nlink != 1:
        raise GraphError("graph file must not be a hard link")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(graph_path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            metadata = os.fstat(handle.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise GraphError("graph file must be a regular file with one link")
            if metadata.st_size > MAX_GRAPH_BYTES:
                raise GraphError("graph exceeds the 32 KiB size limit")
            payload = handle.read(MAX_GRAPH_BYTES + 1)
        if len(payload) > MAX_GRAPH_BYTES:
            raise GraphError("graph exceeds the 32 KiB size limit")
        graph = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GraphError(f"graph is not valid UTF-8 JSON: {error}") from error
    if not isinstance(graph, dict) or set(graph) != {"schema_version", "source", "entities", "unknowns"}:
        raise GraphError("graph has an unexpected top-level shape")
    if type(graph["schema_version"]) is not int or graph["schema_version"] != 1:
        raise GraphError("schema_version must be integer 1")

    source = graph["source"]
    if not isinstance(source, dict) or set(source) != {"revision", "worktree", "evidence_paths"}:
        raise GraphError("source must contain revision, worktree, and evidence_paths only")
    if not isinstance(source["worktree"], str) or source["worktree"] not in {
        "clean",
        "dirty",
        "unknown",
    }:
        raise GraphError("source.worktree must be clean, dirty, or unknown")
    if source["revision"] is not None and (
        not isinstance(source["revision"], str) or not SHA_PATTERN.fullmatch(source["revision"])
    ):
        raise GraphError("source.revision must be a full Git SHA or null")
    if (
        not isinstance(source["evidence_paths"], list)
        or len(source["evidence_paths"]) > MAX_EVIDENCE_PATHS
        or any(not isinstance(value, str) for value in source["evidence_paths"])
    ):
        raise GraphError(f"source.evidence_paths must be a list of at most {MAX_EVIDENCE_PATHS} relative paths")
    if len(source["evidence_paths"]) != len(set(source["evidence_paths"])):
        raise GraphError("source.evidence_paths must not contain duplicates")

    entities = graph["entities"]
    if not isinstance(entities, dict) or set(entities) != set(ENTITY_GROUPS):
        raise GraphError("entities must contain the five documented categories")
    if not isinstance(graph["unknowns"], list) or len(graph["unknowns"]) > MAX_UNKNOWNS or any(
        not isinstance(value, str)
        or "\n" in value
        or "\r" in value
        or len(value) > MAX_UNKNOWN_CHARS
        for value in graph["unknowns"]
    ):
        raise GraphError(
            f"unknowns must contain at most {MAX_UNKNOWNS} single-line strings of at most {MAX_UNKNOWN_CHARS} characters"
        )

    evidence_paths = set(source["evidence_paths"])
    referenced_paths = set(evidence_paths)
    for path in evidence_paths:
        checked_file(root, path)
    for group in ENTITY_GROUPS:
        entries = entities[group]
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES_PER_GROUP:
            raise GraphError(f"entities.{group} must be a list of at most {MAX_ENTRIES_PER_GROUP} entries")
        for entry in entries:
            if not isinstance(entry, dict):
                raise GraphError(f"entities.{group} entries must be objects")
            required = {"path", "evidence_path", "evidence"}
            allowed = required | ({"command"} if group in {"test_runners", "build_scripts"} else set())
            if not required <= set(entry) or not set(entry) <= allowed:
                raise GraphError(f"entities.{group} entry has an unexpected shape")
            if not isinstance(entry["evidence"], str) or not entry["evidence"] or len(entry["evidence"]) > 160:
                raise GraphError(f"entities.{group} evidence must be a concise locator")
            if "\n" in entry["evidence"] or "\r" in entry["evidence"]:
                raise GraphError(f"entities.{group} evidence must be single-line")
            checked_file(root, entry["path"])
            checked_file(root, entry["evidence_path"])
            if entry["evidence_path"] not in evidence_paths:
                raise GraphError(f"entities.{group} evidence_path is missing from source.evidence_paths")
            referenced_paths.add(entry["path"])
            referenced_paths.add(entry["evidence_path"])
            if "command" in entry and entry["command"] is not None and (
                not isinstance(entry["command"], str)
                or not entry["command"]
                or len(entry["command"]) > MAX_COMMAND_CHARS
                or any(character in entry["command"] for character in "\r\n\0")
            ):
                raise GraphError(
                    f"entities.{group} command must be a single-line string of at most {MAX_COMMAND_CHARS} characters or null"
                )

    verify_git_snapshot(root, source, referenced_paths)


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] != "--root":
        print("usage: verify_context_graph.py --root WORKSPACE", file=sys.stderr)
        return 2
    try:
        verify(sys.argv[2])
    except GraphError as error:
        print(f"workspace-map-current: not established: {error}", file=sys.stderr)
        return 1
    print("workspace-map-current: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
