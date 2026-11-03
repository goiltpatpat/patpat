#!/usr/bin/env python3
"""Bridge between patpat-repository-diagram and patpat-statechart.

Provides deterministic bidirectional hand-off:
1. seed-model: Scaffolds SPEC.tla, SPEC.cfg, and view.mjs from a Schema 2
   lifecycle or workflow diagram JSON.
2. attach-bug-path: Injects a TLC counterexample trace as a validated Schema 2
   story view into an existing diagram JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from model import DiagramError, load_json, validate_spec


def clean_identifier(name: str) -> str:
    """Sanitize identifier for TLA+ and JavaScript variable/action names."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.replace("-", "_"))
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"A_{sanitized}"
    return sanitized


def cmd_seed_model(args: argparse.Namespace) -> int:
    """Generate SPEC.tla, SPEC.cfg, and view.mjs from diagram JSON."""
    diagram_path = Path(args.diagram).resolve()
    if not diagram_path.is_file():
        sys.stderr.write(f"error: diagram file not found: {diagram_path}\n")
        return 1

    try:
        raw, _ = load_json(diagram_path)
    except DiagramError as err:
        sys.stderr.write(f"error loading diagram: {err}\n")
        return 1

    dtype = raw.get("type")
    if dtype not in {"lifecycle", "workflow"}:
        sys.stderr.write(f"error: seed-model requires 'lifecycle' or 'workflow' diagram, got {dtype!r}\n")
        return 1

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    body = raw.get("body", {})
    title = raw.get("title", "GeneratedModel")
    module_name = clean_identifier(title)
    if not module_name or module_name == "Spec":
        module_name = "ModelSpec"

    # Extract entities and transitions
    if dtype == "lifecycle":
        entities = body.get("states", [])
        transitions = body.get("transitions", [])
        initial_ids = [e["id"] for e in entities if e.get("kind") == "initial"]
        terminal_ids = [e["id"] for e in entities if e.get("kind") == "terminal"]
    else:  # workflow
        entities = body.get("steps", [])
        transitions = body.get("transitions", [])
        initial_ids = [e["id"] for e in entities if e.get("kind") == "start"]
        terminal_ids = [e["id"] for e in entities if e.get("kind") == "terminal"]

    if not initial_ids:
        sys.stderr.write("error: diagram has no initial/start entity\n")
        return 1

    initial_id = initial_ids[0]

    # Map transition IDs to TLA+ action names and details
    action_defs: list[dict[str, Any]] = []
    for tr in transitions:
        t_id = tr["id"]
        source = tr["source"]
        target = tr["target"]
        label = tr.get("label", t_id)
        action_name = f"Action_{clean_identifier(t_id)}"
        action_defs.append({
            "action_name": action_name,
            "id": t_id,
            "source": source,
            "target": target,
            "label": label,
            "evidence_ids": tr.get("evidence_ids", []),
        })

    # Build SPEC.tla
    tla_lines = [
        f"---- MODULE {module_name} ----",
        "EXTENDS Naturals, Sequences, FiniteSets, TLC",
        "",
        "(*",
        f"  Generated from Patpat {dtype} diagram: {diagram_path.name}",
        f"  Title: {title}",
        f"  Reader: {args.reader or 'Engineer'}",
        "*)",
        "",
        "VARIABLES phase",
        "vars == <<phase>>",
        "",
        f'Init == phase = "{initial_id}"',
        "",
    ]

    action_names = []
    for adef in action_defs:
        act = adef["action_name"]
        action_names.append(act)
        src = adef["source"]
        tgt = adef["target"]
        lbl = adef["label"]
        tla_lines.append(f"(* Transition: {adef['id']} | {lbl} *)")
        tla_lines.append(f'{act} == phase = "{src}" /\\ phase\' = "{tgt}"')
        tla_lines.append("")

    # Terminal / Done action
    terminals_str = ", ".join(f'"{t}"' for t in terminal_ids) if terminal_ids else f'"{initial_id}"'
    tla_lines.append("(* Done action prevents terminal states from causing deadlock violations *)")
    tla_lines.append(f"Done == phase \\in {{{terminals_str}}} /\\ UNCHANGED vars")
    tla_lines.append("")

    # Next relation
    disjunctions = " \\/ ".join(action_names + ["Done"])
    tla_lines.append(f"Next == {disjunctions}")
    tla_lines.append("")
    tla_lines.append("Spec == Init /\\ [][Next]_vars")
    tla_lines.append("")

    # Invariants
    tla_lines.append("(* Reader-defined safety invariants *)")
    custom_invariants = args.rule or []
    if not custom_invariants:
        tla_lines.append("(* Default deadlock invariant: system makes progress until Done *)")
        tla_lines.append("NoDeadlock == phase \\notin {" + terminals_str + "}")
    else:
        for idx, rule in enumerate(custom_invariants, 1):
            inv_name = f"Rule_{idx}_{clean_identifier(rule)[:24]}"
            tla_lines.append(f"(* Rule: {rule} *)")
            tla_lines.append(f'{inv_name} == phase /= "ILLEGAL_STATE"')

    tla_lines.append("")
    tla_lines.append("====")

    spec_tla_path = out_dir / f"{module_name}.tla"
    spec_tla_path.write_text("\n".join(tla_lines), encoding="utf-8")

    # Build SPEC.cfg
    cfg_lines = [
        "SPECIFICATION Spec",
    ]
    if not custom_invariants:
        cfg_lines.append("INVARIANT NoDeadlock")
    else:
        for idx, rule in enumerate(custom_invariants, 1):
            inv_name = f"Rule_{idx}_{clean_identifier(rule)[:24]}"
            cfg_lines.append(f"INVARIANT {inv_name}")

    spec_cfg_path = out_dir / f"{module_name}.cfg"
    spec_cfg_path.write_text("\n".join(cfg_lines), encoding="utf-8")

    # Build view.mjs
    state_map = {e["id"]: e.get("label", e["id"]) for e in entities}
    step_map = {adef["action_name"]: adef["label"] for adef in action_defs}

    view_lines = [
        "// Reader-facing statechart view mapping",
        "// Generated from Patpat diagram",
        "",
        f"export const title = {json.dumps(title)};",
        "",
        "const STATE_LABELS = " + json.dumps(state_map, indent=2) + ";",
        "",
        "const STEP_LABELS = " + json.dumps(step_map, indent=2) + ";",
        "",
        "export const state = (v) => {",
        "  return STATE_LABELS[v.phase] || v.phase;",
        "};",
        "",
        "export const step = (action, from, to) => {",
        "  if (action === 'Done') return null;",
        "  return STEP_LABELS[action] || action;",
        "};",
        "",
        "export const colors = {",
        "  active: 'blue',",
        "  verified: 'teal',",
        "  terminal: 'purple',",
        "};",
        "",
    ]
    view_path = out_dir / "view.mjs"
    view_path.write_text("\n".join(view_lines), encoding="utf-8")

    print(f"Successfully scaffolded TLA+ statechart model to: {out_dir}")
    print(f"  - TLA Spec:   {spec_tla_path.name}")
    print(f"  - Config:     {spec_cfg_path.name}")
    print(f"  - View:       {view_path.name}")
    return 0


def cmd_attach_bug_path(args: argparse.Namespace) -> int:
    """Attach a TLC counterexample trace as a Schema 2 story view in diagram JSON."""
    diagram_path = Path(args.diagram).resolve()
    if not diagram_path.is_file():
        sys.stderr.write(f"error: diagram file not found: {diagram_path}\n")
        return 1

    try:
        raw, _ = load_json(diagram_path)
    except DiagramError as err:
        sys.stderr.write(f"error loading diagram: {err}\n")
        return 1

    # Extract valid entity and transition IDs
    body = raw.get("body", {})
    dtype = raw.get("type")
    if dtype == "lifecycle":
        entities = body.get("states", [])
        transitions = body.get("transitions", [])
    elif dtype == "workflow":
        entities = body.get("steps", [])
        transitions = body.get("transitions", [])
    elif dtype == "architecture":
        entities = body.get("components", [])
        transitions = body.get("relationships", [])
    else:
        entities = []
        transitions = []

    valid_ids = {e["id"] for e in entities} | {t["id"] for t in transitions}

    # Parse trace focus list
    trace_input = args.trace
    focus_ids: list[str] = []
    if Path(trace_input).is_file():
        tdata = json.loads(Path(trace_input).read_text(encoding="utf-8"))
        if isinstance(tdata, list):
            focus_ids = [str(x) for x in tdata]
        elif isinstance(tdata, dict) and "trace" in tdata:
            # Model-check receipt format
            for item in tdata["trace"]:
                if "state" in item and isinstance(item["state"], dict):
                    # check for state label or id
                    sid = item["state"].get("phase") or item["state"].get("id")
                    if sid and str(sid) in valid_ids:
                        focus_ids.append(str(sid))
                if "action" in item:
                    aid = str(item["action"]).removeprefix("Action_")
                    if aid in valid_ids:
                        focus_ids.append(aid)
    else:
        # Comma-separated or JSON string
        try:
            parsed = json.loads(trace_input)
            if isinstance(parsed, list):
                focus_ids = [str(x) for x in parsed]
        except json.JSONDecodeError:
            focus_ids = [x.strip() for x in trace_input.split(",") if x.strip()]

    if not focus_ids:
        sys.stderr.write("error: no valid trace IDs extracted for focus\n")
        return 1

    # Filter or check focus IDs against diagram
    unknown_ids = [fid for fid in focus_ids if fid not in valid_ids]
    if unknown_ids:
        sys.stderr.write(f"warning: trace contains IDs not in diagram: {unknown_ids}\n")
        # Keep only valid IDs as per patpat-repository-diagram contract
        focus_ids = [fid for fid in focus_ids if fid in valid_ids]

    rule = args.rule or "ViolatedInvariant"
    replay = args.replay or "model-only"
    if replay not in {"replayed", "model-only", "replay-inconclusive"}:
        sys.stderr.write(f"error: invalid replay label {replay!r}, must be replayed, model-only, or replay-inconclusive\n")
        return 1

    report = args.report or "report.md"
    story_id = f"bug_path_{clean_identifier(rule)[:20]}"
    story_label = args.title or f"Bug path · {rule}"
    missing_note = f" (omits model states: {', '.join(unknown_ids)})" if unknown_ids else ""
    story_note = f"breaks {rule} (report: {report}, replay: {replay}){missing_note}"

    new_view = {
        "id": story_id,
        "label": story_label,
        "focus": focus_ids,
        "note": story_note,
    }

    views = raw.setdefault("views", [])
    # Replace existing view with same ID if present, otherwise append
    views = [v for v in views if v.get("id") != story_id]
    views.append(new_view)
    raw["views"] = views

    # Validate updated spec
    try:
        repo_root = Path(args.repo_root).resolve() if args.repo_root else None
        validate_spec(raw, repo_root=repo_root)
    except DiagramError as err:
        sys.stderr.write(f"error: resulting spec fails validation: {err}\n")
        return 1

    out_path = Path(args.out).resolve() if args.out else diagram_path
    out_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"Successfully attached bug path to story view in: {out_path}")
    print(f"  - View ID:    {story_id}")
    print(f"  - Label:      {story_label}")
    print(f"  - Focus IDs:  {focus_ids}")
    print(f"  - Note:       {story_note}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bidirectional bridge between patpat-repository-diagram and patpat-statechart."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Subcommand: seed-model
    seed_p = subparsers.add_parser(
        "seed-model",
        help="Scaffold TLA+ spec, config, and view.mjs from lifecycle or workflow diagram",
    )
    seed_p.add_argument("--diagram", required=True, help="Path to source .diagram.json")
    seed_p.add_argument("--out-dir", required=True, help="Directory to write TLA/view files")
    seed_p.add_argument("--reader", help="Name of reader (e.g. Engineer, Product Owner)")
    seed_p.add_argument("--rule", action="append", help="Reader rules to check as invariants")

    # Subcommand: attach-bug-path
    attach_p = subparsers.add_parser(
        "attach-bug-path",
        help="Attach TLC counterexample trace to diagram JSON as a Schema 2 story view",
    )
    attach_p.add_argument("--diagram", required=True, help="Path to target .diagram.json")
    attach_p.add_argument("--trace", required=True, help="Comma-separated IDs or path to JSON trace")
    attach_p.add_argument("--rule", required=True, help="Broken rule / invariant name")
    attach_p.add_argument("--report", default="report.md", help="Relative path to report.md")
    attach_p.add_argument(
        "--replay",
        choices=["replayed", "model-only", "replay-inconclusive"],
        default="model-only",
        help="Replay status label",
    )
    attach_p.add_argument("--title", help="Story view title")
    attach_p.add_argument("--out", help="Output path (defaults to modifying diagram in-place)")
    attach_p.add_argument("--repo-root", help="Repository root for validation")

    args = parser.parse_args()
    if args.command == "seed-model":
        return cmd_seed_model(args)
    if args.command == "attach-bug-path":
        return cmd_attach_bug_path(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
