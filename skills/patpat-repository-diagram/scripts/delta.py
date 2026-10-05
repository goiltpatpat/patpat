#!/usr/bin/env python3
"""Compare two validated architecture snapshots by authored stable IDs."""

from __future__ import annotations

from typing import Any

from model import DiagramError


def _index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in items}


def _changes(before: list[dict[str, Any]], after: list[dict[str, Any]], fields: tuple[str, ...], kind: str) -> list[dict[str, Any]]:
    left, right = _index(before), _index(after)
    result = []
    for identifier in sorted(left.keys() | right.keys()):
        if identifier not in left:
            result.append({"category": "added", "kind": kind, "id": identifier, "after": right[identifier]})
        elif identifier not in right:
            result.append({"category": "removed", "kind": kind, "id": identifier, "before": left[identifier]})
        else:
            changed = [field for field in fields if left[identifier].get(field) != right[identifier].get(field)]
            if changed:
                category = "rerouted" if kind == "relationship" and {"source", "target"} & set(changed) else "changed"
                result.append({
                    "category": category,
                    "kind": kind,
                    "id": identifier,
                    "fields": changed,
                    "before": {field: left[identifier].get(field) for field in changed},
                    "after": {field: right[identifier].get(field) for field in changed},
                })
    return result


def _layer_positions(spec: dict[str, Any]) -> dict[str, tuple[int, int]] | None:
    layers = spec["layout"]["layers"]
    if layers is None:
        return None
    return {identifier: (rank, position) for rank, layer in enumerate(layers) for position, identifier in enumerate(layer)}


def compare_architecture(base: dict[str, Any], head: dict[str, Any], base_receipt: dict[str, Any], head_receipt: dict[str, Any]) -> dict[str, Any]:
    if base["type"] != "architecture" or head["type"] != "architecture":
        raise DiagramError("architecture comparison accepts architecture diagrams only")
    base_repository = base_receipt.get("repository", {})
    head_repository = head_receipt.get("repository", {})
    base_origin, head_origin = base_repository.get("origin"), head_repository.get("origin")
    if not isinstance(base_origin, str) or not base_origin or not isinstance(head_origin, str) or not head_origin:
        raise DiagramError("architecture comparison requires a non-empty sanitized repository origin in both snapshots")
    if base_origin != head_origin:
        raise DiagramError("architecture snapshots must identify the same sanitized repository origin")
    if not isinstance(base_repository.get("name"), str) or not base_repository.get("name") or base_repository.get("name") != head_repository.get("name"):
        raise DiagramError("architecture snapshots must identify the same repository name")

    changes = []
    changes.extend(_changes(
        base["entities"], head["entities"],
        ("label", "kind", "certainty", "evidence_ids", "reason"), "component",
    ))
    changes.extend(_changes(
        base["edges"], head["edges"],
        ("source", "target", "label", "kind", "certainty", "evidence_ids", "feedback"), "relationship",
    ))
    changes.extend(_changes(
        base["groups"], head["groups"],
        ("label", "members", "certainty", "evidence_ids", "reason"), "boundary",
    ))

    before_layout, after_layout = base["layout"], head["layout"]
    if before_layout["direction"] != after_layout["direction"]:
        changes.append({
            "category": "changed", "kind": "layout", "id": "direction",
            "before": before_layout["direction"], "after": after_layout["direction"],
        })
    before_positions, after_positions = _layer_positions(base), _layer_positions(head)
    if (before_positions is None) != (after_positions is None):
        changes.append({
            "category": "changed", "kind": "layout", "id": "authored-layers",
            "before": "unspecified" if before_positions is None else "specified",
            "after": "unspecified" if after_positions is None else "specified",
        })
    before_geometry, after_geometry = before_layout.get("positions"), after_layout.get("positions")
    if (before_geometry is None) != (after_geometry is None):
        changes.append({
            "category": "changed", "kind": "layout", "id": "authored-geometry",
            "before": "automatic" if before_geometry is None else "authored",
            "after": "automatic" if after_geometry is None else "authored",
        })
    before_entities, after_entities = _index(base["entities"]), _index(head["entities"])
    for identifier in sorted(before_entities.keys() & after_entities.keys()):
        before_position = before_positions.get(identifier) if before_positions is not None else None
        after_position = after_positions.get(identifier) if after_positions is not None else None
        before_xy = before_geometry.get(identifier) if before_geometry is not None else None
        after_xy = after_geometry.get(identifier) if after_geometry is not None else None
        layer_moved = before_position is not None and after_position is not None and before_position != after_position
        geometry_moved = before_xy is not None and after_xy is not None and before_xy != after_xy
        if not layer_moved and not geometry_moved:
            continue
        record = {"category": "moved", "kind": "component", "id": identifier}
        if layer_moved:
            record.update({
                "before_layer": before_position[0], "before_position": before_position[1],
                "after_layer": after_position[0], "after_position": after_position[1],
            })
        if geometry_moved:
            record.update({"before_geometry": before_xy, "after_geometry": after_xy})
        changes.append(record)

    before_hints, after_hints = before_layout.get("edge_hints", {}), after_layout.get("edge_hints", {})
    shared_edge_ids = _index(base["edges"]).keys() & _index(head["edges"]).keys()
    for identifier in sorted(shared_edge_ids):
        before_hint, after_hint = before_hints.get(identifier, {}), after_hints.get(identifier, {})
        before_route = {key: before_hint[key] for key in ("source_side", "target_side", "waypoints") if key in before_hint}
        after_route = {key: after_hint[key] for key in ("source_side", "target_side", "waypoints") if key in after_hint}
        if before_route != after_route:
            changes.append({
                "category": "rerouted", "kind": "relationship", "id": identifier,
                "before": before_route or "automatic", "after": after_route or "automatic",
            })
        before_label, after_label = before_hint.get("label"), after_hint.get("label")
        if before_label != after_label:
            changes.append({
                "category": "changed", "kind": "label-layout", "id": identifier,
                "before": before_label or "automatic", "after": after_label or "automatic",
            })
    if base.get("profile") != head.get("profile"):
        changes.append({"category": "changed", "kind": "profile", "id": "profile", "before": base.get("profile"), "after": head.get("profile")})

    category_order = {"added": 0, "removed": 1, "changed": 2, "moved": 3, "rerouted": 4}
    changes.sort(key=lambda item: (category_order[item["category"]], item["kind"], item["id"]))
    counts = {name: sum(item["category"] == name for item in changes) for name in category_order}
    return {
        "schema_version": 1,
        "kind": "architecture-delta",
        "base": {
            "title": base["title"],
            "revision": base_repository.get("revision"),
            "artifact_sha256": base_receipt.get("outputs", {}).get("html"),
        },
        "head": {
            "title": head["title"],
            "revision": head_repository.get("revision"),
            "artifact_sha256": head_receipt.get("outputs", {}).get("html"),
        },
        "counts": counts,
        "changes": changes,
        "limits": [
            "Shows authored structural differences between the supplied snapshots.",
            "Does not infer downstream impact, risk, deployment status, or merge safety.",
        ],
    }
