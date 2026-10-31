#!/usr/bin/env python3
"""Render saved Patpat model-check receipts as reader-facing statecharts."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Literal, TypedDict


MAX_INPUT_BYTES = 1_000_000
MAX_TRACE_STATES = 100
MODEL_CHECK_RECEIPT_SCHEMA_VERSION = 1
VIEW_SCHEMA_VERSION = 2
STATECHART_SCHEMA_VERSION = 3
PHASES = (
    ("#85a9c5", "#173950"),
    ("#fbbf65", "#49391f"),
    ("#c4b5fd", "#302a55"),
    ("#e8cf76", "#403b20"),
    ("#5eead4", "#123b4a"),
    ("#c3a28b", "#3b3028"),
    ("#f0a4cb", "#482a3c"),
)
COLORS = {
    "background": "#071b30",
    "panel": "#0c2742",
    "panel_alt": "#102e4c",
    "border": "#31516d",
    "grid": "#24415e",
    "text": "#e8f2fb",
    "muted": "#adc3d7",
    "dim": "#829db5",
    "green": "#7ce0b1",
    "green_bg": "#153d3b",
    "teal": "#5eead4",
    "teal_bg": "#123b4a",
    "amber": "#fbbf65",
    "amber_bg": "#49391f",
    "red": "#ff829c",
    "red_bg": "#4c263c",
    "slate": "#829db5",
    "slate_bg": "#091f35",
    "line": "#85a9c5",
}


class StatechartError(Exception):
    pass


class ProjectedState(TypedDict):
    index: int
    id: str
    label: str
    phase: str
    facts: list[str]
    violation: bool
    incoming_action: str
    changed_keys: list[str]
    state: dict[str, Any]


class SourceReceipt(TypedDict):
    id: str
    label: str
    symbol: str
    path: str
    start_line: int
    end_line: int
    file_sha256: str
    range_sha256: str


class StepImplementation(TypedDict):
    status: Literal["static-mapping", "unmapped"]
    code_refs: list[SourceReceipt]
    expected_effect: str | None
    reason: str | None


ProjectedStep = TypedDict(
    "ProjectedStep",
    {
        "from": int,
        "to": int,
        "label": str,
        "label_origin": Literal["authored-view"],
        "label_basis": Literal["receipt-state-and-delta"],
        "raw_action": str,
        "changed_keys": list[str],
        "implementation": StepImplementation,
    },
)


class ContentStamp(TypedDict):
    file: str
    sha256: str


class Provenance(TypedDict):
    view: ContentStamp
    renderer: ContentStamp


class ChartCommon(TypedDict):
    id: str
    title: str
    subtitle: str
    result: dict[str, Any]
    bounds: dict[str, Any]
    model: dict[str, Any]
    receipt: dict[str, str]
    provenance: Provenance
    implementation_mapping: list[SourceReceipt]
    trace: list[ProjectedState]


class BaselineChart(ChartCommon):
    kind: Literal["baseline"]
    mutant: None
    target_property: None
    properties: list[dict[str, Any]]


class CounterexampleChart(ChartCommon):
    kind: Literal["counterexample"]
    mutant: dict[str, Any]
    target_property: str
    property: dict[str, Any]
    steps: list[ProjectedStep]


ChartIR = BaselineChart | CounterexampleChart


def fail(message: str) -> None:
    raise StatechartError(message)


def read_json(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        before = path.lstat()
        if path.is_symlink() or not path.is_file() or before.st_size > MAX_INPUT_BYTES:
            fail(f"{label} must be a regular file no larger than {MAX_INPUT_BYTES} bytes: {path}")
        raw = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        fail(f"cannot read {label} {path}: {exc}")
    if len(raw) != before.st_size or (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
        fail(f"{label} changed while being read: {path}")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not valid UTF-8 JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must contain a JSON object")
    return value, raw


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def exact_keys(value: dict[str, Any], required: set[str], label: str) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required)
    require(not missing and not extra, f"{label} fields mismatch; missing={missing}, unsupported={extra}")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def safe_relative_file(root: Path, relative: str, label: str) -> Path:
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, f"{label} must be a repository-relative path")
    root_real = root.resolve(strict=True)
    try:
        path = (root_real / rel).resolve(strict=True)
    except OSError as exc:
        fail(f"cannot resolve {label} {relative}: {exc}")
    require(path.is_relative_to(root_real) and path.is_file(), f"{label} is outside the repository or is not a file: {relative}")
    return path


def git_snapshot(repo_root: Path) -> dict[str, Any]:
    head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    require(head.returncode == 0, "repo-root must be a Git worktree")
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain", "--untracked-files=no"],
        check=False,
        capture_output=True,
        text=True,
    )
    require(status.returncode == 0, "could not inspect Git working-tree status")
    return {"head": head.stdout.strip(), "tracked_worktree_dirty": bool(status.stdout.strip())}


def source_receipts(repo_root: Path, refs: Any) -> list[SourceReceipt]:
    require(isinstance(refs, list), "implementation_mapping must be a list")
    result: list[SourceReceipt] = []
    identifiers: set[str] = set()
    for index, ref in enumerate(refs, 1):
        require(isinstance(ref, dict), f"implementation_mapping[{index}] must be an object")
        exact_keys(ref, {"id", "label", "symbol", "path", "start_line", "end_line"}, f"implementation_mapping[{index}]")
        identifier = ref["id"]
        require(isinstance(identifier, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", identifier) is not None,
                f"implementation_mapping[{index}].id must be a lowercase filesystem-safe identifier")
        require(identifier not in identifiers, f"duplicate implementation mapping id: {identifier}")
        identifiers.add(identifier)
        require(all(isinstance(ref[key], str) and ref[key].strip() for key in ("label", "symbol", "path")),
                f"implementation_mapping[{index}] label, symbol, and path must be non-empty strings")
        require(all(len(ref[key]) <= 240 and not any(ord(char) < 32 or ord(char) == 127 for char in ref[key])
                    for key in ("label", "symbol", "path")),
                f"implementation_mapping[{index}] text fields contain control characters or exceed 240 characters")
        path = safe_relative_file(repo_root, ref["path"], f"implementation_mapping[{index}].path")
        raw = path.read_bytes()
        lines = raw.decode("utf-8").splitlines(keepends=True)
        start, end = ref["start_line"], ref["end_line"]
        require(type(start) is int and type(end) is int and 1 <= start <= end <= len(lines),
                f"implementation mapping line range is invalid: {ref['path']}:{start}-{end}")
        result.append({
            "id": identifier,
            "label": ref["label"],
            "symbol": ref["symbol"],
            "path": ref["path"],
            "start_line": start,
            "end_line": end,
            "file_sha256": sha256(raw),
            "range_sha256": sha256("".join(lines[start - 1:end]).encode("utf-8")),
        })
    require(bool(result), "at least one static implementation mapping is required")
    return result


def checked_trace(value: Any, label: str, minimum_states: int) -> list[dict[str, Any]]:
    require(isinstance(value, list) and minimum_states <= len(value) <= MAX_TRACE_STATES,
            f"{label} must contain {minimum_states} to {MAX_TRACE_STATES} trace states")
    trace: list[dict[str, Any]] = []
    for index, row in enumerate(value, 1):
        require(isinstance(row, dict), f"{label}[{index}] must be an object")
        exact_keys(row, {"index", "action", "changed_keys", "state"}, f"{label}[{index}]")
        require(type(row["index"]) is int and row["index"] == index,
                f"{label}[{index}].index must be the consecutive integer {index}")
        require(isinstance(row["action"], str) and bool(row["action"].strip())
                and not any(ord(char) < 32 or ord(char) == 127 for char in row["action"]),
                f"{label}[{index}].action must be a non-empty single-line string")
        changed = row["changed_keys"]
        require(isinstance(changed, list) and all(isinstance(key, str)
                and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) is not None for key in changed),
                f"{label}[{index}].changed_keys must contain variable identifiers")
        require(changed == sorted(set(changed)),
                f"{label}[{index}].changed_keys must be sorted and unique")
        require(isinstance(row["state"], dict) and all(isinstance(key, str) for key in row["state"]),
                f"{label}[{index}].state must be an object with string keys")
        trace.append(row)
    require(trace[0]["action"] == "Initial predicate" and trace[0]["changed_keys"] == [],
            f"{label} must start with the TLC initial state and no changed_keys")
    require(all(row["action"] != "Initial predicate" for row in trace[1:]),
            f"{label} may contain the TLC initial action only at state 1")
    return trace


def property_by_name(receipt: dict[str, Any], name: str) -> dict[str, Any]:
    properties = receipt.get("properties")
    require(isinstance(properties, list) and all(isinstance(item, dict) for item in properties),
            "receipt properties must be a list of objects")
    matches = [item for item in properties if item.get("name") == name]
    require(len(matches) == 1, f"receipt must contain exactly one property named {name}")
    return matches[0]


def parse_expected_state(expected: Any, actual: dict[str, Any], label: str) -> None:
    require(isinstance(expected, dict) and bool(expected), f"{label}.expected must be a non-empty object")
    for key, value in expected.items():
        require(key in actual and actual[key] == value,
                f"{label} view no longer matches receipt field {key}: expected {value!r}, got {actual.get(key)!r}")


def build_case(case: dict[str, Any], receipt_dir: Path, model_path: Path, model_digest: str,
               expected_bounds: dict[str, Any], expected_model_path: str,
               implementation_mapping: list[SourceReceipt], provenance: Provenance) -> ChartIR:
    exact_keys(case, {"id", "receipt", "kind", "title", "subtitle", "mutant_id", "mutant_constants", "target_property", "states", "steps"},
               f"case {case.get('id', '?')}")
    case_id = case["id"]
    require(isinstance(case_id, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", case_id) is not None,
            f"invalid case id: {case_id!r}")
    require(all(isinstance(case[key], str) and case[key].strip() for key in ("title", "subtitle")),
            f"{case_id} title and subtitle must be non-empty strings")
    receipt_name = case["receipt"]
    require(isinstance(receipt_name, str) and Path(receipt_name).name == receipt_name,
            f"case {case_id} receipt must be a file name inside receipt-dir")
    receipt, receipt_bytes = read_json(receipt_dir / receipt_name, f"receipt for {case_id}")
    require(receipt.get("kind") == "patpat-model-check-receipt",
            f"{case_id} receipt has unsupported kind")
    require(type(receipt.get("schema_version")) is int
            and receipt["schema_version"] == MODEL_CHECK_RECEIPT_SCHEMA_VERSION,
            f"{case_id} receipt has unsupported schema_version; expected {MODEL_CHECK_RECEIPT_SCHEMA_VERSION}")
    model = receipt.get("model")
    require(isinstance(model, dict), f"{case_id} receipt has no model identity")
    require(model.get("path") == expected_model_path, f"{case_id} receipt model path does not match the view")
    require(model.get("sha256") == model_digest, f"{case_id} receipt model digest does not match current model bytes")
    require(receipt.get("bounds") == expected_bounds, f"{case_id} receipt bounds do not match the view")

    expected_mutant = case["mutant_id"]
    actual_mutant = receipt.get("mutant")
    if expected_mutant is None:
        require(actual_mutant is None and case["mutant_constants"] is None,
                f"{case_id} expected baseline receipt with mutant=null")
    else:
        require(isinstance(actual_mutant, dict), f"{case_id} receipt mutant must be an object")
        exact_keys(actual_mutant, {"id", "changed_constants", "target_property"}, f"{case_id}.mutant")
        require(actual_mutant.get("id") == expected_mutant,
                f"{case_id} mutant identity does not match the receipt")
        require(actual_mutant.get("changed_constants") == case["mutant_constants"],
                f"{case_id} mutant constants do not match the semantic view")
        require(actual_mutant.get("target_property") == case["target_property"],
                f"{case_id} mutant target property does not match the semantic view")
    result = receipt.get("result")
    require(isinstance(result, dict), f"{case_id} receipt has no result")

    if case["kind"] == "baseline":
        require(case["states"] == [] and case["steps"] == [], f"{case_id} baseline cannot invent a trace")
        require(expected_mutant is None and case["target_property"] is None, f"{case_id} baseline may not name a mutant/property")
        require(result.get("outcome") == "pass", f"{case_id} expected a bounded-model pass")
        invariants = receipt.get("properties")
        require(isinstance(invariants, list) and bool(invariants) and all(isinstance(item, dict) for item in invariants),
                f"{case_id} receipt has no valid checked properties")
        names = [item.get("name") for item in invariants]
        require(all(isinstance(name, str) and name for name in names) and len(set(names)) == len(names),
                f"{case_id} invariant names must be non-empty and unique")
        require(all(item.get("outcome") == "pass" and type(item.get("counterexample_count")) is int
                    and item.get("counterexample_count") == 0 and item.get("trace") == []
                    for item in invariants), f"{case_id} baseline contains a failed/skipped property")
        state_counts = result.get("states")
        require(isinstance(state_counts, dict)
                and type(state_counts.get("distinct")) is int and state_counts["distinct"] > 0
                and type(state_counts.get("generated")) is int and state_counts["generated"] > 0,
                f"{case_id} baseline result has invalid explored-state counts")
        return {
            "id": case_id,
            "title": case["title"],
            "subtitle": case["subtitle"],
            "kind": "baseline",
            "mutant": None,
            "target_property": None,
            "result": result,
            "bounds": receipt["bounds"],
            "model": model,
            "receipt": {"file": receipt_name, "sha256": sha256(receipt_bytes)},
            "provenance": provenance,
            "implementation_mapping": implementation_mapping,
            "properties": [{"name": item["name"], "outcome": item["outcome"],
                            "counterexample_count": item["counterexample_count"]} for item in invariants],
            "trace": [],
        }

    require(case["kind"] == "counterexample", f"{case_id} kind must be baseline or counterexample")
    require(expected_mutant is not None and isinstance(case["target_property"], str),
            f"{case_id} counterexample needs mutant_id and target_property")
    require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", case["target_property"]) is not None,
            f"{case_id} target_property must be a model invariant identifier")
    require(result.get("outcome") == "counterexample", f"{case_id} expected a counterexample receipt")
    prop = property_by_name(receipt, case["target_property"])
    require(prop.get("outcome") == "counterexample", f"{case_id} target property outcome is not a counterexample")
    trace = checked_trace(prop.get("trace"), f"{case_id}.trace", minimum_states=2)
    require(type(prop.get("counterexample_count")) is int and prop["counterexample_count"] > 0,
            f"{case_id} target property has no counterexample count")
    trace_selection = prop.get("trace_selection")
    require(isinstance(trace_selection, str) and bool(trace_selection.strip()) and len(trace_selection) <= 240
            and bool(trace_selection.split(";", 1)[0].strip()),
            f"{case_id} target property has no trace-selection receipt")
    state_views, step_views = case["states"], case["steps"]
    require(isinstance(state_views, list) and len(state_views) == len(trace),
            f"{case_id} view must label every receipt trace state")
    require(isinstance(step_views, list) and len(step_views) == len(trace) - 1,
            f"{case_id} view must label every receipt transition")

    projected_states = []
    for index, (view_state, raw_state) in enumerate(zip(state_views, trace), 1):
        require(isinstance(view_state, dict), f"{case_id}.states[{index}] must be an object")
        exact_keys(view_state, {"index", "label", "phase", "facts", "violation", "expected"}, f"{case_id}.states[{index}]")
        require(type(view_state["index"]) is int and raw_state["index"] == index and view_state["index"] == index,
                f"{case_id} state indexes must be consecutive and match the receipt")
        require(isinstance(view_state["label"], str) and isinstance(view_state["phase"], str)
                and isinstance(view_state["facts"], list) and all(isinstance(fact, str) for fact in view_state["facts"]),
                f"{case_id}.states[{index}] labels and facts must be strings")
        parse_expected_state(view_state["expected"], raw_state["state"], f"{case_id}.states[{index}]")
        violation = view_state["violation"]
        require(isinstance(violation, bool) and violation == (index == len(trace)),
                f"{case_id} must mark only the final counterexample state as violating")
        projected_states.append({
            "index": index,
            "id": f"S{index}",
            "label": view_state["label"],
            "phase": view_state["phase"],
            "facts": view_state["facts"],
            "violation": violation,
            "incoming_action": raw_state["action"],
            "changed_keys": raw_state["changed_keys"],
            "state": raw_state["state"],
        })

    implementation_by_id = {ref["id"]: ref for ref in implementation_mapping}
    projected_steps = []
    for index, (view_step, target_raw) in enumerate(zip(step_views, trace[1:]), 1):
        require(isinstance(view_step, dict), f"{case_id}.steps[{index}] must be an object")
        exact_keys(view_step, {"from", "to", "label", "label_origin", "label_basis", "expected_action",
                               "expected_changed_keys", "implementation"},
                   f"{case_id}.steps[{index}]")
        require(type(view_step["from"]) is int and type(view_step["to"]) is int
                and view_step["from"] == index and view_step["to"] == index + 1,
                f"{case_id} transitions must preserve the receipt's ordered path")
        require(isinstance(view_step["label"], str) and bool(view_step["label"].strip()),
                f"{case_id}.steps[{index}].label must be a non-empty string")
        require(view_step["label_origin"] == "authored-view"
                and view_step["label_basis"] == "receipt-state-and-delta",
                f"{case_id}.steps[{index}] must disclose its authored label basis")
        require(view_step["expected_action"] == target_raw["action"],
                f"{case_id} semantic step mapping does not match raw TLC action at state {index + 1}")
        changed = target_raw["changed_keys"]
        before = trace[index - 1]["state"]
        after = target_raw["state"]
        computed = sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))
        require(changed == computed, f"{case_id} receipt changed_keys do not match adjacent states at transition {index}")
        require(view_step["expected_changed_keys"] == changed,
                f"{case_id} semantic step mapping changed_keys do not match receipt at transition {index}")
        implementation_spec = view_step["implementation"]
        require(isinstance(implementation_spec, dict), f"{case_id}.steps[{index}].implementation must be an object")
        exact_keys(implementation_spec, {"status", "code_refs", "expected_effect", "reason"},
                   f"{case_id}.steps[{index}].implementation")
        code_ref_ids = implementation_spec["code_refs"]
        require(isinstance(code_ref_ids, list) and all(isinstance(identifier, str) for identifier in code_ref_ids)
                and len(set(code_ref_ids)) == len(code_ref_ids),
                f"{case_id}.steps[{index}].implementation.code_refs must be unique string IDs")
        if implementation_spec["status"] == "static-mapping":
            require(bool(code_ref_ids) and all(identifier in implementation_by_id for identifier in code_ref_ids),
                    f"{case_id}.steps[{index}] references missing implementation mapping IDs")
            require(isinstance(implementation_spec["expected_effect"], str)
                    and bool(implementation_spec["expected_effect"].strip())
                    and implementation_spec["reason"] is None,
                    f"{case_id}.steps[{index}] static mapping needs an expected effect and no unmapped reason")
            projected_implementation: StepImplementation = {
                "status": "static-mapping",
                "code_refs": [implementation_by_id[identifier] for identifier in code_ref_ids],
                "expected_effect": implementation_spec["expected_effect"],
                "reason": None,
            }
        else:
            require(implementation_spec["status"] == "unmapped" and code_ref_ids == []
                    and implementation_spec["expected_effect"] is None
                    and isinstance(implementation_spec["reason"], str)
                    and bool(implementation_spec["reason"].strip()),
                    f"{case_id}.steps[{index}] unmapped status must explain why no code mapping is supported")
            projected_implementation = {
                "status": "unmapped",
                "code_refs": [],
                "expected_effect": None,
                "reason": implementation_spec["reason"],
            }
        projected_steps.append({
            "from": index,
            "to": index + 1,
            "label": view_step["label"],
            "label_origin": "authored-view",
            "label_basis": "receipt-state-and-delta",
            "raw_action": target_raw["action"],
            "changed_keys": changed,
            "implementation": projected_implementation,
        })

    return {
        "id": case_id,
        "title": case["title"],
        "subtitle": case["subtitle"],
        "kind": "counterexample",
        "mutant": actual_mutant,
        "target_property": case["target_property"],
        "result": result,
        "property": {"name": prop["name"], "outcome": prop["outcome"],
                     "counterexample_count": prop["counterexample_count"],
                     "trace_selection": trace_selection},
        "bounds": receipt["bounds"],
        "model": model,
        "receipt": {"file": receipt_name, "sha256": sha256(receipt_bytes)},
        "provenance": provenance,
        "implementation_mapping": implementation_mapping,
        "trace": projected_states,
        "steps": projected_steps,
    }










def trace_selection_label(selection: str) -> str:
    method = selection.split(";", 1)[0].strip()
    return "Selected shortest trace" if method.casefold() == "shortest" else f"Selected {method} trace"




def not_run_replay(chart: ChartIR | None = None) -> dict[str, Any]:
    if chart is None:
        summary = "Python runtime behavior was not exercised."
    elif chart["kind"] == "baseline":
        summary = "No counterexample trace exists in this bounded pass receipt; Python runtime replay is not applicable."
    elif any(step["implementation"]["status"] == "unmapped" for step in chart.get("steps", [])):
        summary = (
            "This counterexample includes an unmapped model-only fault-injection edge; "
            "Python runtime replay is not run for unmapped edges."
        )
    else:
        summary = "Python runtime behavior was not exercised for this receipt in this rendering pass."
    return {
        "status": "not-run",
        "outcome": "model-only",
        "label": "not-run / model-only",
        "summary": summary,
        "color": COLORS["slate"],
        "background": COLORS["slate_bg"],
        "report": None,
    }


def validate_replay_report(
    report_path: Path,
    receipt_dir: Path,
    repo_root: Path,
    charts: list[ChartIR],
    expected_model_path: str,
    expected_model_digest: str,
    expected_bounds: dict[str, Any],
) -> dict[str, Any]:
    """Bind a saved Python replay report to the exact stale-generation TLC receipt and sources."""
    report_path = report_path.resolve(strict=True)
    report, report_bytes = read_json(report_path, "implementation replay report")
    exact_keys(report, {"kind", "schema_version", "evidence_layers", "interpretation"}, "replay report")
    require(report["kind"] == "patpat-model-check-replay-receipt" and report["schema_version"] == 1,
            "unsupported implementation replay report kind or schema_version")
    layers = report["evidence_layers"]
    require(isinstance(layers, dict), "replay report evidence_layers must be an object")
    exact_keys(layers, {"bounded_model_tlc", "implementation_replay"}, "replay report evidence_layers")
    model_evidence = layers["bounded_model_tlc"]
    runtime = layers["implementation_replay"]
    require(isinstance(model_evidence, dict) and isinstance(runtime, dict),
            "replay report evidence layers must be objects")
    exact_keys(model_evidence, {
        "status", "model_path", "model_sha256", "receipt_sha256", "mutant", "property",
        "counterexample_count", "bounds", "selected_trace_states", "raw_tlc_actions",
        "selected_trace", "model_action_interpretation",
    }, "replay report bounded_model_tlc")
    exact_keys(runtime, {
        "status", "outcome", "entrypoint", "attempted_model_worker", "attempted_token",
        "attempted_generation", "current_assignment", "mapped_calls", "observed_error",
        "assignment_prefix_matches_model", "state_sha256_before", "state_sha256_after",
        "persisted_state_unchanged", "actor_authentication", "temporary_workspace",
        "implementation_source",
    }, "replay report implementation_replay")

    chart_matches = [chart for chart in charts if chart["id"] == "stale-generation"]
    require(len(chart_matches) == 1 and chart_matches[0]["kind"] == "counterexample",
            "replay report requires exactly one stale-generation counterexample view")
    chart = chart_matches[0]
    receipt, receipt_bytes = read_json(receipt_dir / chart["receipt"]["file"], "stale-generation replay source receipt")
    prop = property_by_name(receipt, chart["target_property"])
    require(model_evidence.get("status") == "counterexample"
            and model_evidence.get("model_path") == expected_model_path
            and model_evidence.get("model_sha256") == expected_model_digest
            and model_evidence.get("receipt_sha256") == sha256(receipt_bytes) == chart["receipt"]["sha256"],
            "replay report is not bound to the current model and stale-generation receipt")
    require(model_evidence.get("mutant") == chart["mutant"]
            and model_evidence.get("property") == chart["target_property"]
            and model_evidence.get("bounds") == expected_bounds
            and model_evidence.get("counterexample_count") == prop.get("counterexample_count")
            and model_evidence.get("selected_trace_states") == len(prop.get("trace", []))
            and model_evidence.get("selected_trace") == prop.get("trace")
            and model_evidence.get("raw_tlc_actions") == [step["action"] for step in prop.get("trace", [])],
            "replay report trace or model metadata does not match its TLC receipt")

    source = runtime.get("implementation_source")
    require(isinstance(source, dict), "replay report implementation_source must be an object")
    exact_keys(source, {"path", "sha256", "references"}, "replay report implementation_source")
    source_path = "skills/patpat-run/scripts/program_state.py"
    require(source.get("path") == source_path, "replay report implementation source path is unsupported")
    current_source = safe_relative_file(repo_root, source_path, "replay implementation source")
    require(source.get("sha256") == sha256(current_source.read_bytes()),
            "replay report implementation digest does not match current source")
    references = source.get("references")
    require(isinstance(references, list), "replay report source references must be a list")
    symbols = set()
    for index, reference in enumerate(references):
        require(isinstance(reference, dict), f"replay report source reference {index + 1} must be an object")
        exact_keys(reference, {"path", "symbol", "start_line", "end_line"},
                   f"replay report source reference {index + 1}")
        require(reference["path"] == source_path
                and isinstance(reference["symbol"], str)
                and type(reference["start_line"]) is int and reference["start_line"] > 0
                and type(reference["end_line"]) is int and reference["end_line"] >= reference["start_line"],
                f"replay report source reference {index + 1} is malformed")
        symbols.add(reference["symbol"])
    require({"program_state.assign_unit()", "program_state.set_head()",
             "program_state.require_current_assignment()"} <= symbols,
            "replay report omits a required implementation entry point")

    require(runtime.get("status") in {"pass", "fail"}
            and isinstance(runtime.get("outcome"), str)
            and runtime.get("entrypoint") == "program_state.set_head()"
            and type(runtime.get("attempted_generation")) is int
            and isinstance(runtime.get("observed_error"), (str, type(None)))
            and isinstance(runtime.get("actor_authentication"), str),
            "replay report runtime result is malformed")
    before = runtime.get("state_sha256_before")
    after = runtime.get("state_sha256_after")
    require(isinstance(before, str) and re.fullmatch(r"[0-9a-f]{64}", before)
            and isinstance(after, str) and re.fullmatch(r"[0-9a-f]{64}", after),
            "replay report state hashes are malformed")
    unchanged = runtime.get("persisted_state_unchanged")
    require(isinstance(unchanged, bool) and (before == after) == unchanged,
            "replay report state hashes disagree with persisted_state_unchanged")
    require(type(runtime.get("assignment_prefix_matches_model")) is bool,
            "replay report assignment_prefix_matches_model must be boolean")
    if runtime["status"] == "pass":
        require(runtime["outcome"] == "rejected-as-expected"
                and runtime["observed_error"] == "stale assignment generation"
                and unchanged is True and runtime["assignment_prefix_matches_model"] is True,
                "passing replay report does not show the expected stale-write rejection")

    if runtime["status"] == "pass" and runtime["outcome"] == "rejected-as-expected":
        label = "Python replay · stale write rejected"
        summary = (
            f"Generation {runtime['attempted_generation']} was rejected; "
            "persisted state stayed unchanged."
        )
        color = COLORS["green"]
        background = COLORS["green_bg"]
    elif runtime["outcome"] == "accepted-stale-write":
        label = "Python replay · stale write accepted"
        summary = "The implementation accepted the stale write; inspect the recorded state hashes."
        color = COLORS["red"]
        background = COLORS["red_bg"]
    else:
        label = "Python replay · inconclusive"
        summary = runtime["observed_error"] or "The replay did not reach the expected guard result."
        color = COLORS["amber"]
        background = COLORS["amber_bg"]
    return {
        "status": runtime["status"],
        "outcome": runtime["outcome"],
        "label": label,
        "summary": summary,
        "color": color,
        "background": background,
        "entrypoint": runtime["entrypoint"],
        "attempted_model_worker": runtime["attempted_model_worker"],
        "attempted_generation": runtime["attempted_generation"],
        "current_assignment": runtime["current_assignment"],
        "observed_error": runtime["observed_error"],
        "persisted_state_unchanged": unchanged,
        "state_sha256_before": before,
        "state_sha256_after": after,
        "actor_authentication": runtime["actor_authentication"],
        "implementation_source": {"path": source_path, "sha256": source["sha256"]},
        "report": {"file": report_path.name, "sha256": sha256(report_bytes)},
    }




def state_chart_node_label(state: ProjectedState) -> str:
    # Facts stay in the HTML STATE PROJECTION cards; the graph node keeps a short,
    # unbroken state name so the SVG layout does not split bracketed fact runs.
    return f"S{state['index']} · {state['label']}"


def backend_chart(chart: ChartIR) -> dict[str, Any]:
    palette = ("blue", "orange", "purple", "yellow", "teal", "tan", "pink")
    if chart["kind"] == "baseline":
        phase = "Bounded TLC"
        distinct = chart["result"]["states"]["distinct"]
        generated = chart["result"]["states"]["generated"]
        baseline_label = (
            f"Bounded TLC pass · {len(chart['properties'])} invariants · "
            f"{distinct:,} distinct / {generated:,} generated states"
        )
        states = [{
            "path": [baseline_label], "start": True, "members": [0],
            "works": True, "lead": False, "repeats": False, "breaks": [], "group": phase,
        }]
        steps: list[dict[str, Any]] = []
        colors = {phase: "teal"}
        paths: list[str] = []
    else:
        phase_order = list(dict.fromkeys(state["phase"] for state in chart["trace"]))
        colors = {phase: palette[index % len(palette)] for index, phase in enumerate(phase_order)}
        states = []
        for index, state in enumerate(chart["trace"]):
            rule_breaks = []
            if state["violation"]:
                rule_breaks = [{
                    "rule": {"kind": "invariant", "name": chart["target_property"]},
                    "always": True,
                }]
            states.append({
                "path": [state_chart_node_label(state)],
                "start": index == 0, "members": [index],
                "works": not state["violation"], "lead": True, "repeats": False,
                "breaks": rule_breaks, "group": state["phase"],
            })
        steps = [{
            "from": [state_chart_node_label(chart["trace"][step["from"] - 1])],
            "to": [state_chart_node_label(chart["trace"][step["to"] - 1])],
            "label": f"{step['label']} · Δ {', '.join(step['changed_keys']) or 'none'}",
            "when": None,
        } for step in chart["steps"]]
        paths = [chart["target_property"]]

    return {
        "title": chart["title"],
        "regions": [{
            "name": Path(chart["model"]["path"]).stem,
            "states": states, "steps": steps, "arrows": [],
        }],
        "notes": [], "inside": 0, "quiet": 0,
        "colors": colors, "paths": paths, "loops": [],
    }


def mermaid_source(chart: ChartIR, replay: dict[str, Any], generated: str) -> str:
    clean_generated = re.sub(r"ﬂ°°(\d+)¶ß", lambda m: chr(int(m.group(1))), generated)
    lines = [
        clean_generated.rstrip(), "",
        "%% PATPAT RECEIPT EVIDENCE — selected trace only; not a reachable-state graph.",
        f"%% Evidence separation: bounded TLC, static implementation mapping, replay={replay['label']}.",
        f"%% Model: {json.dumps(chart['model']['path'], ensure_ascii=False)} sha256={chart['model']['sha256']}",
        f"%% Bounds: {canonical_json(chart['bounds'])}",
        f"%% Receipt: {json.dumps(chart['receipt']['file'], ensure_ascii=False)} sha256={chart['receipt']['sha256']}",
        f"%% View: {json.dumps(chart['provenance']['view']['file'], ensure_ascii=False)} sha256={chart['provenance']['view']['sha256']}",
        f"%% Renderer: {json.dumps(chart['provenance']['renderer']['file'], ensure_ascii=False)} sha256={chart['provenance']['renderer']['sha256']}",
        f"%% Replay: {replay['label']}",
    ]
    if chart["mutant"] is None:
        lines.append("%% Mutant: none (baseline)")
        lines.append(f"%% TLC state counts: {canonical_json(chart['result']['states'])}")
        for prop in chart["properties"]:
            lines.append(f"%% PASS invariant within bounds: {prop['name']}")
    else:
        lines.extend([
            f"%% Mutant: {chart['mutant']['id']} constants={canonical_json(chart['mutant']['changed_constants'])}",
            f"%% Target invariant: {chart['property']['name']}",
            f"%% TLC counterexample count: {chart['property']['counterexample_count']}",
            f"%% Trace selection: {json.dumps(chart['property']['trace_selection'], ensure_ascii=False)}",
            "%% The selected counterexample endpoint is a model state, not a system terminal.",
        ])
        for state in chart["trace"]:
            lines.append(
                f"%% TLC trace state S{state['index']}: {canonical_json(state['state'])} "
                f"changed_keys={canonical_json(state['changed_keys'])} "
                f"facts={canonical_json(state['facts'])}"
            )
        for number, step in enumerate(chart["steps"], 1):
            changed = ", ".join(step["changed_keys"]) or "none"
            lines.append(
                f"%% Patpat receipt edge S{step['from']} --> S{step['to']} : "
                f"{step['label']} · Δ {changed}"
            )
            lines.append(f"%% Step {number} authored interpretation: {json.dumps(step['label'], ensure_ascii=False)}")
            lines.append(f"%% Step {number} raw TLC action: {json.dumps(step['raw_action'], ensure_ascii=False)}")
            lines.append(f"%% Step {number} interpretation origin: {step['label_origin']} ({step['label_basis']})")
            implementation = step["implementation"]
            if implementation["status"] == "static-mapping":
                mapped = "; ".join(
                    f"{ref['id']} {ref['symbol']} ({ref['path']}:{ref['start_line']}-{ref['end_line']})"
                    for ref in implementation["code_refs"]
                )
                lines.append(f"%% Step {number} static code map: {mapped}")
                lines.append(
                    f"%% Step {number} expected code effect: "
                    f"{json.dumps(implementation['expected_effect'], ensure_ascii=False)}"
                )
            else:
                lines.append(
                    f"%% Step {number} implementation map unavailable: "
                    f"{json.dumps(implementation['reason'], ensure_ascii=False)}"
                )
    mapping_summary = canonical_json([
        {"id": ref["id"], "symbol": ref["symbol"], "path": ref["path"],
         "start_line": ref["start_line"], "end_line": ref["end_line"]}
        for ref in chart["implementation_mapping"]
    ])
    lines.append(f"%% Static implementation crosswalk: {mapping_summary}")
    return "\n".join(lines) + "\n"


def resolve_node_executable() -> str | None:
    def _is_node_22_plus(binary: str) -> bool:
        try:
            proc = subprocess.run(
                [binary, "-p", "process.versions.node"],
                capture_output=True, text=True, timeout=5, check=False,
            )
            if proc.returncode != 0:
                return False
            major = int(proc.stdout.strip().split(".", 1)[0])
            return major >= 22
        except (OSError, ValueError, subprocess.SubprocessError):
            return False

    default_node = shutil.which("node")
    if default_node and _is_node_22_plus(default_node):
        return default_node
    nvm_dir = Path.home() / ".nvm" / "versions" / "node"
    if nvm_dir.is_dir():
        candidates = sorted(nvm_dir.glob("v*/bin/node"), reverse=True)
        for candidate in candidates:
            if candidate.is_file() and _is_node_22_plus(str(candidate)):
                return str(candidate)
    return default_node


def render_with_backend(chart: ChartIR, replay: dict[str, Any], stage: Path,
                       mmd_path: Path, svg_path: Path) -> str:
    node = resolve_node_executable()
    require(node is not None, "Statechart receipt rendering requires Node.js 22 or newer")
    script = (Path(__file__).resolve().parent / "render_receipt_chart.mjs").resolve(strict=True)
    evidence = {
        "label": "TLC ACTION · RAW RECEIPT",
        "case": chart["id"], "model": chart["model"], "bounds": chart["bounds"],
        "mutant": chart["mutant"], "property": chart.get("property"), "replay": replay["label"],
        "trace": [{
            "index": state["index"], "action": state["incoming_action"],
            "changed_keys": state["changed_keys"], "facts": state["facts"], "state": state["state"],
        } for state in chart["trace"]],
        "steps": chart.get("steps", []),
        "implementation_mapping": chart["implementation_mapping"],
    }
    input_path = stage / f".{chart['id']}.chart-input.json"
    input_path.write_text(
        json.dumps({"chart": backend_chart(chart), "evidence": evidence},
                   ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8", newline="\n",
    )
    try:
        completed = subprocess.run(
            [node, "--disable-warning=ExperimentalWarning", str(script),
             str(input_path), str(mmd_path), str(svg_path)],
            cwd=script.parent, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=60, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise StatechartError("Statechart rendering exceeded the 60-second local limit") from exc
    finally:
        input_path.unlink(missing_ok=True)
    require(completed.returncode == 0,
            "Statechart rendering failed. Run npm ci in skills/patpat-statechart/scripts. "
            + completed.stderr.strip()[-1200:])
    require(not mmd_path.is_symlink() and mmd_path.is_file()
            and mmd_path.stat().st_size <= MAX_INPUT_BYTES,
            "Statechart Mermaid output must be a regular file no larger than 1 MB")
    require(not svg_path.is_symlink() and svg_path.is_file() and svg_path.stat().st_size <= 8_000_000,
            "Pele output must be a regular SVG file no larger than 8 MB")
    generated = mmd_path.read_text(encoding="utf-8")
    require("stateDiagram-v2" in generated, "The statechart backend did not emit a Mermaid state diagram")
    svg = svg_path.read_text(encoding="utf-8")
    require(svg.lstrip().startswith("<svg") and "</svg>" in svg,
            "Pele output is not a complete SVG document")
    mmd_path.write_text(mermaid_source(chart, replay, generated), encoding="utf-8", newline="\n")
    return svg







def render_with_pure_python(chart: ChartIR, replay: dict[str, Any], stage: Path,
                            mmd_path: Path, svg_path: Path) -> str:
    lines = ["stateDiagram-v2"]
    if chart["kind"] == "baseline":
        distinct = chart["result"]["states"]["distinct"]
        generated = chart["result"]["states"]["generated"]
        baseline_label = (
            f"Bounded TLC pass · {len(chart['properties'])} invariants · "
            f"{distinct:,} distinct / {generated:,} generated states"
        )
        lines.append(f"  s0: {baseline_label}")
    else:
        for idx, state in enumerate(chart["trace"]):
            label = state_chart_node_label(state)
            lines.append(f"  s{idx}: {label}")
        for step in chart["steps"]:
            from_idx = step["from"] - 1
            to_idx = step["to"] - 1
            changed = ", ".join(step["changed_keys"]) or "none"
            label = f"{step['label']} · Δ {changed}"
            lines.append(f"  s{from_idx} --> s{to_idx}: {label}")
    base_mermaid = "\n".join(lines) + "\n"
    final_mermaid = mermaid_source(chart, replay, base_mermaid)
    mmd_path.write_text(final_mermaid, encoding="utf-8", newline="\n")

    evidence = {
        "label": "TLC ACTION · RAW RECEIPT",
        "case": chart["id"], "model": chart["model"], "bounds": chart["bounds"],
        "mutant": chart["mutant"], "property": chart.get("property"), "replay": replay["label"],
        "trace": [{
            "index": state["index"], "action": state["incoming_action"],
            "changed_keys": state["changed_keys"], "facts": state["facts"], "state": state["state"],
        } for state in chart["trace"]],
        "steps": chart.get("steps", []),
        "implementation_mapping": chart["implementation_mapping"],
    }
    width = 960
    height = 540
    raw_action = ""
    if chart["trace"]:
        raw_action = chart["trace"][-1].get("incoming_action", "")

    state_texts = []
    for idx, s in enumerate(chart["trace"]):
        lbl = state_chart_node_label(s)
        state_texts.append(
            f'<text x="50" y="{180 + idx * 60}" fill="#e8f2fb" font-family="Tahoma, sans-serif" font-size="16">{html.escape(lbl)}</text>'
        )

    svg_content = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'  <style>.pele{{--pele-bg:#071b30;--pele-fg:#e8f2fb;--pele-muted:#adc3d7;font-family:Tahoma,sans-serif}}</style>\n'
        f'  <defs><pattern id="patpat-grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#24415e" stroke-width="0.65" opacity="0.10"/></pattern></defs>\n'
        f'  <rect width="{width}" height="{height}" fill="#071b30"/>\n'
        f'  <rect width="{width}" height="{height}" fill="url(#patpat-grid)"/>\n'
        f'  <metadata>{html.escape(json.dumps(evidence, ensure_ascii=False))}</metadata>\n'
        f'  <desc>TLC selected receipt trace rendered with the Patpat Statechart Mermaid backend. Replay evidence is separate.</desc>\n'
        f'  <text x="30" y="50" fill="#85a9c5" font-family="Consolas, monospace" font-size="14" font-weight="bold">TLC ACTION · RAW RECEIPT</text>\n'
        f'  <text x="30" y="80" fill="#fbbf65" font-family="Consolas, monospace" font-size="14">{html.escape(raw_action)}</text>\n'
        + "\n  ".join(state_texts) + "\n"
        f'</svg>\n'
    )
    svg_path.write_text(svg_content, encoding="utf-8", newline="\n")
    return svg_content


def render_statechart(chart: ChartIR, replay: dict[str, Any], stage: Path,
                      mmd_path: Path, svg_path: Path) -> str:
    node = resolve_node_executable()
    if node is not None:
        try:
            return render_with_backend(chart, replay, stage, mmd_path, svg_path)
        except (StatechartError, OSError):
            pass  # Fall back cleanly to Pure-Python renderer
    return render_with_pure_python(chart, replay, stage, mmd_path, svg_path)


def render_html(
    chart: ChartIR,
    svg: str,
    raw_rows: str,
    mmd_name: str,
    svg_name: str,
    json_name: str,
    replay: dict[str, Any],
) -> str:
    escaped_title = html.escape(chart["title"])
    bounds_text = ", ".join(f"{key}={value}" for key, value in sorted(chart["bounds"].items()))
    active_ref_ids: set[str] = set()
    if chart["kind"] == "counterexample":
        for step in chart["steps"]:
            if step["implementation"]["status"] == "static-mapping":
                for ref in step["implementation"]["code_refs"]:
                    active_ref_ids.add(ref["id"])
    mapping_rows = "".join(
        '<li><div class="ref-head"><strong>{}</strong><span class="ref-tag {}">{}</span></div>'
        '<code>{}:{}-{}</code><br><small>file sha256 {} · range sha256 {}</small></li>'.format(
            html.escape(ref["symbol"]),
            "active" if ref["id"] in active_ref_ids else "crosswalk",
            "USED IN THIS TRACE" if ref["id"] in active_ref_ids else "MODEL-WIDE CROSSWALK",
            html.escape(ref["path"]),
            ref["start_line"],
            ref["end_line"],
            ref["file_sha256"],
            ref["range_sha256"],
        )
        for ref in chart["implementation_mapping"]
    )
    provenance_text = (
        f"View SHA-256: {chart['provenance']['view']['sha256']}\n"
        f"Renderer SHA-256: {chart['provenance']['renderer']['sha256']}\n"
        f"Model SHA-256: {chart['model']['sha256']}\n"
        f"Receipt SHA-256: {chart['receipt']['sha256']}"
    )
    file_links = " · ".join(
        f'<a href="{html.escape(name, quote=True)}">{html.escape(label)}</a>'
        for name, label in ((svg_name, "SVG"), (mmd_name, "Mermaid source"), (json_name, "statechart data"))
    )
    if replay.get("report"):
        replay_detail = (
            f"<br>Report: {html.escape(replay['report']['file'])}<br>"
            f"Report SHA-256: <code>{html.escape(replay['report']['sha256'])}</code><br>"
            f"State SHA-256 before: <code>{html.escape(replay['state_sha256_before'])}</code><br>"
            f"State SHA-256 after: <code>{html.escape(replay['state_sha256_after'])}</code><br>"
            f"Actor authentication: {html.escape(replay['actor_authentication'])}<br>"
            "Interpretation: this replay checked the mapped Python path; it does not turn the TLC mutant into a demonstrated runtime defect."
        )
    else:
        replay_detail = ""
    if chart["kind"] == "baseline":
        passing_names = ", ".join(prop["name"] for prop in chart["properties"])
        model_rows = [
            "Result: PASS within the saved finite bounds",
            f"Properties passing ({len(chart['properties'])}): {passing_names}",
            f"States: {chart['result']['states']['distinct']:,} distinct / {chart['result']['states']['generated']:,} generated",
            "No counterexample trace exists in this receipt.",
        ]
    else:
        constants = ", ".join(f"{key}={str(value).lower()}" for key, value in sorted(chart["mutant"]["changed_constants"].items()))
        model_rows = [
            f"Mutant: {chart['mutant']['id']} ({constants})",
            f"Invariant: {chart['target_property']}",
            f"TLC counterexamples: {chart['property']['counterexample_count']:,}",
            f"Selected receipt path: {len(chart['trace'])} states · {trace_selection_label(chart['property']['trace_selection'])}",
        ]
    model_html = "<br>".join(html.escape(row) for row in model_rows)
    if chart["kind"] == "baseline":
        legend_items = [("Bounded TLC pass", COLORS["teal"], COLORS["teal_bg"])]
    else:
        phase_order = list(dict.fromkeys(state["phase"] for state in chart["trace"]))
        legend_items = [
            (phase, PHASES[index % len(PHASES)][0], PHASES[index % len(PHASES)][1])
            for index, phase in enumerate(phase_order)
        ]
        legend_items.append((f"Invariant violation · {chart['target_property']}", COLORS["red"], COLORS["red_bg"]))
    legend_html = "".join(
        '<span class="legend-chip"><i class="swatch" style="--swatch-stroke:{};--swatch-fill:{}"></i>{}</span>'.format(
            stroke, fill, html.escape(label)
        )
        for label, stroke, fill in legend_items
    )
    if chart["kind"] == "counterexample":
        transition_cards = []
        for number, step in enumerate(chart["steps"], 1):
            changed = step["changed_keys"] or ["none"]
            changed_html = "".join(f'<span class="key-chip">{html.escape(key)}</span>' for key in changed)
            from_state = chart["trace"][step["from"] - 1]
            to_state = chart["trace"][step["to"] - 1]
            from_facts = " · ".join(from_state.get("facts", [])) or from_state["label"]
            to_facts = " · ".join(to_state.get("facts", [])) or to_state["label"]
            state_facts_html = (
                f'<p class="state-facts"><strong>STATE PROJECTION (S{step["from"]} → S{step["to"]})</strong><br>'
                f'<span>S{step["from"]} ({html.escape(from_state["label"])}): {html.escape(from_facts)}</span><br>'
                f'<span>S{step["to"]} ({html.escape(to_state["label"])}): {html.escape(to_facts)}</span></p>'
            )
            implementation = step["implementation"]
            if implementation["status"] == "static-mapping":
                mapped = "; ".join(
                    f"{ref['symbol']} · {ref['path']}:{ref['start_line']}-{ref['end_line']}"
                    for ref in implementation["code_refs"]
                )
                mapping_html = (
                    f'<p class="step-map"><strong>STATIC IMPLEMENTATION MAPPING</strong> · '
                    f'{html.escape(mapped)}<br><span>{html.escape(implementation["expected_effect"] or "")}</span></p>'
                )
            else:
                mapping_html = (
                    f'<p class="step-map unmapped"><strong>MODEL-ONLY EDGE</strong> · '
                    f'{html.escape(implementation["reason"] or "")}</p>'
                )
            transition_cards.append(
                f'<article class="step-card"><div class="step-top"><strong>S{step["from"]} → S{step["to"]}</strong>'
                f'<span>STEP {number} · TLC RECEIPT</span></div>'
                f'<p class="raw-action"><strong>RAW TLC ACTION</strong><br><code>{html.escape(step["raw_action"])}</code></p>'
                f'<p class="interpretation"><strong>AUTHORED INTERPRETATION</strong><br>{html.escape(step["label"])}</p>'
                f'{state_facts_html}'
                f'<div class="key-row"><strong>changed_keys</strong>{changed_html}</div>{mapping_html}</article>'
            )
        trace_section = (
            '<section class="trace-evidence" aria-label="Selected TLC trace transition evidence">'
            '<h2>Selected TLC trace · transition evidence</h2>'
            f'<div class="step-list">{"".join(transition_cards)}</div></section>'
        )
    else:
        trace_section = (
            '<section class="trace-evidence baseline-trace"><h2>Selected TLC trace</h2>'
            '<p>The bounded baseline receipt contains no counterexample path. No transitions were inferred.</p></section>'
        )
    badge_color = replay.get("color", COLORS["slate"])
    badge_bg = replay.get("background", COLORS["slate_bg"])
    badge_style = f"border:1px solid {badge_color};color:{badge_color};background:{badge_bg}"
    return f'''<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; form-action 'none'">
<title>{escaped_title}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#071b30;color:#e8f2fb;font:15px/1.55 "Segoe UI",Tahoma,sans-serif}}main{{max-width:1560px;margin:auto;padding:20px}}header{{display:flex;justify-content:flex-end;margin:0 0 12px}}a{{color:#8ce6da}}.links{{white-space:nowrap}}figure{{margin:0 auto;border:1px solid #31516d;border-radius:18px;overflow:auto;background:#071b30;box-shadow:0 16px 42px #0004;display:flex;justify-content:center;max-height:82vh}}figure svg{{display:block;width:auto;max-width:100%;height:auto;max-height:82vh}}.legend{{display:flex;flex-wrap:wrap;justify-content:center;gap:8px;margin:12px auto 0;max-width:1100px}}.legend-chip{{display:inline-flex;align-items:center;gap:8px;padding:5px 10px;border:1px solid #31516d;border-radius:999px;background:#0c2742;color:#d7e5f2;font-size:12px}}.swatch{{width:13px;height:13px;border:2px solid var(--swatch-stroke);border-radius:4px;background:var(--swatch-fill);flex:none}}.trace-evidence{{margin-top:18px;padding:18px;border:1px solid #31516d;border-radius:16px;background:#0c2742}}.trace-evidence h2{{margin:0 0 12px;font-size:16px}}.step-list{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px;align-items:start}}.step-card{{padding:14px;border:1px solid #31516d;border-radius:12px;background:#091f35;overflow-wrap:anywhere}}.step-top{{display:flex;justify-content:space-between;gap:12px;align-items:center;color:#9bdcf0;font:700 11px Consolas,monospace}}.step-top span{{color:#829db5}}.raw-action,.interpretation,.state-facts,.step-map{{margin:12px 0 0;color:#d7e5f2}}.raw-action strong,.interpretation strong,.state-facts strong,.step-map strong,.key-row>strong{{display:block;color:#91d9ec;font:800 10px Consolas,monospace;letter-spacing:.04em}}.raw-action code{{font:12px/1.5 Consolas,monospace;color:#cfdeec}}.state-facts span{{font-size:12px;color:#adc3d7}}.key-row{{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin-top:12px}}.key-row>strong{{margin-right:4px;color:#fbbf65}}.key-chip{{display:inline-block;padding:3px 9px;border:1px solid #8b6c39;border-radius:999px;background:#3a2e1e;color:#fbd38d;font:700 11px Consolas,monospace}}.step-map{{padding-top:10px;border-top:1px solid #31516d;font-size:12px}}.step-map strong{{display:inline;color:#c4b5fd}}.step-map span{{color:#adc3d7}}.step-map.unmapped strong{{color:#ff829c}}.baseline-trace p{{color:#adc3d7;margin:0}}.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}}.evidence{{background:#0c2742;border:1px solid #31516d;border-radius:12px;padding:16px;overflow-wrap:anywhere}}.evidence h3{{font:800 11px Consolas,monospace;margin:0 0 8px;color:#c4b5fd}}.evidence p,.evidence ul{{margin:0;color:#d7e5f2}}.evidence li{{margin:0 0 12px}}.ref-head{{display:flex;flex-wrap:wrap;align-items:center;gap:6px}}.ref-tag{{display:inline-block;padding:1px 7px;border-radius:999px;font:700 10px Consolas,monospace}}.ref-tag.active{{border:1px solid #5eead4;background:#123b4a;color:#8ce6da}}.ref-tag.crosswalk{{border:1px solid #31516d;background:#091f35;color:#829db5}}.evidence code{{display:inline-block;word-break:break-all;font:11px/1.45 Consolas,monospace;color:#cfdeec}}.evidence small{{color:#adc3d7;word-break:break-all}}.badge{{display:inline-block;border-radius:999px;padding:2px 8px;font:800 11px Consolas,monospace}}details{{margin-top:16px;padding:14px 16px;border:1px solid #31516d;background:#0c2742;border-radius:14px}}summary{{cursor:pointer;font-weight:700;color:#c9d8e7}}.raw{{margin-top:14px!important}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#061526;border:1px solid #31516d;border-radius:10px;padding:12px;color:#cfdeec;font:12px/1.5 Consolas,monospace}}@media(max-width:900px){{main{{padding:12px}}header{{display:block}}.links{{white-space:normal}}.grid{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div class="links">{file_links}</div></header>
<figure>{svg}</figure>
<nav class="legend" aria-label="State and invariant legend">{legend_html}</nav>
{trace_section}
<section class="grid" aria-label="Evidence layers">
<article class="evidence"><h3>01 · BOUNDED MODEL (TLC)</h3><p>Bounds: {html.escape(bounds_text)}<br>{model_html}<br>{html.escape(chart['subtitle'])}</p></article>
<article class="evidence"><h3>02 · IMPLEMENTATION MAPPING (STATIC)</h3><p>Source crosswalk only · no runtime claim</p><ul>{mapping_rows}</ul></article>
<article class="evidence"><h3>03 · PYTHON RUNTIME REPLAY</h3><p><span class="badge" style="{badge_style}">{html.escape(replay.get('label', 'not-run / model-only'))}</span><br>{html.escape(replay.get('summary', 'Python runtime behavior was not exercised.'))}{replay_detail}</p></article>
</section>
<details><summary>Full provenance hashes and raw TLC trace</summary><div class="evidence"><h3>PROVENANCE · INPUTS</h3><code>{html.escape(provenance_text)}</code></div>
<details class="raw"><summary>Raw TLC trace, authored interpretations, per-step mapping, and changed_keys</summary><pre>{html.escape(raw_rows)}</pre></details>
</details></main></body></html>'''


def publish_directory_no_replace(stage: Path, destination: Path) -> None:
    """Atomically publish a staged directory without replacing a racing destination."""
    if os.path.lexists(destination):
        raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(destination))
    if os.name == "nt":
        os.rename(stage, destination)
        return
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise OSError(errno.ENOTSUP, "atomic no-replace directory publication is unavailable", str(destination))
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(stage), -100, os.fsencode(destination), 1)
        if result == 0:
            return
        error = ctypes.get_errno()
        if error in {errno.EINVAL, errno.ENOSYS, errno.EOPNOTSUPP}:
            if os.path.lexists(destination):
                raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(destination))
            os.rename(stage, destination)
            return
        raise OSError(error, os.strerror(error), str(destination))
    raise OSError(errno.ENOTSUP, "atomic no-replace directory publication is unsupported on this platform", str(destination))


def main() -> int:
    parser = argparse.ArgumentParser(description="Render saved model-check receipts as reader-facing statecharts; does not run TLC or Python replay.")
    parser.add_argument("--receipt-dir", type=Path, required=True, help="directory containing the receipt files named by the view")
    parser.add_argument("--view", type=Path, required=True, help="strict semantic state/step mapping JSON")
    parser.add_argument("--repo-root", type=Path, required=True, help="Git root used to bind model and implementation source evidence")
    parser.add_argument("--out-dir", type=Path, required=True, help="new output directory; existing paths are refused")
    parser.add_argument("--replay-report", type=Path, help="optional saved Python replay report bound to the exact stale-generation receipt and source digest")
    args = parser.parse_args()

    stage: Path | None = None
    try:
        receipt_dir = args.receipt_dir.resolve(strict=True)
        require(receipt_dir.is_dir(), "receipt-dir must be a directory")
        repo_root = args.repo_root.resolve(strict=True)
        view_path = args.view.resolve(strict=True)
        view, view_raw = read_json(view_path, "view mapping")
        exact_keys(view, {"schema_version", "slug", "title", "model_path", "bounds", "implementation_mapping", "cases"}, "view")
        require(view["schema_version"] == VIEW_SCHEMA_VERSION, f"unsupported view schema_version; expected {VIEW_SCHEMA_VERSION}")
        require(isinstance(view["slug"], str) and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", view["slug"]),
                "view slug must be a lowercase filesystem-safe name")
        require(isinstance(view["title"], str) and bool(view["title"].strip()), "view title is required")
        require(isinstance(view["model_path"], str), "view model_path must be a repository-relative string")
        model_path = safe_relative_file(repo_root, view["model_path"], "model_path")
        model_digest = sha256(model_path.read_bytes())
        refs = source_receipts(repo_root, view["implementation_mapping"])
        snapshot = git_snapshot(repo_root)
        require(isinstance(view["bounds"], dict) and bool(view["bounds"])
                and all(isinstance(key, str) and type(value) is int and value >= 0
                        for key, value in view["bounds"].items()),
                "view bounds must be a non-empty object of non-negative integers")
        view_stamp: ContentStamp = {"file": view_path.name, "sha256": sha256(view_raw)}
        renderer_path = Path(__file__).resolve(strict=True)
        renderer_stamp: ContentStamp = {"file": renderer_path.name, "sha256": sha256(renderer_path.read_bytes())}
        provenance: Provenance = {"view": view_stamp, "renderer": renderer_stamp}
        require(isinstance(view["cases"], list) and 1 <= len(view["cases"]) <= 12,
                "view must define between one and twelve cases")
        case_specs: list[ChartIR] = []
        ids = set()
        for case in view["cases"]:
            require(isinstance(case, dict), "every view case must be an object")
            built = build_case(case, receipt_dir, model_path, model_digest, view["bounds"],
                               Path(view["model_path"]).as_posix(), refs, provenance)
            require(built["id"] not in ids, f"duplicate case id: {built['id']}")
            ids.add(built["id"])
            case_specs.append(built)

        replay_by_case = {chart["id"]: not_run_replay(chart) for chart in case_specs}
        if args.replay_report is not None:
            replay_by_case["stale-generation"] = validate_replay_report(
                args.replay_report,
                receipt_dir,
                repo_root,
                case_specs,
                Path(view["model_path"]).as_posix(),
                model_digest,
                view["bounds"],
            )

        out_dir = args.out_dir.absolute()
        require(not os.path.lexists(out_dir), f"output path already exists; refusing overwrite: {out_dir}")
        require(out_dir.parent.is_dir(), f"output parent directory must already exist: {out_dir.parent}")
        require(out_dir.name not in {".", ".."}, "output directory needs a normal leaf name")
        stage = Path(tempfile.mkdtemp(prefix=f".{out_dir.name}.stage-", dir=out_dir.parent))
        scripts_dir = Path(__file__).resolve().parent
        mermaid_backend = scripts_dir / "backends" / "mermaid.ts"
        receipt_adapter = scripts_dir / "render_receipt_chart.mjs"
        renderer_backend = {
            "name": "statechart-mermaid+pele",
            "package": "pele",
            "version": "1.9.0",
            "source_revision": "4dd1d05818d19792e7cd6e818f1667f95f7e1dbe",
            "mermaid_backend_sha256": sha256(mermaid_backend.read_bytes()),
            "receipt_adapter_sha256": sha256(receipt_adapter.read_bytes()),
        }
        manifest = {"schema_version": STATECHART_SCHEMA_VERSION, "slug": view["slug"], "title": view["title"], "repository": snapshot,
                    "model": {"path": view["model_path"], "sha256": model_digest},
                    "view": view_stamp, "renderer": renderer_stamp,
                    "renderer_backend": renderer_backend,
                    "bounds": view["bounds"], "replay": {}, "implementation_mapping": refs, "cases": []}
        cards = []
        for chart in case_specs:
            stem = f"{view['slug']}-{chart['id']}"
            svg_name, mmd_name, json_name, html_name = (f"{stem}.svg", f"{stem}.mmd", f"{stem}.statechart.json", f"{stem}.html")
            replay = replay_by_case[chart["id"]]
            mmd_path = stage / mmd_name
            svg_path = stage / svg_name
            svg = render_statechart(chart, replay, stage, mmd_path, svg_path)
            mmd = mmd_path.read_text(encoding="utf-8")
            public_chart: dict[str, Any] = {"schema_version": STATECHART_SCHEMA_VERSION, **chart}
            public_chart["repository"] = snapshot
            public_chart["replay"] = replay
            public_chart["renderer_backend"] = manifest["renderer_backend"]
            manifest["replay"][chart["id"]] = replay
            trace_rows = [
                f"S{s['index']} raw_action={canonical_json(s['incoming_action'])} changed_keys={canonical_json(s['changed_keys'])} state={canonical_json(s['state'])}"
                for s in chart["trace"]
            ]
            edge_rows = []
            if chart["kind"] == "counterexample":
                for step in chart["steps"]:
                    implementation = step["implementation"]
                    edge_rows.append(
                        f"EDGE S{step['from']}->S{step['to']} label_origin={step['label_origin']} "
                        f"label={canonical_json(step['label'])} raw_action={canonical_json(step['raw_action'])} "
                        f"changed_keys={canonical_json(step['changed_keys'])} implementation={canonical_json(implementation)}"
                    )
            raw_rows = "\n".join(trace_rows + edge_rows) or "No trace in the baseline receipt; no state path is inferred."
            html_doc = render_html(chart, svg, raw_rows, mmd_name, svg_name, json_name, replay)
            files_to_write = [
                (json_name, json.dumps(public_chart, ensure_ascii=False, sort_keys=True, indent=2) + "\n"),
                (html_name, html_doc),
            ]
            require(svg_path.is_file() and svg_path.read_text(encoding="utf-8") == svg,
                    "Pele output changed between validation and staging")
            for name, content in files_to_write:
                (stage / name).write_text(content, encoding="utf-8", newline="\n")
            manifest["cases"].append({"id": chart["id"], "html": html_name, "svg": svg_name, "mermaid": mmd_name,
                                      "statechart": json_name, "renderer_backend": renderer_backend["name"], "receipt": chart["receipt"]})
            cards.append(f'<article><h2>{html.escape(chart["title"])}</h2><p>{html.escape(chart["subtitle"])}</p><p class="replay">Replay: {html.escape(replay["label"])}</p><a href="{html.escape(html_name, quote=True)}">Open statechart</a> · <a href="{html.escape(svg_name, quote=True)}">SVG</a> · <a href="{html.escape(mmd_name, quote=True)}">MMD</a></article>')
        (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
        index = f'''<!doctype html><html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>{html.escape(view['title'])}</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#071b30;color:#e8f2fb;font:15px/1.5 "Segoe UI",Tahoma,sans-serif}}main{{max-width:1120px;margin:auto;padding:36px 22px}}.kicker{{color:#5eead4;font:700 11px Consolas,monospace;letter-spacing:.15em}}h1{{margin:8px 0;font-size:30px}}.intro{{color:#adc3d7;max-width:760px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin-top:24px}}article{{padding:20px;border:1px solid #31516d;border-radius:16px;background:#0c2742}}article h2{{font-size:18px;margin:0 0 8px}}article p{{color:#adc3d7;min-height:32px}}article .replay{{color:#c4b5fd;font:12px Consolas,monospace}}a{{color:#8ce6da}}.note{{margin-top:20px;padding:16px;border:1px dashed #57758f;border-radius:12px;color:#adc3d7}}@media(max-width:600px){{main{{padding:18px 14px}}h1{{font-size:24px}}}}</style></head><body><main><div class="kicker">PATPAT · BOUNDED TLA+ MODEL</div><h1>{html.escape(view['title'])}</h1><p class="intro">Each view separates bounded TLC evidence from static code mapping. Replay evidence is case-specific; a model counterexample alone is not a Python runtime defect.</p><div class="grid">{''.join(cards)}</div><p class="note">The statechart uses authored, reader-facing action labels. Exact raw TLC actions and changed_keys remain in the evidence records. The violating endpoint is a model state, not a system terminal. All artifacts are generated locally and work offline.</p></main></body></html>'''
        (stage / "index.html").write_text(index, encoding="utf-8", newline="\n")
        publish_directory_no_replace(stage, out_dir)
        stage = None
        print(json.dumps({"status": "rendered", "output": str(out_dir), "renderer": renderer_backend["name"], "cases": [item["id"] for item in case_specs],
                          "files": sorted(path.name for path in out_dir.iterdir()),
                          "replay": {case_id: report["label"] for case_id, report in replay_by_case.items()}}, ensure_ascii=True))
        return 0
    except (StatechartError, OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"statechart error: {exc}", file=sys.stderr)
        return 2
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)


if __name__ == "__main__":
    raise SystemExit(main())
