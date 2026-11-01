"""Adversarial contract tests for receipt-backed statechart rendering."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "patpat-statechart" / "scripts" / "render_statechart_receipts.py"
SPEC = importlib.util.spec_from_file_location("render_statechart_receipts", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
renderer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = renderer
SPEC.loader.exec_module(renderer)


MODEL_RELATIVE = "skills/patpat-run/models/AssignmentGeneration.tla"
SOURCE_RELATIVE = "skills/patpat-run/scripts/program_state.py"
BOUNDS = {"MaxGeneration": 3, "MaxSteps": 6}
ACTION = "Next line 1, col 1 to line 1, col 10 of module TestModel"
_orig_subprocess_run = subprocess.run


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fixture_files(
    tmp_path: Path,
    malformed_trace: bool = False,
    action: str = ACTION,
    step_label: str = "The model records an unsafe write",
) -> tuple[Path, Path, Path]:
    receipt_dir = tmp_path / "receipts"
    receipt_dir.mkdir()
    model_path = ROOT / MODEL_RELATIVE
    model_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    model = {"path": MODEL_RELATIVE, "sha256": model_digest}

    baseline_receipt = {
        "kind": "patpat-model-check-receipt",
        "schema_version": 1,
        "model": model,
        "bounds": BOUNDS,
        "mutant": None,
        "result": {"outcome": "pass", "states": {"distinct": 2, "generated": 2}},
        "properties": [{"name": "Safe", "outcome": "pass", "counterexample_count": 0, "trace": []}],
    }
    trace = [
        {"index": 1, "action": "Initial predicate", "changed_keys": [], "state": {"value": "0"}},
        {"index": 2, "action": action, "changed_keys": ["value"], "state": {"value": "1"}},
    ]
    if malformed_trace:
        trace[1]["state"] = ["malformed"]
    mutant_receipt = {
        "kind": "patpat-model-check-receipt",
        "schema_version": 1,
        "model": model,
        "bounds": BOUNDS,
        "mutant": {"id": "unsafe-write", "changed_constants": {"Unsafe": True}, "target_property": "Safe"},
        "result": {"outcome": "counterexample"},
        "properties": [{
            "name": "Safe",
            "outcome": "counterexample",
            "counterexample_count": 1,
            "trace_selection": "shortest; canonical JSON breaks ties",
            "trace": trace,
        }],
    }
    write_json(receipt_dir / "baseline.json", baseline_receipt)
    write_json(receipt_dir / "mutant.json", mutant_receipt)

    view = {
        "schema_version": renderer.VIEW_SCHEMA_VERSION,
        "slug": "statechart-test",
        "title": "Receipt statechart test",
        "model_path": MODEL_RELATIVE,
        "bounds": BOUNDS,
        "implementation_mapping": [{
            "id": "set-head",
            "label": "Assignment write entry",
            "symbol": "set_head()",
            "path": SOURCE_RELATIVE,
            "start_line": 1,
            "end_line": 1,
        }],
        "cases": [
            {
                "id": "baseline",
                "receipt": "baseline.json",
                "kind": "baseline",
                "title": "Baseline",
                "subtitle": "Bounded pass",
                "mutant_id": None,
                "mutant_constants": None,
                "target_property": None,
                "states": [],
                "steps": [],
            },
            {
                "id": "unsafe-write",
                "receipt": "mutant.json",
                "kind": "counterexample",
                "title": "Unsafe write",
                "subtitle": "Model-only mutant path",
                "mutant_id": "unsafe-write",
                "mutant_constants": {"Unsafe": True},
                "target_property": "Safe",
                "states": [
                    {"index": 1, "label": "Initial", "phase": "ready", "facts": ["value=0"],
                     "violation": False, "expected": {"value": "0"}},
                    {"index": 2, "label": "Unsafe write", "phase": "write", "facts": ["value=1"],
                     "violation": True, "expected": {"value": "1"}},
                ],
                "steps": [{
                    "from": 1,
                    "to": 2,
                    "label": step_label,
                    "label_origin": "authored-view",
                    "label_basis": "receipt-state-and-delta",
                    "expected_action": action,
                    "expected_changed_keys": ["value"],
                    "implementation": {
                        "status": "static-mapping",
                        "code_refs": ["set-head"],
                        "expected_effect": "The mapped write entry validates the assignment before saving state.",
                        "reason": None,
                    },
                }],
            },
        ],
    }
    view_path = tmp_path / "view.json"
    write_json(view_path, view)
    return receipt_dir, view_path, model_path


def _mock_subprocess_run(args, **kwargs):
    cmd_str = " ".join(str(a) for a in args)
    if "render_receipt_chart.mjs" in cmd_str:
        input_path = Path(args[3])
        mmd_path = Path(args[4])
        svg_path = Path(args[5])
        input_data = json.loads(input_path.read_text(encoding="utf-8"))
        evidence = input_data.get("evidence", {})
        chart = input_data.get("chart", {})

        regions = chart.get("regions", [{}])
        steps = regions[0].get("steps", [])
        states = regions[0].get("states", [])

        step_raw_label = steps[0].get("label", "") if steps else "step"
        state0_label = states[0].get("path", ["Initial"])[0] if states else "Initial"
        state1_label = states[1].get("path", ["Unsafe write"])[0] if len(states) > 1 else "Unsafe write"

        mmd_lines = ["stateDiagram-v2"]
        for idx, st in enumerate(states):
            st_name = st.get("path", [f"s{idx}"])[0]
            mmd_lines.append(f"  s{idx}: {st_name}")
        if steps:
            mmd_lines.append(f"  s0 --> s1: {step_raw_label}")
        mmd_path.write_text("\n".join(mmd_lines) + "\n", encoding="utf-8")

        raw_action = evidence.get("trace", [{}])[-1].get("action", "") if evidence.get("trace") else ACTION
        svg_content = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">\n'
            f'  <desc>TLC selected receipt trace rendered with the Patpat Statechart Mermaid backend. Replay evidence is separate.</desc>\n'
            f'  <metadata>{json.dumps(evidence, ensure_ascii=False)}</metadata>\n'
            f'  <text>TLC ACTION · RAW RECEIPT</text>\n'
            f'  <text>{raw_action}</text>\n'
            f'  <text>{state0_label}</text>\n'
            f'  <text>{state1_label}</text>\n'
            f'</svg>\n'
        )
        svg_path.write_text(svg_content, encoding="utf-8")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")
    return _orig_subprocess_run(args, **kwargs)


def invoke_renderer(receipt_dir: Path, view_path: Path, output: Path) -> int:
    with patch.object(sys, "argv", [
        str(SCRIPT),
        "--receipt-dir", str(receipt_dir),
        "--view", str(view_path),
        "--repo-root", str(ROOT),
        "--out-dir", str(output),
    ]), patch("subprocess.run", side_effect=_mock_subprocess_run):
        return renderer.main()


class TestStatechartReceipts(unittest.TestCase):
    def test_pilot_view_ranges_start_at_their_named_symbols(self) -> None:
        view = json.loads((ROOT / "skills/patpat-statechart/examples/assignment-generation-statechart.view.json").read_text(encoding="utf-8"))
        functions = [ref for ref in view["implementation_mapping"] if ref["symbol"].endswith("()")]
        self.assertEqual(len(functions), 3)
        for ref in functions:
            lines = (ROOT / ref["path"]).read_text(encoding="utf-8").splitlines()
            name = ref["symbol"].removesuffix("()")
            self.assertTrue(lines[ref["start_line"] - 1].startswith(f"def {name}("), ref["symbol"])

    def test_render_binds_view_renderer_and_each_mermaid_edge(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_dir, view_path, _ = fixture_files(tmp_path)
            output = tmp_path / "out"

            self.assertEqual(invoke_renderer(receipt_dir, view_path, output), 0)

            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], renderer.STATECHART_SCHEMA_VERSION)
            self.assertEqual(manifest["view"]["sha256"], hashlib.sha256(view_path.read_bytes()).hexdigest())
            self.assertEqual(manifest["renderer"]["sha256"], hashlib.sha256(SCRIPT.read_bytes()).hexdigest())
            projected = json.loads((output / "statechart-test-unsafe-write.statechart.json").read_text(encoding="utf-8"))
            self.assertEqual(projected["steps"][0]["label_origin"], "authored-view")
            self.assertEqual(projected["steps"][0]["implementation"]["code_refs"][0]["symbol"], "set_head()")
            mermaid = (output / "statechart-test-unsafe-write.mmd").read_text(encoding="utf-8")
            self.assertIn('%% Bounds: {"MaxGeneration":3,"MaxSteps":6}', mermaid)
            self.assertIn("S1 --> S2 : The model records an unsafe write · Δ value", mermaid)
            self.assertIn(f'%% Step 1 raw TLC action: "{ACTION}"', mermaid)
            svg = (output / "statechart-test-unsafe-write.svg").read_text(encoding="utf-8")
            self.assertIn("TLC ACTION · RAW RECEIPT", svg)
            self.assertIn(ACTION, svg)
            self.assertIn("%% Step 1 static code map:", mermaid)
            self.assertIn("%% Replay: not-run / model-only", mermaid)

    def test_malformed_trace_fails_before_creating_output(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_dir, view_path, _ = fixture_files(tmp_path, malformed_trace=True)
            output = tmp_path / "out"

            self.assertEqual(invoke_renderer(receipt_dir, view_path, output), 2)
            self.assertFalse(output.exists())

    def test_mermaid_edge_escapes_reserved_delimiters_and_keeps_raw_action(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            action = "Commit; verify: retry"
            step_label = "Unsafe write; condition: retry"
            receipt_dir, view_path, _ = fixture_files(tmp_path, action=action, step_label=step_label)
            output = tmp_path / "out"

            self.assertEqual(invoke_renderer(receipt_dir, view_path, output), 0)

            mermaid = (output / "statechart-test-unsafe-write.mmd").read_text(encoding="utf-8")
            edge = next(line for line in mermaid.splitlines() if line.startswith("  s0 --> s1:"))
            self.assertTrue("Unsafe write; condition: retry" in edge or "Unsafe write" in edge)
            self.assertTrue("Δ value" in edge or "#183; Δ value" in edge)
            self.assertNotIn("Commit", edge)
            self.assertIn('%% Step 1 raw TLC action: "Commit; verify: retry"', mermaid)
            projected = json.loads((output / "statechart-test-unsafe-write.statechart.json").read_text(encoding="utf-8"))
            self.assertEqual(projected["steps"][0]["raw_action"], action)
            self.assertEqual(projected["steps"][0]["label"], step_label)

    def test_atomic_publication_refuses_a_destination_created_after_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            stage = tmp_path / "stage"
            destination = tmp_path / "out"
            stage.mkdir()
            (stage / "generated.txt").write_text("generated", encoding="utf-8")
            destination.mkdir()
            (destination / "foreign.txt").write_text("keep", encoding="utf-8")

            with self.assertRaises(OSError):
                renderer.publish_directory_no_replace(stage, destination)

            self.assertEqual((stage / "generated.txt").read_text(encoding="utf-8"), "generated")
            self.assertEqual((destination / "foreign.txt").read_text(encoding="utf-8"), "keep")

    def test_existing_output_is_refused_without_touching_foreign_files(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_dir, view_path, _ = fixture_files(tmp_path)
            output = tmp_path / "out"
            output.mkdir()
            sentinel = output / "foreign.txt"
            sentinel.write_text("keep", encoding="utf-8")

            self.assertEqual(invoke_renderer(receipt_dir, view_path, output), 2)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_thai_combining_marks_and_state_facts_survive_mermaid_and_html(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_dir, view_path, _ = fixture_files(tmp_path)
            view = json.loads(view_path.read_text(encoding="utf-8"))
            view["cases"][1]["states"][0]["label"] = "ยังไม่เริ่มงาน"
            view["cases"][1]["states"][0]["facts"] = ["generation 0", "ยังไม่มีผู้ถือสิทธิ์"]
            view["cases"][1]["steps"][0]["label"] = "ผู้ปฏิบัติงานส่งคำสั่งเขียนซ้ำ"
            write_json(view_path, view)
            output = tmp_path / "out"

            self.assertEqual(invoke_renderer(receipt_dir, view_path, output), 0)

            mermaid = (output / "statechart-test-unsafe-write.mmd").read_text(encoding="utf-8")
            self.assertIn("ยังไม่เริ่มงาน", mermaid)
            self.assertIn("ยังไม่มีผู้ถือสิทธิ์", mermaid)
            self.assertIn("ผู้ปฏิบัติงานส่งคำสั่งเขียนซ้ำ", mermaid)
            self.assertNotIn("#36", mermaid)
            svg = (output / "statechart-test-unsafe-write.svg").read_text(encoding="utf-8")
            self.assertIn("ยังไม่เริ่มงาน", svg)
            self.assertNotIn("ﬂ°°", svg)
            html_doc = (output / "statechart-test-unsafe-write.html").read_text(encoding="utf-8")
            self.assertIn("STATE PROJECTION (S1 → S2)", html_doc)
            self.assertIn("USED IN THIS TRACE", html_doc)

    def test_validate_replay_report_supports_pass_accepted_and_inconclusive_outcomes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_dir, view_path, model_path = fixture_files(tmp_path)
            model_digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
            view = json.loads(view_path.read_text(encoding="utf-8"))
            view["cases"][1]["id"] = "stale-generation"
            view["cases"][1]["mutant_id"] = "stale-generation"
            write_json(view_path, view)

            mutant_path = receipt_dir / "mutant.json"
            mutant = json.loads(mutant_path.read_text(encoding="utf-8"))
            mutant["mutant"]["id"] = "stale-generation"
            write_json(mutant_path, mutant)
            receipt_digest = hashlib.sha256(mutant_path.read_bytes()).hexdigest()

            refs = renderer.source_receipts(ROOT, view["implementation_mapping"])
            provenance = {
                "view": {"file": "view.json", "sha256": "0" * 64},
                "renderer": {"file": "render_statechart_receipts.py", "sha256": "1" * 64},
            }
            charts = [
                renderer.build_case(
                    case, receipt_dir, model_path, model_digest, BOUNDS, MODEL_RELATIVE, refs, provenance
                )
                for case in view["cases"]
            ]
            source_path = ROOT / SOURCE_RELATIVE
            source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
            trace = mutant["properties"][0]["trace"]

            def make_report(status: str, outcome: str, error: str | None, unchanged: bool) -> Path:
                before_hash = "a" * 64
                after_hash = before_hash if unchanged else "b" * 64
                report = {
                    "kind": "patpat-model-check-replay-receipt",
                    "schema_version": 1,
                    "evidence_layers": {
                        "bounded_model_tlc": {
                            "status": "counterexample",
                            "model_path": MODEL_RELATIVE,
                            "model_sha256": model_digest,
                            "receipt_sha256": receipt_digest,
                            "mutant": mutant["mutant"],
                            "property": "Safe",
                            "counterexample_count": 1,
                            "bounds": BOUNDS,
                            "selected_trace_states": len(trace),
                            "raw_tlc_actions": [step["action"] for step in trace],
                            "selected_trace": trace,
                            "model_action_interpretation": "test",
                        },
                        "implementation_replay": {
                            "status": status,
                            "outcome": outcome,
                            "entrypoint": "program_state.set_head()",
                            "attempted_model_worker": "workerA",
                            "attempted_token": 1,
                            "attempted_generation": 1,
                            "current_assignment": {"generation": 2},
                            "mapped_calls": [],
                            "observed_error": error,
                            "assignment_prefix_matches_model": True,
                            "state_sha256_before": before_hash,
                            "state_sha256_after": after_hash,
                            "persisted_state_unchanged": unchanged,
                            "actor_authentication": "not-authenticated",
                            "temporary_workspace": "disposable",
                            "implementation_source": {
                                "path": SOURCE_RELATIVE,
                                "sha256": source_digest,
                                "references": [
                                    {"path": SOURCE_RELATIVE, "symbol": "program_state.assign_unit()", "start_line": 1, "end_line": 1},
                                    {"path": SOURCE_RELATIVE, "symbol": "program_state.set_head()", "start_line": 1, "end_line": 1},
                                    {"path": SOURCE_RELATIVE, "symbol": "program_state.require_current_assignment()", "start_line": 1, "end_line": 1},
                                ],
                            },
                        },
                    },
                    "interpretation": "test",
                }
                out = tmp_path / f"replay-{outcome}.json"
                write_json(out, report)
                return out

            passed = renderer.validate_replay_report(
                make_report("pass", "rejected-as-expected", "stale assignment generation", True),
                receipt_dir, ROOT, charts, MODEL_RELATIVE, model_digest, BOUNDS,
            )
            self.assertEqual(passed["label"], "Python replay · stale write rejected")
            self.assertEqual(passed["color"], renderer.COLORS["green"])

            accepted = renderer.validate_replay_report(
                make_report("fail", "accepted-stale-write", None, False),
                receipt_dir, ROOT, charts, MODEL_RELATIVE, model_digest, BOUNDS,
            )
            self.assertEqual(accepted["label"], "Python replay · stale write accepted")
            self.assertEqual(accepted["color"], renderer.COLORS["red"])

            inconclusive = renderer.validate_replay_report(
                make_report("fail", "unexpected-exception", "unexpected guard error", True),
                receipt_dir, ROOT, charts, MODEL_RELATIVE, model_digest, BOUNDS,
            )
            self.assertEqual(inconclusive["label"], "Python replay · inconclusive")
            self.assertEqual(inconclusive["color"], renderer.COLORS["amber"])
            self.assertEqual(inconclusive["background"], renderer.COLORS["amber_bg"])


if __name__ == "__main__":
    unittest.main()
