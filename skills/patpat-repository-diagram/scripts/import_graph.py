#!/usr/bin/env python3
"""Build an evidence-backed Patpat diagram from resolvable Python imports."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
import time
import tokenize
from typing import Any
from unittest.mock import patch

from model import (
    MAX_EDGES,
    MAX_EVIDENCE,
    MAX_NODES,
    MAX_SOURCE_JSON_BYTES,
    DiagramError,
    git_context,
    validate_spec,
)
from render import _make_layout


TOOL = "patpat-repository-diagram/python-import-graph"
MAX_FILE_BYTES = 1_000_000
MAX_SOURCE_LIST_BYTES = 8_000_000
MAX_SOURCE_FILES = 10_000
MAX_TOTAL_SOURCE_BYTES = 64_000_000
MAX_IMPORT_FACTS = 25_000
EXCLUDED_DIRECTORY_NAMES = {
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
    "venv",
}
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class ImportFact:
    source: str
    line: int
    end_line: int
    column: int
    kind: str
    specifier: str | None
    relative_level: int = 0
    relative_package: str | None = None
    status: str = "unresolved"
    target: str | None = None
    reason: str | None = None
    evidence_id: str | None = None


def _stable_id(prefix: str, *parts: str) -> str:
    value = "\0".join(parts).encode("utf-8", errors="strict")
    return prefix + hashlib.sha256(value).hexdigest()[:20]


def _consume_budget(current: int, amount: int, maximum: int, resource: str) -> int:
    if amount < 0 or current > maximum - amount:
        raise DiagramError(f"repository analysis resource limit exceeded: {resource} is above {maximum}")
    return current + amount


def _normal_relpath(value: str, name: str) -> str:
    if value == ".":
        return value
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or "\\" in value
        or re.match(r"^[A-Za-z]:", value)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise DiagramError(f"{name} must be a normalized repository-relative path")
    return value


def _within_scope(path: str, scope: str) -> bool:
    if scope == ".":
        return True
    return path == scope or path.startswith(scope + "/")


def _module_for_path(path: str, root: str) -> str | None:
    relative = PurePosixPath(path)
    if root != ".":
        try:
            relative = relative.relative_to(PurePosixPath(root))
        except ValueError:
            return None
    parts = list(relative.parts)
    if not parts or not parts[-1].endswith(".py"):
        return None
    if parts[-1] == "__init__.py":
        parts.pop()
    else:
        parts[-1] = parts[-1][:-3]
    if not parts or not all(part.isidentifier() for part in parts):
        return None
    return ".".join(parts)


def _package_for_path(path: str, roots: list[str]) -> str:
    candidates = [root for root in roots if _module_for_path(path, root) is not None or _within_scope(path, root)]
    if not candidates:
        return ""
    root = max(candidates, key=lambda item: len(PurePosixPath(item).parts))
    module = _module_for_path(path, root)
    if module is None:
        return ""
    if PurePosixPath(path).name == "__init__.py":
        return module
    return module.rpartition(".")[0]


def _valid_module_name(value: str) -> bool:
    stripped = value.lstrip(".")
    if not stripped:
        return value.startswith(".")
    return all(part.isidentifier() for part in stripped.split("."))


def _call_name(
    call: ast.Call,
    module_aliases: set[str],
    loader_aliases: set[str],
    shadowed: set[str],
) -> str | None:
    function = call.func
    if isinstance(function, ast.Name):
        if function.id == "__import__" and function.id not in shadowed:
            return "__import__"
        if function.id in loader_aliases:
            return "importlib.import_module"
    if (
        isinstance(function, ast.Attribute)
        and function.attr == "import_module"
        and isinstance(function.value, ast.Name)
        and function.value.id in module_aliases
    ):
        return "importlib.import_module"
    return None


def _dynamic_aliases(tree: ast.Module) -> tuple[set[str], set[str], set[str]]:
    module_aliases: set[str] = set()
    loader_aliases: set[str] = set()
    shadowed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    module_aliases.add(alias.asname or "importlib")
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    loader_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            shadowed.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            shadowed.add(node.name)
            shadowed.update(arg.arg for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
            if node.args.vararg:
                shadowed.add(node.args.vararg.arg)
            if node.args.kwarg:
                shadowed.add(node.args.kwarg.arg)
        elif isinstance(node, ast.ClassDef):
            shadowed.add(node.name)
    return module_aliases - shadowed, loader_aliases - shadowed, shadowed


def _literal_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_imports(
    source: str,
    path: str,
    max_facts: int = MAX_IMPORT_FACTS,
) -> tuple[list[ImportFact], str | None]:
    try:
        tree = ast.parse(source, filename=path)
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return [], "syntax-error"

    raw: list[ImportFact] = []

    def add(item: ImportFact) -> None:
        _consume_budget(len(raw), 1, max_facts, "import facts")
        raw.append(item)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                add(
                    ImportFact(
                        path,
                        node.lineno,
                        node.lineno,
                        getattr(alias, "col_offset", node.col_offset),
                        "import",
                        alias.name,
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            specifier = "." * node.level + (node.module or "")
            add(
                ImportFact(
                    path,
                    node.lineno,
                    node.lineno,
                    node.col_offset,
                    "from-import",
                    specifier,
                    relative_level=node.level,
                )
            )

    module_aliases, loader_aliases, shadowed = _dynamic_aliases(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        looks_like_loader = (
            isinstance(function, ast.Name) and function.id == "__import__"
        ) or (
            isinstance(function, ast.Attribute) and function.attr == "import_module"
        )
        loader = _call_name(node, module_aliases, loader_aliases, shadowed)
        if loader is None:
            if looks_like_loader:
                add(
                    ImportFact(
                        path,
                        node.lineno,
                        getattr(node, "end_lineno", node.lineno) or node.lineno,
                        node.col_offset,
                        "dynamic-import",
                        None,
                        reason="dynamic-loader-unresolved",
                    )
                )
            continue

        argument = node.args[0] if node.args else None
        specifier = _literal_string(argument)
        package = None
        if loader == "importlib.import_module":
            package = next((_literal_string(item.value) for item in node.keywords if item.arg == "package"), None)
            if package is None and len(node.args) > 1:
                package = _literal_string(node.args[1])
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        if end_line - node.lineno > 60:
            add(
                ImportFact(
                    path,
                    node.lineno,
                    end_line,
                    node.col_offset,
                    "dynamic-import",
                    None,
                    reason="statement-too-long-for-evidence",
                )
            )
            continue
        if specifier is None:
            add(
                ImportFact(
                    path,
                    node.lineno,
                    end_line,
                    node.col_offset,
                    "dynamic-import",
                    None,
                    reason="dynamic-specifier-not-literal",
                )
            )
            continue
        dots = len(specifier) - len(specifier.lstrip("."))
        add(
            ImportFact(
                path,
                node.lineno,
                end_line,
                node.col_offset,
                "dynamic-import",
                specifier,
                relative_level=dots,
                relative_package=package if dots else None,
                reason=("relative-dynamic-import-needs-literal-package" if dots and not package else None),
            )
        )

    raw.sort(key=lambda item: (item.line, item.column, item.kind, item.specifier or "", item.reason or ""))
    occurrences: list[ImportFact] = []
    for index, item in enumerate(raw):
        evidence_id = _stable_id("E", item.source, str(item.line), str(item.column), item.kind, item.specifier or "", str(index))
        occurrences.append(ImportFact(**{**item.__dict__, "evidence_id": evidence_id}))
    return occurrences, None


def _relative_module(specifier: str, level: int, package: str) -> tuple[str | None, str | None]:
    if level <= 0:
        return specifier, None
    package_parts = package.split(".") if package else []
    climb = level - 1
    if climb > len(package_parts):
        return None, "relative-import-above-package-root"
    keep = len(package_parts) - climb
    module_part = specifier.lstrip(".")
    pieces = package_parts[:keep]
    if module_part:
        pieces.extend(module_part.split("."))
    if not pieces:
        return None, "relative-import-has-no-module-target"
    return ".".join(pieces), None


def _resolve_imports(
    facts: list[ImportFact],
    candidate_paths: set[str],
    parsed_paths: set[str],
    roots: list[str],
    scope: str,
) -> list[ImportFact]:
    index: dict[str, set[str]] = {}
    for path in sorted(candidate_paths):
        for root in roots:
            module = _module_for_path(path, root)
            if module:
                index.setdefault(module, set()).add(path)

    resolved: list[ImportFact] = []
    for item in facts:
        if item.reason:
            resolved.append(item)
            continue
        specifier = item.specifier
        if specifier is None or len(specifier) > 180:
            resolved.append(ImportFact(**{**item.__dict__, "specifier": None, "reason": "module-specifier-too-long-redacted"}))
            continue
        if not _valid_module_name(specifier):
            resolved.append(ImportFact(**{**item.__dict__, "specifier": None, "reason": "unsupported-module-specifier-redacted"}))
            continue
        if len(item.source) > 320:
            resolved.append(ImportFact(**{**item.__dict__, "specifier": None, "reason": "source-path-too-long-for-evidence"}))
            continue
        if item.relative_level and item.kind == "dynamic-import" and not item.relative_package:
            resolved.append(ImportFact(**{**item.__dict__, "reason": "relative-dynamic-import-needs-literal-package"}))
            continue
        package = item.relative_package if item.relative_package is not None else _package_for_path(item.source, roots)
        module, error = _relative_module(specifier, item.relative_level, package)
        if error or module is None:
            resolved.append(ImportFact(**{**item.__dict__, "reason": error or "unresolved-module"}))
            continue
        targets = index.get(module, set())
        if len(targets) > 1:
            resolved.append(ImportFact(**{**item.__dict__, "reason": "ambiguous-module-target"}))
            continue
        if not targets:
            top_level = module.split(".", 1)[0]
            status = "standard-library" if not item.relative_level and top_level in sys.stdlib_module_names else "external-or-unresolved"
            reason = "outside-repository-source-roots" if status == "external-or-unresolved" else None
            resolved.append(ImportFact(**{**item.__dict__, "status": status, "reason": reason}))
            continue
        target = next(iter(targets))
        if not _within_scope(target, scope):
            resolved.append(ImportFact(**{**item.__dict__, "reason": "target-outside-selected-scope"}))
            continue
        if target not in parsed_paths:
            resolved.append(ImportFact(**{**item.__dict__, "reason": "target-source-not-parsed"}))
            continue
        resolved.append(ImportFact(**{**item.__dict__, "status": "repository", "target": target}))
    return resolved


def _feedback_edges(paths: list[str], edges: list[tuple[str, str, str]]) -> set[str]:
    adjacency: dict[str, list[tuple[str, str]]] = {path: [] for path in paths}
    for source, target, edge_id in edges:
        adjacency[source].append((target, edge_id))
    for outgoing in adjacency.values():
        outgoing.sort()
    state: dict[str, int] = {path: 0 for path in paths}
    feedback: set[str] = set()

    for path in paths:
        if state[path] != 0:
            continue
        state[path] = 1
        stack: list[tuple[str, int]] = [(path, 0)]
        while stack:
            current, index = stack[-1]
            outgoing = adjacency[current]
            if index >= len(outgoing):
                state[current] = 2
                stack.pop()
                continue
            target, edge_id = outgoing[index]
            stack[-1] = (current, index + 1)
            if state[target] == 1:
                feedback.add(edge_id)
            elif state[target] == 0:
                state[target] = 1
                stack.append((target, 0))
    return feedback


def _display_path(path: str) -> str:
    if len(path) <= 180:
        return path
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:8]
    tail = f"…/{PurePosixPath(path).name} [{digest}]"
    return path[: 180 - len(tail) - 1] + "/" + tail


def _build_spec(facts: list[ImportFact], language: str) -> dict[str, Any] | None:
    grouped: dict[tuple[str, str], list[ImportFact]] = {}
    for item in facts:
        if item.status == "repository" and item.target is not None and item.evidence_id is not None:
            grouped.setdefault((item.source, item.target), []).append(item)
    if not grouped:
        return None

    used_paths = sorted({path for edge in grouped for path in edge})
    node_ids = {path: _stable_id("N", path) for path in used_paths}
    edge_ids = {pair: _stable_id("R", *pair) for pair in grouped}
    edge_rows = sorted((source, target, edge_ids[(source, target)]) for source, target in grouped)
    feedback = _feedback_edges(used_paths, edge_rows)

    evidence: list[dict[str, Any]] = []
    for pair in sorted(grouped):
        for item in sorted(grouped[pair], key=lambda row: (row.source, row.line, row.column, row.specifier or "")):
            if item.specifier is None:
                continue
            if language == "th":
                claim = f"คำสั่ง Python {item.kind} ระบุการนำเข้าโมดูล {item.specifier}"
            else:
                claim = f"Python {item.kind} statement imports module {item.specifier}"
            evidence.append(
                {
                    "id": item.evidence_id,
                    "origin": "repository",
                    "path": item.source,
                    "start_line": item.line,
                    "end_line": item.end_line,
                    "claim": claim[:320],
                }
            )

    incident_evidence: dict[str, set[str]] = {path: set() for path in used_paths}
    relationships: list[dict[str, Any]] = []
    for pair in sorted(grouped):
        source, target = pair
        refs = grouped[pair]
        evidence_ids = sorted(item.evidence_id for item in refs if item.evidence_id)
        incident_evidence[source].update(evidence_ids)
        incident_evidence[target].update(evidence_ids)
        edge_id = edge_ids[pair]
        row: dict[str, Any] = {
            "id": edge_id,
            "source": node_ids[source],
            "target": node_ids[target],
            "label": "นำเข้า" if language == "th" else "imports",
            "kind": "depends_on",
            "certainty": "confirmed",
            "evidence_ids": evidence_ids,
        }
        if edge_id in feedback:
            row["feedback"] = True
        relationships.append(row)

    components = [
        {
            "id": node_ids[path],
            "label": _display_path(path),
            "kind": "component",
            "certainty": "confirmed",
            "evidence_ids": sorted(incident_evidence[path]),
        }
        for path in used_paths
    ]
    unresolved = sum(item.status not in {"repository", "standard-library"} for item in facts)
    if language == "th":
        title = "กราฟ import ของ Python"
        summary = (
            f"แสดงเฉพาะ import ที่ resolve ไปยังไฟล์ Python ในขอบเขตที่เลือกได้: "
            f"{len(components)} โมดูล, {len(relationships)} ความสัมพันธ์; "
            f"มี {unresolved} รายการที่ยัง resolve ไม่ได้ ดูรายงานประกอบ"
        )
    else:
        title = "Python import graph"
        summary = (
            f"Only imports resolved to Python files in the selected scope are drawn: "
            f"{len(components)} modules, {len(relationships)} relationships; "
            f"{unresolved} imports were unresolved or external candidates. See the sidecar report."
        )
    return {
        "schema_version": 2,
        "type": "architecture",
        "language": language,
        "title": title,
        "summary": summary,
        "layout": {"direction": "LR"},
        "evidence": evidence,
        "body": {"components": components, "relationships": relationships},
    }


def _prepare_layout(spec: dict[str, Any], repo_root: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    base_layout = _make_layout(validate_spec(spec, repo_root=repo_root))
    warnings = base_layout["warnings"]
    if not warnings:
        return spec, {"status": "passed", "adjustments": [], "warnings": []}

    layers = base_layout["layers"]
    layer_index = {identifier: index for index, layer in enumerate(layers) for identifier in layer}
    peer_index = {identifier: index for layer in layers for index, identifier in enumerate(layer)}
    positions = base_layout["positions"]
    labels = {item["id"]: item for item in base_layout["labels"]}

    def warning_mentions(warning: str, edge_id: str) -> bool:
        detail = warning.partition(": ")[2].partition(";")[0]
        return edge_id in detail.split("/")

    eligible: dict[str, dict[str, Any]] = {}
    for edge in spec["body"]["relationships"]:
        if edge.get("feedback"):
            continue
        source_rank = layer_index[edge["source"]]
        target_rank = layer_index[edge["target"]]
        if target_rank - source_rank <= 1:
            continue
        if peer_index[edge["source"]] != len(layers[source_rank]) - 1:
            continue
        if peer_index[edge["target"]] != len(layers[target_rank]) - 1:
            continue
        eligible[edge["id"]] = edge

    candidate_ids: set[str] = set()
    for warning in warnings:
        detail = warning.partition(": ")[2].partition(";")[0]
        if warning.startswith("edge crossing:"):
            crossing_ids = [identifier for identifier in detail.split("/") if identifier in eligible]
            if crossing_ids:
                candidate_ids.add(max(
                    crossing_ids,
                    key=lambda identifier: (
                        layer_index[eligible[identifier]["source"]],
                        peer_index[eligible[identifier]["source"]],
                        identifier,
                    ),
                ))
        else:
            candidate_ids.update(identifier for identifier in eligible if warning_mentions(warning, identifier))

    candidates = [eligible[identifier] for identifier in candidate_ids]

    candidates.sort(key=lambda edge: (layer_index[edge["source"]], peer_index[edge["source"]], edge["id"]))
    if candidates:
        node_bottom = max(rect["y"] + rect["h"] for rect in positions.values())
        lane_y = node_bottom + 28.0
        hints = spec["layout"].setdefault("edge_hints", {})
        adjustments = []
        for edge in candidates:
            label = labels[edge["id"]]
            lane_y += label["h"] / 2.0
            if lane_y + label["h"] / 2.0 + 8.0 > base_layout["height"]:
                break
            source = positions[edge["source"]]
            target = positions[edge["target"]]
            hints[edge["id"]] = {
                "source_side": "bottom",
                "target_side": "bottom",
                "waypoints": [
                    {"x": source["x"] + source["w"] / 2.0, "y": lane_y},
                    {"x": target["x"] + target["w"] / 2.0, "y": lane_y},
                ],
            }
            adjustments.append({"relationship": edge["id"], "route": "bottom clearance lane"})
            lane_y += label["h"] / 2.0 + 10.0
        if adjustments:
            final_layout = _make_layout(validate_spec(spec, repo_root=repo_root))
            return spec, {
                "status": "passed" if not final_layout["warnings"] else "blocked",
                "adjustments": adjustments,
                "warnings": final_layout["warnings"],
            }

    return spec, {"status": "blocked", "adjustments": [], "warnings": warnings}


def _tracked_python_paths(root: Path, max_paths: int | None = None) -> list[str]:
    command = ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    try:
        with TemporaryFile(mode="w+b") as listing_file:
            process = subprocess.Popen(command, stdout=listing_file, stderr=subprocess.DEVNULL)
            deadline = time.monotonic() + 20
            while process.poll() is None:
                if os.fstat(listing_file.fileno()).st_size > MAX_SOURCE_LIST_BYTES:
                    process.kill()
                    process.wait()
                    raise DiagramError(
                        f"repository analysis resource limit exceeded: Git source inventory exceeds {MAX_SOURCE_LIST_BYTES} bytes"
                    )
                if time.monotonic() >= deadline:
                    process.kill()
                    process.wait()
                    raise DiagramError("Git could not list repository source files")
                time.sleep(0.01)
            if process.returncode != 0:
                raise DiagramError("Git could not list repository source files")
            if os.fstat(listing_file.fileno()).st_size > MAX_SOURCE_LIST_BYTES:
                raise DiagramError(
                    f"repository analysis resource limit exceeded: Git source inventory exceeds {MAX_SOURCE_LIST_BYTES} bytes"
                )
            listing_file.seek(0)
            inventory = listing_file.read(MAX_SOURCE_LIST_BYTES + 1)
    except OSError as error:
        raise DiagramError("Git could not list repository source files") from error
    paths: set[str] = set()
    path_limit = MAX_SOURCE_FILES if max_paths is None else max_paths
    try:
        for raw in inventory.split(b"\0"):
            if not raw:
                continue
            relative = raw.decode("utf-8", errors="strict")
            if relative.endswith(".py"):
                normalized = _normal_relpath(relative, "Git source path")
                if normalized not in paths:
                    _consume_budget(len(paths), 1, path_limit, "Python source files")
                    paths.add(normalized)
    except UnicodeDecodeError as error:
        raise DiagramError("Git returned a non-UTF-8 source path") from error
    return sorted(paths)


def _read_python_file(path: Path, root: Path) -> tuple[str | None, str | None, str | None, int]:
    current = path
    while current != root:
        if current.is_symlink():
            return None, None, "symlink", 0
        current = current.parent
    try:
        if not path.resolve(strict=True).is_relative_to(root):
            return None, None, "outside-repository", 0
    except OSError:
        return None, None, "unreadable", 0
    if path.is_symlink():
        return None, None, "symlink", 0
    try:
        original_stat = path.lstat()
    except OSError:
        return None, None, "unreadable", 0
    if not stat.S_ISREG(original_stat.st_mode):
        return None, None, "not-regular-file", 0
    if original_stat.st_size > MAX_FILE_BYTES:
        return None, None, "too-large", 0
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None, None, "unreadable", 0
    try:
        with os.fdopen(descriptor, "rb") as source_file:
            opened_stat = os.fstat(source_file.fileno())
            if (
                not stat.S_ISREG(opened_stat.st_mode)
                or (opened_stat.st_dev, opened_stat.st_ino) != (original_stat.st_dev, original_stat.st_ino)
            ):
                return None, None, "source-changed-during-read", 0
            if opened_stat.st_size > MAX_FILE_BYTES:
                return None, None, "too-large", 0
            data = source_file.read(MAX_FILE_BYTES + 1)
            if len(data) != opened_stat.st_size:
                return None, None, "source-changed-during-read", len(data)
    except OSError:
        try:
            os.close(descriptor)
        except OSError:
            pass
        return None, None, "unreadable", 0
    if len(data) > MAX_FILE_BYTES:
        return None, None, "too-large", 0
    try:
        encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
        source = data.decode(encoding)
    except (SyntaxError, UnicodeError, LookupError):
        return None, hashlib.sha256(data).hexdigest(), "encoding-error", len(data)
    return source, hashlib.sha256(data).hexdigest(), None, len(data)


def _source_roots(root: Path, requested: list[str] | None) -> list[str]:
    if requested:
        values = requested
    else:
        values = ["."]
        if (root / "src").is_dir() and not (root / "src").is_symlink():
            values.append("src")
    roots: list[str] = []
    for value in values:
        relative = _normal_relpath(value, "--python-root")
        absolute = root if relative == "." else root.joinpath(*PurePosixPath(relative).parts)
        if absolute.is_symlink() or not absolute.is_dir() or not absolute.resolve().is_relative_to(root):
            raise DiagramError(f"--python-root is not a regular directory inside the repository: {relative}")
        if relative not in roots:
            roots.append(relative)
    return roots


def _scope_path(root: Path, value: str) -> str:
    relative = _normal_relpath(value, "--scope")
    absolute = root if relative == "." else root.joinpath(*PurePosixPath(relative).parts)
    if absolute.is_symlink() or not absolute.is_dir() or not absolute.resolve().is_relative_to(root):
        raise DiagramError(f"--scope is not a regular directory inside the repository: {relative}")
    return relative


def analyze_repository(
    repo_root: Path,
    name: str,
    language: str = "en",
    requested_roots: list[str] | None = None,
    scope_value: str = ".",
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    context = git_context(repo_root)
    root = repo_root.resolve(strict=True)
    scope = _scope_path(root, scope_value)
    roots = _source_roots(root, requested_roots)
    all_paths = _tracked_python_paths(root)
    scoped_paths = [
        path
        for path in all_paths
        if _within_scope(path, scope) and not any(part in EXCLUDED_DIRECTORY_NAMES for part in PurePosixPath(path).parts[:-1])
    ]

    parsed_paths: set[str] = set()
    file_rows: list[dict[str, Any]] = []
    raw_facts: list[ImportFact] = []
    skipped: dict[str, int] = {}
    total_source_bytes = 0
    for relative in scoped_paths:
        source, digest, reason, source_bytes = _read_python_file(
            root.joinpath(*PurePosixPath(relative).parts), root
        )
        total_source_bytes = _consume_budget(
            total_source_bytes, source_bytes, MAX_TOTAL_SOURCE_BYTES, "scanned source bytes"
        )
        if reason is None and source is not None:
            facts, parse_error = _extract_imports(
                source, relative, MAX_IMPORT_FACTS - len(raw_facts)
            )
            if parse_error:
                reason = parse_error
            else:
                parsed_paths.add(relative)
                raw_facts.extend(facts)
                file_rows.append({"path": relative, "sha256": digest, "status": "parsed"})
                continue
        skipped[reason or "unreadable"] = skipped.get(reason or "unreadable", 0) + 1
        file_rows.append({"path": relative, "sha256": digest, "status": "skipped", "reason": reason or "unreadable"})

    candidate_paths = set(all_paths)
    facts = _resolve_imports(raw_facts, candidate_paths, parsed_paths, roots, scope)
    internal_facts = [item for item in facts if item.status == "repository" and item.target is not None]
    graph_paths = {path for item in internal_facts for path in (item.source, item.target) if path is not None}
    graph_pairs = {(item.source, item.target) for item in internal_facts if item.target is not None}
    evidence_count = sum(item.evidence_id is not None for item in internal_facts)
    spec: dict[str, Any] | None = None
    layout_report = {"status": "not-run", "adjustments": [], "warnings": []}
    diagram_status = "no-resolved-repository-imports" if not graph_pairs else "ready"
    limit_errors: list[str] = []
    if graph_pairs:
        if len(graph_paths) > MAX_NODES:
            limit_errors.append(f"modules exceed renderer limit {MAX_NODES}")
        if len(graph_pairs) > MAX_EDGES:
            limit_errors.append(f"relationships exceed renderer limit {MAX_EDGES}")
        if evidence_count > MAX_EVIDENCE:
            limit_errors.append(f"evidence entries exceed renderer limit {MAX_EVIDENCE}")
        if limit_errors:
            diagram_status = "diagram-limit-exceeded"
        else:
            spec = _build_spec(facts, language)
    if spec is not None:
        spec, layout_report = _prepare_layout(spec, root)
        if layout_report["status"] == "blocked":
            limit_errors.extend(f"layout geometry: {warning}" for warning in layout_report["warnings"])
            diagram_status = "layout-unresolved"
            spec = None
    if spec is not None:
        if len(json.dumps(spec, ensure_ascii=False).encode("utf-8")) > MAX_SOURCE_JSON_BYTES:
            limit_errors.append("diagram source exceeds renderer limit 1 MB")
            diagram_status = "diagram-limit-exceeded"
            spec = None

    report_facts = [
        {
            "source": item.source,
            "line": item.line,
            "kind": item.kind,
            "module": item.specifier,
            "status": item.status,
            **({"target": item.target} if item.target else {}),
            **({"reason": item.reason} if item.reason else {}),
        }
        for item in facts
    ]
    report = {
        "schema_version": 1,
        "tool": TOOL,
        "repository": {"name": context["name"], "revision": context["revision"], "dirty": context["dirty"]},
        "parser": "Python ast (stdlib)",
        "scope": scope,
        "python_roots": roots,
        "files": {
            "repository_candidates": len(all_paths),
            "scope_candidates": len(scoped_paths),
            "parsed": len(parsed_paths),
            "skipped": sum(skipped.values()),
            "skipped_by_reason": dict(sorted(skipped.items())),
            "inventory": file_rows,
        },
        "imports": {
            "seen": len(facts),
            "resolved_to_repository": sum(item.status == "repository" for item in facts),
            "standard_library": sum(item.status == "standard-library" for item in facts),
            "external_or_unresolved": sum(item.status == "external-or-unresolved" for item in facts),
            "unresolved": sum(item.status == "unresolved" for item in facts),
            "facts": report_facts,
            "limits": [
                "Only import statements and recognized literal calls to __import__ or importlib.import_module are parsed.",
                "Other runtime loading mechanisms, computed names, and import-time behavior are not inferred.",
                "from package import name resolves to the package module only; symbol or submodule binding is not inferred.",
                "Files over 1 MB or non-regular source paths are skipped without reading source text.",
                f"Analysis stops without partial artifacts above {MAX_SOURCE_LIST_BYTES} Git inventory bytes, {MAX_SOURCE_FILES} Python files, {MAX_TOTAL_SOURCE_BYTES} scanned source bytes, or {MAX_IMPORT_FACTS} import facts.",
            ],
        },
        "diagram": {
            "status": diagram_status,
            "modules": len(graph_paths),
            "relationships": len(graph_pairs),
            "evidence": evidence_count,
            "layout": layout_report,
            "limits": limit_errors,
        },
    }
    if spec is not None:
        validate_spec(spec, repo_root=root)
    return report, spec


def _write_outputs(out_dir: Path, name: str, report: dict[str, Any], spec: dict[str, Any] | None) -> list[Path]:
    report_path = out_dir / f"{name}.imports.json"
    spec_path = out_dir / f"{name}.diagram.json"
    if report_path.exists() or spec_path.exists():
        raise DiagramError("output already exists; choose a new output directory or name")
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        for path, value in ((report_path, report), (spec_path, spec)):
            if value is None:
                continue
            data = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            with path.open("xb") as destination:
                written.append(path)
                destination.write(data)
                destination.flush()
                os.fsync(destination.fileno())
    except OSError:
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        raise DiagramError("could not write generated import graph files")
    return written


def _self_test() -> int:
    for maximum, label in (
        (MAX_SOURCE_FILES, "Python source files"),
        (MAX_TOTAL_SOURCE_BYTES, "scanned source bytes"),
        (MAX_IMPORT_FACTS, "import facts"),
    ):
        if _consume_budget(maximum - 1, 1, maximum, label) != maximum:
            raise AssertionError(f"{label} limit rejected its exact boundary")
        try:
            _consume_budget(maximum, 1, maximum, label)
        except DiagramError as error:
            if "resource limit exceeded" not in str(error):
                raise AssertionError(f"{label} limit did not report a resource bound") from error
        else:
            raise AssertionError(f"{label} limit accepted an over-bound value")

    with TemporaryDirectory(prefix="patpat-import-graph-self-test-") as temporary_name:
        root = Path(temporary_name).resolve()
        source_path = root / "module.py"
        source_bytes = b"value = 1\n"
        source_path.write_bytes(source_bytes)
        source, digest, reason, read_bytes = _read_python_file(source_path, root)
        if source != source_bytes.decode("utf-8") or digest != hashlib.sha256(source_bytes).hexdigest() or reason or read_bytes != len(source_bytes):
            raise AssertionError("bounded regular-file reading did not preserve source text and digest")
        oversized = root / "oversized.py"
        oversized.write_bytes(b" " * (MAX_FILE_BYTES + 1))
        if _read_python_file(oversized, root) != (None, None, "too-large", 0):
            raise AssertionError("oversized source was read or hashed instead of skipped")
        non_regular = root / "directory.py"
        non_regular.mkdir()
        if _read_python_file(non_regular, root) != (None, None, "not-regular-file", 0):
            raise AssertionError("a non-regular Python source path was opened")
        link = root / "linked.py"
        try:
            link.symlink_to(source_path)
        except OSError:
            pass
        else:
            if _read_python_file(link, root) != (None, None, "symlink", 0):
                raise AssertionError("a symbolic-link source path was followed")
        changed = root / "changed-during-read.py"
        changed.write_bytes(b"x")
        real_fstat = os.fstat

        def grow_after_fstat(descriptor: int) -> os.stat_result:
            result = real_fstat(descriptor)
            with changed.open("ab") as appended:
                appended.write(b"y")
            return result

        with patch("os.fstat", side_effect=grow_after_fstat):
            changed_result = _read_python_file(changed, root)
        if changed_result != (None, None, "source-changed-during-read", 2):
            raise AssertionError("bytes read from a changing source were omitted from the analysis budget")

    with TemporaryDirectory(prefix="patpat-import-graph-inventory-test-") as temporary_name:
        root = Path(temporary_name).resolve()
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True, timeout=10)
        (root / "one.py").write_text("value = 1\n", encoding="utf-8")
        (root / "two.py").write_text("value = 2\n", encoding="utf-8")
        if _tracked_python_paths(root, max_paths=2) != ["one.py", "two.py"]:
            raise AssertionError("Python source inventory did not include tracked and untracked files")
        try:
            _tracked_python_paths(root, max_paths=1)
        except DiagramError as error:
            if "Python source files" not in str(error):
                raise AssertionError("source file limit did not identify its resource") from error
        else:
            raise AssertionError("Python source inventory accepted an over-bound candidate count")

    try:
        _extract_imports("import first\nimport second\n", "limited.py", max_facts=1)
    except DiagramError as error:
        if "import facts" not in str(error):
            raise AssertionError("import fact limit did not identify its resource") from error
    else:
        raise AssertionError("parser accepted an over-bound import fact count")

    with TemporaryDirectory(prefix="patpat-import-graph-empty-test-") as temporary_name:
        parent = Path(temporary_name).resolve()
        root = parent / "repo"
        root.mkdir()
        subprocess.run(["git", "-C", str(root), "init", "--quiet"], check=True, timeout=10)
        subprocess.run(
            [
                "git", "-C", str(root), "-c", "user.name=Patpat Self Test",
                "-c", "user.email=patpat-self-test@example.invalid", "commit",
                "--allow-empty", "--quiet", "-m", "fixture",
            ],
            check=True,
            timeout=10,
        )
        (root / "stdlib_only.py").write_text("import pathlib\n", encoding="utf-8")
        output = parent / "output"
        result = subprocess.run(
            [
                sys.executable, str(Path(__file__).resolve()), "--repo-root", str(root),
                "--out-dir", str(output), "--name", "no-internal-imports",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        try:
            cli_result = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError(f"empty graph CLI did not return a status record: {result.stderr}") from error
        report_path = output / "no-internal-imports.imports.json"
        diagram_path = output / "no-internal-imports.diagram.json"
        if (
            result.returncode != 0
            or cli_result.get("status") != "no-resolved-repository-imports"
            or cli_result.get("diagram") != ""
            or not report_path.is_file()
            or diagram_path.exists()
        ):
            raise AssertionError("empty graph CLI must retain its report and stop without a diagram")

    sources = {
        "pkg/__init__.py": "",
        "pkg/a.py": (
            "from .b import value\n"
            "import importlib\n"
            "importlib.import_module('pkg.b')\n"
            "importlib.import_module(module_name)\n"
            "import pathlib\n"
        ),
        "pkg/b.py": "from .a import value\n",
        "pkg/missing.py": "",
    }
    facts: list[ImportFact] = []
    for path, source in sorted(sources.items()):
        parsed, error = _extract_imports(source, path)
        if error:
            raise AssertionError(f"self-test fixture failed to parse: {path}")
        facts.extend(parsed)
    resolved = _resolve_imports(facts, set(sources), set(sources), ["."], ".")
    statuses = {(item.source, item.specifier): item.status for item in resolved}
    if statuses.get(("pkg/a.py", ".b")) != "repository":
        raise AssertionError("relative import did not resolve to its repository module")
    if statuses.get(("pkg/a.py", "pkg.b")) != "repository":
        raise AssertionError("literal dynamic import did not resolve to its repository module")
    if not any(
        item.source == "pkg/a.py"
        and item.kind == "dynamic-import"
        and item.specifier is None
        and item.reason == "dynamic-specifier-not-literal"
        for item in resolved
    ):
        raise AssertionError("non-literal dynamic import was not reported unresolved")
    shadowed_facts, shadowed_error = _extract_imports(
        "def __import__(name):\n    return None\n__import__('pkg.b')\n",
        "pkg/shadowed.py",
    )
    if shadowed_error or not any(
        item.kind == "dynamic-import"
        and item.specifier is None
        and item.reason == "dynamic-loader-unresolved"
        for item in shadowed_facts
    ):
        raise AssertionError("a shadowed __import__ function was incorrectly treated as a repository import")
    if statuses.get(("pkg/a.py", "pathlib")) != "standard-library":
        raise AssertionError("standard-library import was not classified")
    if statuses.get(("pkg/b.py", ".a")) != "repository":
        raise AssertionError("reverse import did not resolve for cycle coverage")
    spec = _build_spec(resolved, "en")
    if spec is None or not any(edge.get("feedback") for edge in spec["body"]["relationships"]):
        raise AssertionError("cycle-closing relationship was not routed as feedback")
    if len({item["id"] for item in spec["body"]["components"]}) != len(spec["body"]["components"]):
        raise AssertionError("module IDs are not unique")

    fanout_facts = [
        ImportFact(
            "tests/test_adversarial_controls.py", 8, 8, 0, "from-import",
            "scripts.eval_adversarial_controls", status="repository",
            target="scripts/eval_adversarial_controls.py",
            evidence_id=_stable_id("E", "fanout", "eval"),
        ),
        ImportFact(
            "tests/test_adversarial_controls.py", 60, 60, 0, "from-import",
            "scripts.dry_run_loop", status="repository",
            target="scripts/dry_run_loop.py",
            evidence_id=_stable_id("E", "fanout", "dry-run"),
        ),
        ImportFact(
            "tests/test_sanitize_logs.py", 6, 6, 0, "from-import",
            "scripts.sanitize_logs", status="repository",
            target="scripts/sanitize_logs.py",
            evidence_id=_stable_id("E", "fanout", "sanitize"),
        ),
    ]
    fanout_spec = _build_spec(fanout_facts, "en")
    if fanout_spec is None:
        raise AssertionError("multi-target imports did not create a graph")
    fanout_routed, fanout_report = _prepare_layout(fanout_spec, None)
    if fanout_report["status"] != "passed" or fanout_report["warnings"]:
        raise AssertionError(f"adjacent-rank fanout imports crossed: {fanout_report}")

    layered = {
        "schema_version": 2,
        "type": "architecture",
        "language": "en",
        "title": "Long import route",
        "summary": "A layered source graph with one shared dependency",
        "layout": {"direction": "LR"},
        "evidence": [{"id": "B1", "origin": "brief", "claim": "Fixture relationship"}],
        "body": {
            "components": [
                {"id": f"N{index}", "label": label, "kind": "component", "certainty": "confirmed", "evidence_ids": ["B1"]}
                for index, label in enumerate(("module a", "module b", "module c", "shared model"), 1)
            ],
            "relationships": [
                {"id": "R1", "source": "N1", "target": "N4", "label": "imports", "kind": "depends_on", "certainty": "confirmed", "evidence_ids": ["B1"]},
                {"id": "R2", "source": "N2", "target": "N3", "label": "imports", "kind": "depends_on", "certainty": "confirmed", "evidence_ids": ["B1"]},
                {"id": "R3", "source": "N3", "target": "N4", "label": "imports", "kind": "depends_on", "certainty": "confirmed", "evidence_ids": ["B1"]},
                {"id": "R4", "source": "N2", "target": "N4", "label": "imports", "kind": "depends_on", "certainty": "confirmed", "evidence_ids": ["B1"]},
            ],
        },
    }
    routed, layout_report = _prepare_layout(layered, None)
    if layout_report["status"] != "passed" or layout_report["warnings"]:
        raise AssertionError(f"long skipped-rank imports did not pass geometry routing: {layout_report}")
    if [row["relationship"] for row in layout_report["adjustments"]] != ["R4"]:
        raise AssertionError(f"only the obstructed bottom-peer route should be adjusted: {layout_report['adjustments']}")
    routed_layout = _make_layout(validate_spec(routed, repo_root=None))
    long_path = next(path for path in routed_layout["paths"] if path["edge"]["id"] == "R4")
    if long_path["points"][0][1] != routed_layout["positions"]["N2"]["y"] + routed_layout["positions"]["N2"]["h"]:
        raise AssertionError("clearance route did not leave the bottom edge of its source node")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, help="exact Git repository root to inspect")
    parser.add_argument("--out-dir", type=Path, help="new or existing directory outside the repository")
    parser.add_argument("--name", default="python-import-graph", help="output slug")
    parser.add_argument("--language", choices=("en", "th"), default="en")
    parser.add_argument("--python-root", action="append", help="repository-relative Python import root; repeatable")
    parser.add_argument("--scope", default=".", help="repository-relative directory to analyze")
    parser.add_argument("--self-test", action="store_true", help="check source reading, parser, graph, and geometry contracts")
    args = parser.parse_args()
    if args.self_test:
        try:
            _self_test()
        except AssertionError as error:
            print(f"import graph self-test failed: {error}", file=sys.stderr)
            return 1
        print(json.dumps({"status": "passed", "tool": TOOL, "scope": "source reading, parser, graph, and geometry contracts"}))
        return 0
    if args.repo_root is None or args.out_dir is None:
        parser.error("--repo-root and --out-dir are required")
    if not SLUG_PATTERN.fullmatch(args.name):
        parser.error("--name must be a lowercase hyphenated slug")
    try:
        root = args.repo_root.resolve(strict=True)
        context = git_context(root)
        output = args.out_dir.resolve()
        if output == root or root in output.parents:
            raise DiagramError("--out-dir must be outside the repository")
        report, spec = analyze_repository(root, args.name, args.language, args.python_root, args.scope)
        written = _write_outputs(output, args.name, report, spec)
    except (DiagramError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["diagram"]["status"],
                "revision": context["revision"],
                "files": report["files"]["parsed"],
                "resolved_imports": report["imports"]["resolved_to_repository"],
                "report": str(next(path for path in written if path.name.endswith(".imports.json"))),
                "diagram": str(next((path for path in written if path.name.endswith(".diagram.json")), "")),
                "limits": report["diagram"]["limits"],
            },
            ensure_ascii=False,
        )
    )
    return 2 if report["diagram"]["status"] in {"diagram-limit-exceeded", "layout-unresolved"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
