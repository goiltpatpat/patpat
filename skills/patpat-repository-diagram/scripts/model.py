#!/usr/bin/env python3
"""Validate Patpat's typed repository-diagram source and source anchors."""

from __future__ import annotations

from collections import deque
import hashlib
import json
import math
import re
import subprocess
from urllib.parse import urlsplit
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSIONS = {1, 2}
DIAGRAM_TYPES = {"architecture", "workflow", "sequence", "dataflow", "lifecycle"}
LANGUAGES = {"en", "th"}
CERTAINTIES = {"confirmed", "inferred", "unknown"}
ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,31}$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
MAX_NODES = 80
MAX_EDGES = 160
MAX_EVIDENCE = 240
MAX_LABEL_LENGTH = 180
MAX_SOURCE_JSON_BYTES = 1_000_000


class DiagramError(ValueError):
    """A diagram source or repository anchor violates the Patpat contract."""


def _object(value: Any, name: str, required: set[str], optional: set[str] = frozenset()) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiagramError(f"{name} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing:
        raise DiagramError(f"{name} is missing: {', '.join(sorted(missing))}")
    if unknown:
        raise DiagramError(f"{name} has unsupported fields: {', '.join(sorted(unknown))}")
    return value


def _text(value: Any, name: str, *, maximum: int = MAX_LABEL_LENGTH, multiline: bool = False) -> str:
    if not isinstance(value, str):
        raise DiagramError(f"{name} must be text")
    if not value.strip() or len(value) > maximum:
        raise DiagramError(f"{name} must contain 1 to {maximum} characters")
    for char in value:
        code = ord(char)
        if code < 32 and not (multiline and char == "\n"):
            raise DiagramError(f"{name} contains a control character")
        if code == 127:
            raise DiagramError(f"{name} contains a control character")
    return value.strip()


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise DiagramError(f"{name} must match {ID_PATTERN.pattern}")
    return value


def _string_list(value: Any, name: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or (not allow_empty and not value):
        raise DiagramError(f"{name} must be a {'possibly empty ' if allow_empty else ''}array")
    result = [_id(item, f"{name}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise DiagramError(f"{name} contains duplicate IDs")
    return result


def _array(value: Any, name: str, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise DiagramError(f"{name} must be an array of at most {maximum} entries")
    return value


def _certainty_fields(item: dict[str, Any], name: str) -> tuple[str, list[str], str | None]:
    certainty = item.get("certainty")
    if not isinstance(certainty, str) or certainty not in CERTAINTIES:
        raise DiagramError(f"{name}.certainty must be confirmed, inferred, or unknown")
    evidence_ids = _string_list(item.get("evidence_ids"), f"{name}.evidence_ids", allow_empty=True)
    reason = item.get("reason")
    if certainty == "unknown":
        if evidence_ids:
            raise DiagramError(f"{name}: unknown claims cannot cite source evidence")
        reason = _text(reason, f"{name}.reason", maximum=240)
    else:
        if not evidence_ids:
            raise DiagramError(f"{name}: {certainty} claims need evidence_ids")
        if reason is not None:
            raise DiagramError(f"{name}.reason is allowed only when certainty is unknown")
    return certainty, evidence_ids, reason


def _entity(
    item: Any,
    name: str,
    allowed_kinds: set[str],
    *,
    optional: set[str] = frozenset(),
) -> dict[str, Any]:
    item = _object(
        item,
        name,
        {"id", "label", "kind", "certainty", "evidence_ids"},
        optional | {"reason"},
    )
    identifier = _id(item["id"], f"{name}.id")
    label = _text(item["label"], f"{name}.label")
    kind = item["kind"]
    if not isinstance(kind, str) or kind not in allowed_kinds:
        raise DiagramError(f"{name}.kind must be one of: {', '.join(sorted(allowed_kinds))}")
    certainty, evidence_ids, reason = _certainty_fields(item, name)
    result = {
        "id": identifier,
        "label": label,
        "kind": kind,
        "certainty": certainty,
        "evidence_ids": evidence_ids,
        "reason": reason,
    }
    if "lane_id" in optional and "lane_id" in item:
        result["lane_id"] = _id(item["lane_id"], f"{name}.lane_id")
    return result


def _edge(
    item: Any,
    name: str,
    allowed_kinds: set[str],
    *,
    sequence: bool = False,
) -> dict[str, Any]:
    required = {"id", "source", "target", "label", "kind", "certainty", "evidence_ids"}
    if sequence:
        required.add("order")
    item = _object(item, name, required, {"reason", "feedback"})
    identifier = _id(item["id"], f"{name}.id")
    source = _id(item["source"], f"{name}.source")
    target = _id(item["target"], f"{name}.target")
    label = _text(item["label"], f"{name}.label")
    kind = item["kind"]
    if not isinstance(kind, str) or kind not in allowed_kinds:
        raise DiagramError(f"{name}.kind must be one of: {', '.join(sorted(allowed_kinds))}")
    certainty, evidence_ids, reason = _certainty_fields(item, name)
    feedback = item.get("feedback", False)
    if not isinstance(feedback, bool):
        raise DiagramError(f"{name}.feedback must be boolean")
    result = {
        "id": identifier,
        "source": source,
        "target": target,
        "label": label,
        "kind": kind,
        "certainty": certainty,
        "evidence_ids": evidence_ids,
        "reason": reason,
        "feedback": feedback,
    }
    if sequence:
        order = item["order"]
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise DiagramError(f"{name}.order must be a positive integer")
        result["order"] = order
    return result


def _group(item: Any, name: str, member_name: str) -> dict[str, Any]:
    item = _object(
        item,
        name,
        {"id", "label", member_name, "certainty", "evidence_ids"},
        {"reason"},
    )
    identifier = _id(item["id"], f"{name}.id")
    label = _text(item["label"], f"{name}.label")
    members = _string_list(item[member_name], f"{name}.{member_name}")
    certainty, evidence_ids, reason = _certainty_fields(item, name)
    return {
        "id": identifier,
        "label": label,
        "members": members,
        "certainty": certainty,
        "evidence_ids": evidence_ids,
        "reason": reason,
    }


def _unique_ids(groups: list[list[dict[str, Any]]]) -> None:
    seen: set[str] = set()
    for group in groups:
        for item in group:
            identifier = item["id"]
            if identifier in seen:
                raise DiagramError(f"duplicate diagram ID: {identifier}")
            seen.add(identifier)


def _evidence(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list) or not items or len(items) > MAX_EVIDENCE:
        raise DiagramError(f"evidence must contain 1 to {MAX_EVIDENCE} entries")
    result = []
    seen: set[str] = set()
    for index, raw in enumerate(items):
        name = f"evidence[{index}]"
        if not isinstance(raw, dict):
            raise DiagramError(f"{name} must be an object")
        origin = raw.get("origin", "repository")
        if not isinstance(origin, str) or origin not in {"repository", "brief"}:
            raise DiagramError(f"{name}.origin must be repository or brief")
        required = {"id", "claim"} if origin == "brief" else {"id", "path", "start_line", "end_line", "claim"}
        item = _object(raw, name, required, {"origin"})
        identifier = _id(item["id"], f"{name}.id")
        if identifier in seen:
            raise DiagramError(f"duplicate evidence ID: {identifier}")
        seen.add(identifier)
        claim = _text(item["claim"], f"{name}.claim", maximum=320)
        if origin == "brief":
            result.append({"id": identifier, "origin": origin, "claim": claim})
            continue
        path = _text(item["path"], f"{name}.path", maximum=320)
        pure_path = PurePosixPath(path)
        if pure_path.is_absolute() or pure_path.as_posix() != path or re.match(r"^[A-Za-z]:", path) or "\\" in path or any(part in {"", ".", ".."} for part in pure_path.parts):
            raise DiagramError(f"{name}.path must be a normalized repository-relative path")
        start = item["start_line"]
        end = item["end_line"]
        if isinstance(start, bool) or not isinstance(start, int) or start < 1:
            raise DiagramError(f"{name}.start_line must be a positive integer")
        if isinstance(end, bool) or not isinstance(end, int) or end < start or end - start > 60:
            raise DiagramError(f"{name}.end_line must be within 60 lines after start_line")
        repository_item = {
            "id": identifier,
            "path": path,
            "start_line": start,
            "end_line": end,
            "claim": claim,
        }
        if "origin" in item:
            repository_item["origin"] = origin
        result.append(repository_item)
    return result


def _finite_coordinate(value: Any, name: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DiagramError(f"{name} must be a finite number")
    if value < minimum or value > maximum:
        raise DiagramError(f"{name} must be between {minimum:g} and {maximum:g}")
    if not math.isfinite(value):
        raise DiagramError(f"{name} must be a finite number")
    return float(value)


def _layout(raw: Any, diagram_type: str, entity_ids: set[str], edge_ids: set[str]) -> dict[str, Any]:
    if raw is None:
        return {"direction": "LR", "layers": None}
    geometry_fields = {"positions", "edge_hints"} if diagram_type != "sequence" else set()
    raw = _object(raw, "layout", set(), {"direction", "layers"} | geometry_fields)
    direction = raw.get("direction", "LR")
    if not isinstance(direction, str) or direction not in {"LR", "TB"}:
        raise DiagramError("layout.direction must be LR or TB")
    if diagram_type == "sequence" and direction != "LR":
        raise DiagramError("sequence diagrams use temporal left-to-right direction; layout.direction must be LR")
    layers = raw.get("layers")
    if layers is not None:
        if diagram_type == "sequence":
            raise DiagramError("sequence diagrams use message order, not layout.layers")
        if not isinstance(layers, list) or not layers or any(not isinstance(layer, list) or not layer for layer in layers):
            raise DiagramError("layout.layers must be a non-empty array of non-empty ID arrays")
        normalized = []
        for index, layer in enumerate(layers):
            normalized.append([_id(identifier, f"layout.layers[{index}]") for identifier in layer])
        flat = [identifier for layer in normalized for identifier in layer]
        if len(flat) != len(set(flat)):
            raise DiagramError("layout.layers repeats an entity ID")
        layers = normalized
    normalized = {"direction": direction, "layers": layers}
    if "positions" in raw:
        value = raw["positions"]
        if not isinstance(value, dict) or not value:
            raise DiagramError("layout.positions must map every graph entity ID to {x, y}")
        supplied_ids = {_id(identifier, "layout.positions key") for identifier in value}
        if supplied_ids != entity_ids:
            missing = sorted(entity_ids - supplied_ids)
            unknown = sorted(supplied_ids - entity_ids)
            raise DiagramError(f"layout.positions must cover every graph entity exactly once; missing={missing}, unknown={unknown}")
        positions = {}
        for identifier, coordinates in value.items():
            coordinates = _object(coordinates, f"layout.positions.{identifier}", {"x", "y"})
            positions[identifier] = {
                "x": _finite_coordinate(coordinates["x"], f"layout.positions.{identifier}.x", minimum=0, maximum=20000),
                "y": _finite_coordinate(coordinates["y"], f"layout.positions.{identifier}.y", minimum=0, maximum=20000),
            }
        normalized["positions"] = positions
    if "edge_hints" in raw:
        value = raw["edge_hints"]
        if not isinstance(value, dict) or not value or len(value) > len(edge_ids):
            raise DiagramError("layout.edge_hints must map one or more graph relationship IDs to geometry hints")
        edge_hints = {}
        allowed_sides = {"top", "right", "bottom", "left"}
        for identifier, raw_hint in value.items():
            identifier = _id(identifier, "layout.edge_hints key")
            if identifier not in edge_ids:
                raise DiagramError(f"layout.edge_hints references unknown relationship {identifier}")
            hint = _object(raw_hint, f"layout.edge_hints.{identifier}", set(), {"source_side", "target_side", "waypoints", "label"})
            if not hint:
                raise DiagramError(f"layout.edge_hints.{identifier} must contain at least one geometry hint")
            normalized_hint = {}
            for side_key in ("source_side", "target_side"):
                if side_key in hint:
                    side = hint[side_key]
                    if not isinstance(side, str) or side not in allowed_sides:
                        raise DiagramError(f"layout.edge_hints.{identifier}.{side_key} must be top, right, bottom, or left")
                    normalized_hint[side_key] = side
            if "waypoints" in hint:
                waypoints = hint["waypoints"]
                if not isinstance(waypoints, list) or not 1 <= len(waypoints) <= 12:
                    raise DiagramError(f"layout.edge_hints.{identifier}.waypoints must contain 1 to 12 points")
                normalized_points = []
                for index, point in enumerate(waypoints):
                    point = _object(point, f"layout.edge_hints.{identifier}.waypoints[{index}]", {"x", "y"})
                    normalized_points.append({
                        "x": _finite_coordinate(point["x"], f"layout.edge_hints.{identifier}.waypoints[{index}].x", minimum=0, maximum=20000),
                        "y": _finite_coordinate(point["y"], f"layout.edge_hints.{identifier}.waypoints[{index}].y", minimum=0, maximum=20000),
                    })
                if any(left == right for left, right in zip(normalized_points, normalized_points[1:])):
                    raise DiagramError(f"layout.edge_hints.{identifier}.waypoints cannot repeat adjacent points")
                normalized_hint["waypoints"] = normalized_points
            if "label" in hint:
                label = _object(hint["label"], f"layout.edge_hints.{identifier}.label", {"segment"}, {"offset"})
                segment = label["segment"]
                if isinstance(segment, bool) or not isinstance(segment, int) or not 0 <= segment <= 12:
                    raise DiagramError(f"layout.edge_hints.{identifier}.label.segment must be an integer from 0 to 12")
                offset = label.get("offset", {"x": 0, "y": 0})
                offset = _object(offset, f"layout.edge_hints.{identifier}.label.offset", {"x", "y"})
                normalized_hint["label"] = {
                    "segment": segment,
                    "offset": {
                        "x": _finite_coordinate(offset["x"], f"layout.edge_hints.{identifier}.label.offset.x", minimum=-2000, maximum=2000),
                        "y": _finite_coordinate(offset["y"], f"layout.edge_hints.{identifier}.label.offset.y", minimum=-2000, maximum=2000),
                    },
                }
            if not normalized_hint:
                raise DiagramError(f"layout.edge_hints.{identifier} must contain at least one geometry hint")
            edge_hints[identifier] = normalized_hint
        normalized["edge_hints"] = edge_hints
    return normalized


def _story_views(value: Any, element_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not 1 <= len(value) <= 12:
        raise DiagramError("views must contain 1 to 12 authored story views")
    result = []
    seen: set[str] = set()
    for index, raw in enumerate(value):
        name = f"views[{index}]"
        item = _object(raw, name, {"id", "label", "focus"}, {"note"})
        identifier = _id(item["id"], f"{name}.id")
        if identifier in seen:
            raise DiagramError(f"duplicate story view ID: {identifier}")
        seen.add(identifier)
        label = _text(item["label"], f"{name}.label", maximum=120)
        focus = _string_list(item["focus"], f"{name}.focus")
        if len(focus) > 40:
            raise DiagramError(f"{name}.focus must contain at most 40 stable element IDs")
        unknown = sorted(set(focus) - element_ids)
        if unknown:
            raise DiagramError(f"{name}.focus references unknown diagram elements: {', '.join(unknown)}")
        note = _text(item["note"], f"{name}.note", maximum=320) if "note" in item else None
        result.append({"id": identifier, "label": label, "focus": focus, "note": note})
    return result


def _validate_workflow_structure(steps: list[dict[str, Any]], transitions: list[dict[str, Any]]) -> None:
    outgoing = {step["id"]: [] for step in steps}
    incoming = {step["id"]: [] for step in steps}
    for transition in transitions:
        outgoing[transition["source"]].append(transition["target"])
        incoming[transition["target"]].append(transition["source"])

    starts = [step["id"] for step in steps if step["kind"] == "start"]
    terminals = [step["id"] for step in steps if step["kind"] == "terminal"]
    for step in steps:
        identifier = step["id"]
        if step["kind"] in {"gate", "decision"} and len(outgoing[identifier]) < 2:
            raise DiagramError(f"decision step {identifier} must have at least two outgoing transitions")
        if step["kind"] == "terminal" and outgoing[identifier]:
            raise DiagramError(f"terminal step {identifier} cannot have outgoing transitions")

    def reachable(origins: list[str], adjacency: dict[str, list[str]]) -> set[str]:
        visited = set(origins)
        pending = deque(origins)
        while pending:
            current = pending.popleft()
            for neighbor in adjacency[current]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        return visited

    from_start = reachable(starts, outgoing)
    for step in steps:
        if step["id"] not in from_start:
            raise DiagramError(f"workflow step {step['id']} is not reachable from a start step")

    to_terminal = reachable(terminals, incoming)
    for step in steps:
        if step["id"] not in to_terminal:
            raise DiagramError(f"workflow step {step['id']} cannot reach a terminal step")


def validate_spec(
    raw: Any,
    repo_root: Path | None,
    *,
    require_repository_sources: bool = False,
) -> dict[str, Any]:
    """Validate a typed source spec and capture exact source-line digests."""
    raw = _object(raw, "diagram", {"schema_version", "type", "title", "evidence", "body"}, {"summary", "layout", "language", "profile", "views"})
    schema_version = raw["schema_version"]
    if isinstance(schema_version, bool) or not isinstance(schema_version, int) or schema_version not in SCHEMA_VERSIONS:
        raise DiagramError(f"schema_version must be one of: {', '.join(map(str, sorted(SCHEMA_VERSIONS)))}")
    if schema_version == 1 and "profile" in raw:
        raise DiagramError("schema_version 1 does not support profiles")
    if schema_version == 1 and "views" in raw:
        raise DiagramError("schema_version 1 does not support story views")
    diagram_type = raw["type"]
    if not isinstance(diagram_type, str) or diagram_type not in DIAGRAM_TYPES:
        raise DiagramError(f"type must be one of: {', '.join(sorted(DIAGRAM_TYPES))}")
    title = _text(raw["title"], "title", maximum=120)
    language = raw.get("language", "en")
    if not isinstance(language, str) or language not in LANGUAGES:
        raise DiagramError(f"language must be one of: {', '.join(sorted(LANGUAGES))}")
    evidence = _evidence(raw["evidence"])
    brief_only = all(item.get("origin", "repository") == "brief" for item in evidence)
    if language == "th":
        default_summary = "แผนภาพโต้ตอบจากคำบรรยาย" if brief_only else "แผนภาพจากหลักฐานใน repository"
    else:
        default_summary = f"Interactive {diagram_type} diagram from the brief" if brief_only else f"Source-backed {diagram_type} diagram"
    summary = _text(raw.get("summary", default_summary), "summary", maximum=260)
    body = raw["body"]
    evidence_ids = {entry["id"] for entry in evidence}
    if diagram_type == "architecture":
        body = _object(body, "body", {"components", "relationships"}, {"boundaries"})
        entity_name, edge_name = "components", "relationships"
        entity_kinds = {"actor", "service", "gateway", "worker", "database", "cache", "queue", "external", "component"}
        edge_kinds = {"call", "data", "event", "deploys_to", "contains", "depends_on"}
        entities = [_entity(item, f"components[{i}]", entity_kinds) for i, item in enumerate(_array(body[entity_name], entity_name, MAX_NODES))]
        edges = [_edge(item, f"relationships[{i}]", edge_kinds) for i, item in enumerate(_array(body[edge_name], edge_name, MAX_EDGES))]
        groups = [_group(item, f"boundaries[{i}]", "component_ids") for i, item in enumerate(_array(body.get("boundaries", []), "boundaries", MAX_NODES))]
    elif diagram_type == "workflow":
        body = _object(body, "body", {"steps", "transitions"}, {"lanes"})
        entity_name, edge_name = "steps", "transitions"
        entity_kinds = {"start", "action", "gate", "decision", "wait", "terminal"}
        edge_kinds = {"next", "yes", "no", "approval", "retry", "cancel", "error", "condition"}
        entities = [_entity(item, f"steps[{i}]", entity_kinds) for i, item in enumerate(_array(body[entity_name], entity_name, MAX_NODES))]
        edges = [_edge(item, f"transitions[{i}]", edge_kinds) for i, item in enumerate(_array(body[edge_name], edge_name, MAX_EDGES))]
        groups = [_group(item, f"lanes[{i}]", "step_ids") for i, item in enumerate(_array(body.get("lanes", []), "lanes", MAX_NODES))]
        step_kinds = [entity["kind"] for entity in entities]
        if "start" not in step_kinds or "terminal" not in step_kinds:
            raise DiagramError("workflow needs at least one start and one terminal step")
    elif diagram_type == "sequence":
        body = _object(body, "body", {"participants", "messages"})
        entity_name, edge_name = "participants", "messages"
        entity_kinds = {"actor", "client", "service", "worker", "database", "queue", "external", "system"}
        edge_kinds = {"call", "return", "async", "event"}
        entities = [_entity(item, f"participants[{i}]", entity_kinds) for i, item in enumerate(_array(body[entity_name], entity_name, MAX_NODES))]
        edges = [_edge(item, f"messages[{i}]", edge_kinds, sequence=True) for i, item in enumerate(_array(body[edge_name], edge_name, MAX_EDGES))]
        groups = []
        orders = [edge["order"] for edge in edges]
        if len(orders) != len(set(orders)):
            raise DiagramError("sequence message order values must be unique")
    elif diagram_type == "dataflow":
        body = _object(body, "body", {"entities", "flows"})
        entity_name, edge_name = "entities", "flows"
        entity_kinds = {"source", "transform", "store", "consumer", "sink", "queue"}
        edge_kinds = {"data", "event", "stream", "snapshot"}
        entities = [_entity(item, f"entities[{i}]", entity_kinds) for i, item in enumerate(_array(body[entity_name], entity_name, MAX_NODES))]
        edges = [_edge(item, f"flows[{i}]", edge_kinds) for i, item in enumerate(_array(body[edge_name], edge_name, MAX_EDGES))]
        groups = []
    else:
        body = _object(body, "body", {"states", "transitions"})
        entity_name, edge_name = "states", "transitions"
        entity_kinds = {"initial", "state", "terminal"}
        edge_kinds = {"transition", "timeout", "retry", "cancel", "error"}
        entities = [_entity(item, f"states[{i}]", entity_kinds) for i, item in enumerate(_array(body[entity_name], entity_name, MAX_NODES))]
        edges = [_edge(item, f"transitions[{i}]", edge_kinds) for i, item in enumerate(_array(body[edge_name], edge_name, MAX_EDGES))]
        groups = []
        if sum(entity["kind"] == "initial" for entity in entities) != 1:
            raise DiagramError("lifecycle needs exactly one initial state")
        if not any(entity["kind"] == "terminal" for entity in entities):
            raise DiagramError("lifecycle needs at least one terminal state")

    if not entities or len(entities) > MAX_NODES:
        raise DiagramError(f"{entity_name} must contain 1 to {MAX_NODES} entries")
    if not edges or len(edges) > MAX_EDGES:
        raise DiagramError(f"{edge_name} must contain 1 to {MAX_EDGES} entries")
    _unique_ids([entities, edges, groups, evidence])
    entity_ids = {item["id"] for item in entities}
    for item in edges:
        if item["source"] not in entity_ids or item["target"] not in entity_ids:
            raise DiagramError(f"{item['id']} references an unknown source or target")
        if item["source"] == item["target"] and not item["feedback"] and diagram_type != "sequence":
            raise DiagramError(f"self-relationship {item['id']} must set feedback=true")
    if diagram_type == "workflow":
        _validate_workflow_structure(entities, edges)
    views = _story_views(raw["views"], entity_ids | {item["id"] for item in edges}) if "views" in raw else []
    group_members: set[str] = set()
    for group in groups:
        for member in group["members"]:
            if member not in entity_ids:
                raise DiagramError(f"{group['id']} references unknown entity {member}")
            if member in group_members:
                raise DiagramError(f"entity {member} belongs to more than one boundary or lane")
            group_members.add(member)
    layout = _layout(raw.get("layout"), diagram_type, entity_ids, {item["id"] for item in edges})
    if layout["layers"] is not None:
        flattened = [identifier for layer in layout["layers"] for identifier in layer]
        if set(flattened) != entity_ids:
            raise DiagramError("layout.layers must contain each entity exactly once")
        rank = {identifier: index for index, layer in enumerate(layout["layers"]) for identifier in layer}
        for edge in edges:
            if not edge["feedback"] and rank[edge["source"]] >= rank[edge["target"]]:
                raise DiagramError(f"layout.layers must move {edge['id']} forward or mark it feedback=true")
    referenced_evidence: set[str] = set()
    for item in entities + edges + groups:
        for evidence_id in item["evidence_ids"]:
            if evidence_id not in evidence_ids:
                raise DiagramError(f"{item['id']} references unknown evidence {evidence_id}")
            referenced_evidence.add(evidence_id)
    if referenced_evidence != evidence_ids:
        unused = sorted(evidence_ids - referenced_evidence)
        raise DiagramError(f"evidence entries are unused: {', '.join(unused)}")

    profile = raw.get("profile")
    if profile is not None:
        profile = _object(profile, "profile", {"type"})
        if schema_version != 2 or diagram_type != "architecture" or profile["type"] != "deployment-ownership":
            raise DiagramError("profile.type deployment-ownership is supported only for schema_version 2 architecture diagrams")
        if not groups or {member for group in groups for member in group["members"]} != entity_ids:
            raise DiagramError("deployment-ownership profile requires every component to belong to exactly one evidenced boundary")
        if any(group["certainty"] != "confirmed" or not group["evidence_ids"] for group in groups):
            raise DiagramError("deployment-ownership boundaries must be confirmed directly by source evidence")
        evidence_by_id = {item["id"]: item for item in evidence}
        if any(
            evidence_by_id[evidence_id].get("origin", "repository") != "repository"
            for group in groups
            for evidence_id in group["evidence_ids"]
        ):
            raise DiagramError("deployment-ownership boundaries cannot use brief-only evidence")

    snapshots: dict[str, dict[str, Any]] = {}
    has_repository_evidence = any(item.get("origin", "repository") == "repository" for item in evidence)
    if repo_root is None and require_repository_sources and has_repository_evidence:
        raise DiagramError("repository evidence requires --repo-root; brief-only diagrams do not")
    for item in evidence:
        if item.get("origin", "repository") == "brief":
            snapshots[item["id"]] = {
                **item,
                "sha256": hashlib.sha256(item["claim"].encode("utf-8")).hexdigest(),
            }
    if repo_root is not None:
        root = repo_root.resolve(strict=True)

        def git_bytes(*args: str) -> bytes | None:
            try:
                result = subprocess.run(
                    ["git", "-C", str(root), *args],
                    check=False,
                    capture_output=True,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                raise DiagramError("git source snapshot could not be read") from error
            return result.stdout if result.returncode == 0 else None

        revision_bytes = git_bytes("--no-replace-objects", "rev-parse", "--verify", "HEAD^{commit}")
        revision = revision_bytes.decode("ascii", errors="ignore").strip() if revision_bytes else ""
        if not SHA_PATTERN.fullmatch(revision):
            raise DiagramError("Git source snapshot could not resolve an immutable HEAD commit")

        for item in evidence:
            if item.get("origin", "repository") == "brief":
                continue
            path = root.joinpath(*PurePosixPath(item["path"]).parts)
            try:
                resolved = path.resolve(strict=True)
            except OSError as error:
                raise DiagramError(f"{item['id']} source path cannot be resolved: {item['path']}") from error
            if not resolved.is_relative_to(root) or not resolved.is_file():
                raise DiagramError(f"{item['id']} source path must be a regular file inside the repository")
            data = resolved.read_bytes()
            lines = data.splitlines(keepends=True)
            if item["end_line"] > len(lines):
                raise DiagramError(f"{item['id']} line range exceeds {item['path']}")
            excerpt = b"".join(lines[item["start_line"] - 1 : item["end_line"]])
            committed = git_bytes("--no-replace-objects", "show", f"{revision}:{item['path']}")
            committed_digest = hashlib.sha256(committed).hexdigest() if committed is not None else None
            file_digest = hashlib.sha256(data).hexdigest()
            snapshots[item["id"]] = {
                **item,
                "sha256": hashlib.sha256(excerpt).hexdigest(),
                "file_sha256": file_digest,
                "snapshot": "committed" if committed_digest == file_digest else "working-tree",
                "committed_file_sha256": committed_digest,
            }

    return {
        "schema_version": schema_version,
        "type": diagram_type,
        "language": language,
        "title": title,
        "summary": summary,
        "entities": entities,
        "edges": edges,
        "groups": groups,
        "evidence": evidence,
        "snapshots": snapshots,
        "layout": layout,
        "profile": profile,
        "views": views,
    }


def git_context(repo_root: Path | None) -> dict[str, Any]:
    """Read the exact repository identity and whether its worktree is dirty."""
    if repo_root is None:
        return {
            "name": "User brief",
            "revision": None,
            "dirty": None,
            "changed_paths": [],
            "changed_paths_truncated": False,
            "origin": None,
        }
    root = repo_root.resolve(strict=True)

    def git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise DiagramError("git metadata could not be read") from error
        if result.returncode != 0:
            raise DiagramError("diagram output requires a Git repository")
        return result.stdout.strip()

    git_root = Path(git("rev-parse", "--show-toplevel")).resolve(strict=True)
    if git_root != root:
        raise DiagramError("repo-root must be the Git repository root")
    revision = git("rev-parse", "HEAD")
    if not SHA_PATTERN.fullmatch(revision):
        raise DiagramError("Git returned an invalid HEAD revision")
    try:
        status_result = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiagramError("git worktree status could not be read") from error
    if status_result.returncode != 0:
        raise DiagramError("git worktree status could not be read")
    status = status_result.stdout
    changed_paths = []
    for line in status.splitlines():
        if len(line) >= 4:
            path = line[3:]
            if " -> " in path:
                path = path.rsplit(" -> ", 1)[1]
            changed_paths.append(path)
    changed_paths = sorted(set(changed_paths))
    origin = None
    try:
        origin_result = subprocess.run(
            ["git", "-C", str(root), "config", "--get", "remote.origin.url"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiagramError("Git origin metadata could not be read") from error
    if origin_result.returncode == 0:
        value = origin_result.stdout.strip()
        try:
            if "://" in value:
                parsed = urlsplit(value)
                if parsed.hostname and parsed.scheme in {"http", "https", "ssh", "git"}:
                    hostname = parsed.hostname.lower()
                    if ":" in hostname and not hostname.startswith("["):
                        hostname = f"[{hostname}]"
                    if parsed.port is not None:
                        hostname = f"{hostname}:{parsed.port}"
                    origin = f"{hostname}{parsed.path}".rstrip("/")
            else:
                match = re.fullmatch(r"(?:[^@/]+@)?([^:/]+):([^?#]+)", value)
                if match:
                    origin = f"{match.group(1)}/{match.group(2)}".rstrip("/")
        except ValueError:
            origin = None
    return {
        "name": root.name,
        "revision": revision,
        "dirty": bool(status),
        "changed_paths": changed_paths[:500],
        "changed_paths_truncated": len(changed_paths) > 500,
        "origin": origin,
    }


def parse_json(data: bytes) -> Any:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise DiagramError(f"JSON repeats object key {key!r}")
            result[key] = value
        return result

    try:
        raw = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiagramError(f"invalid UTF-8 JSON: {error}") from error
    return raw


def load_json(path: Path) -> tuple[Any, bytes]:
    with path.open("rb") as source:
        data = source.read(MAX_SOURCE_JSON_BYTES + 1)
    if len(data) > MAX_SOURCE_JSON_BYTES:
        raise DiagramError("diagram source JSON exceeds the 1 MB limit")
    return parse_json(data), data
