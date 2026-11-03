"""Tests for the native patpat-repository-diagram and patpat-statechart bridge."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "patpat-repository-diagram" / "scripts"))
from statechart_bridge import clean_identifier, main


SAMPLE_LIFECYCLE = {
    "schema_version": 2,
    "type": "lifecycle",
    "language": "en",
    "title": "Payment Order Flow",
    "summary": "Sample lifecycle flow for testing bridge",
    "evidence": [
        {
            "origin": "brief",
            "id": "E1",
            "claim": "Customer initiates payment",
        },
        {
            "origin": "brief",
            "id": "E2",
            "claim": "Gateway completes or fails transaction",
        },
    ],
    "body": {
        "states": [
            {
                "id": "S_INIT",
                "label": "Order Created",
                "kind": "initial",
                "certainty": "confirmed",
                "evidence_ids": ["E1"],
            },
            {
                "id": "S_PROCESSING",
                "label": "Payment Processing",
                "kind": "state",
                "certainty": "confirmed",
                "evidence_ids": ["E1", "E2"],
            },
            {
                "id": "S_PAID",
                "label": "Paid & Settled",
                "kind": "terminal",
                "certainty": "confirmed",
                "evidence_ids": ["E2"],
            },
            {
                "id": "S_FAILED",
                "label": "Payment Failed",
                "kind": "terminal",
                "certainty": "confirmed",
                "evidence_ids": ["E2"],
            },
        ],
        "transitions": [
            {
                "id": "T_SUBMIT",
                "source": "S_INIT",
                "target": "S_PROCESSING",
                "label": "Submit Card Details",
                "kind": "transition",
                "certainty": "confirmed",
                "evidence_ids": ["E1"],
            },
            {
                "id": "T_SUCCESS",
                "source": "S_PROCESSING",
                "target": "S_PAID",
                "label": "Bank Authorization OK",
                "kind": "transition",
                "certainty": "confirmed",
                "evidence_ids": ["E2"],
            },
            {
                "id": "T_FAIL",
                "source": "S_PROCESSING",
                "target": "S_FAILED",
                "label": "Card Declined",
                "kind": "error",
                "certainty": "confirmed",
                "evidence_ids": ["E2"],
            },
        ],
    },
    "layout": {
        "direction": "TB",
        "layers": [
            ["S_INIT"],
            ["S_PROCESSING"],
            ["S_PAID", "S_FAILED"],
        ],
    },
}


class StatechartBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test_bridge_"))
        self.diagram_file = self.temp_dir / "payment_flow.diagram.json"
        self.diagram_file.write_text(json.dumps(SAMPLE_LIFECYCLE, indent=2), encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_clean_identifier(self) -> None:
        self.assertEqual(clean_identifier("order-processing"), "order_processing")
        self.assertEqual(clean_identifier("123step"), "A_123step")
        self.assertEqual(clean_identifier("T-SUBMIT_NOW"), "T_SUBMIT_NOW")

    def test_seed_model_lifecycle(self) -> None:
        out_dir = self.temp_dir / "scaffold"
        sys_argv_backup = sys.argv
        try:
            sys.argv = [
                "statechart_bridge.py",
                "seed-model",
                "--diagram",
                str(self.diagram_file),
                "--out-dir",
                str(out_dir),
                "--reader",
                "Product Manager",
                "--rule",
                "Never hand over drink if payment failed",
            ]
            exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            sys.argv = sys_argv_backup

        # Verify generated files exist
        tla_file = out_dir / "Payment_Order_Flow.tla"
        cfg_file = out_dir / "Payment_Order_Flow.cfg"
        view_file = out_dir / "view.mjs"

        self.assertTrue(tla_file.exists(), f"Missing {tla_file}")
        self.assertTrue(cfg_file.exists(), f"Missing {cfg_file}")
        self.assertTrue(view_file.exists(), f"Missing {view_file}")

        tla_content = tla_file.read_text(encoding="utf-8")
        self.assertIn("MODULE Payment_Order_Flow", tla_content)
        self.assertIn('Init == phase = "S_INIT"', tla_content)
        self.assertIn('Action_T_SUBMIT == phase = "S_INIT" /\\ phase\' = "S_PROCESSING"', tla_content)
        self.assertIn('Action_T_SUCCESS == phase = "S_PROCESSING" /\\ phase\' = "S_PAID"', tla_content)
        self.assertIn('Action_T_FAIL == phase = "S_PROCESSING" /\\ phase\' = "S_FAILED"', tla_content)
        self.assertIn('Done == phase \\in {"S_PAID", "S_FAILED"} /\\ UNCHANGED vars', tla_content)
        self.assertIn("Rule_1_", tla_content)

        cfg_content = cfg_file.read_text(encoding="utf-8")
        self.assertIn("SPECIFICATION Spec", cfg_content)
        self.assertIn("INVARIANT Rule_1_", cfg_content)

        view_content = view_file.read_text(encoding="utf-8")
        self.assertIn("Payment Processing", view_content)
        self.assertIn("Submit Card Details", view_content)
        self.assertIn("export const state =", view_content)
        self.assertIn("export const step =", view_content)

    def test_attach_bug_path(self) -> None:
        sys_argv_backup = sys.argv
        try:
            sys.argv = [
                "statechart_bridge.py",
                "attach-bug-path",
                "--diagram",
                str(self.diagram_file),
                "--trace",
                "S_INIT,T_SUBMIT,S_PROCESSING,T_FAIL,S_FAILED",
                "--rule",
                "NoPrematureDelivery",
                "--report",
                "reports/pm_audit.md",
                "--replay",
                "replayed",
            ]
            exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            sys.argv = sys_argv_backup

        updated_json = json.loads(self.diagram_file.read_text(encoding="utf-8"))
        self.assertIn("views", updated_json)
        self.assertEqual(len(updated_json["views"]), 1)

        view = updated_json["views"][0]
        self.assertEqual(view["id"], "bug_path_NoPrematureDelivery")
        self.assertEqual(view["label"], "Bug path · NoPrematureDelivery")
        self.assertEqual(view["focus"], ["S_INIT", "T_SUBMIT", "S_PROCESSING", "T_FAIL", "S_FAILED"])
        self.assertIn("breaks NoPrematureDelivery", view["note"])
        self.assertIn("replay: replayed", view["note"])

    def test_attach_bug_path_with_unknown_model_states(self) -> None:
        """Unknown states in TLC trace are noted without failing diagram validation."""
        sys_argv_backup = sys.argv
        try:
            sys.argv = [
                "statechart_bridge.py",
                "attach-bug-path",
                "--diagram",
                str(self.diagram_file),
                "--trace",
                "S_INIT,T_SUBMIT,S_PROCESSING,MODEL_INTERNAL_CRASH,S_FAILED",
                "--rule",
                "InternalCheck",
                "--replay",
                "model-only",
            ]
            exit_code = main()
            self.assertEqual(exit_code, 0)
        finally:
            sys.argv = sys_argv_backup

        updated_json = json.loads(self.diagram_file.read_text(encoding="utf-8"))
        view = updated_json["views"][0]
        # Focus omits MODEL_INTERNAL_CRASH because diagram doesn't have it
        self.assertEqual(view["focus"], ["S_INIT", "T_SUBMIT", "S_PROCESSING", "S_FAILED"])
        self.assertIn("omits model states: MODEL_INTERNAL_CRASH", view["note"])


if __name__ == "__main__":
    unittest.main()
