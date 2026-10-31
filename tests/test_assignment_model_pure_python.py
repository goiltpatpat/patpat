#!/usr/bin/env python3
"""Regression tests for pure-Python assignment model checking."""

from __future__ import annotations

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER_SCRIPT = ROOT / "skills" / "patpat-run" / "scripts" / "check_assignment_model.py"

if str(CHECKER_SCRIPT.parent) not in sys.path:
    sys.path.insert(0, str(CHECKER_SCRIPT.parent))

from check_assignment_model import (
    AssignmentState,
    explore_assignment_state_space_python,
    verify_pure_python_model,
    MUTANT_INVARIANT,
    REJECTED_WRITE_MUTANT_INVARIANT,
)


class TestPurePythonAssignmentModel(unittest.TestCase):
    def test_baseline_passes_all_invariants(self) -> None:
        """Baseline model check must pass all declared invariants."""
        result = explore_assignment_state_space_python(
            enforce_generation=True,
            inject_rejected_write=False,
        )
        self.assertTrue(result["passed"])
        self.assertIsNone(result["counterexample"])
        self.assertIsNone(result["violated_invariant"])
        self.assertGreater(result["distinct_states"], 1000)
        self.assertGreater(result["total_generated"], 4000)

    def test_stale_generation_mutant_detected(self) -> None:
        """Stale-generation mutant must violate NoStaleWrites."""
        result = explore_assignment_state_space_python(
            enforce_generation=False,
            inject_rejected_write=False,
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["violated_invariant"], MUTANT_INVARIANT)
        self.assertIsNotNone(result["counterexample"])
        trace = result["counterexample"]
        self.assertEqual(len(trace), 4)
        # Final state must contain a stale write
        final_state = trace[-1]["state"]
        stale_writes = [tok != cur for tok, cur in final_state.writes]
        self.assertTrue(any(stale_writes))

    def test_rejected_write_mutant_detected(self) -> None:
        """Rejected-write mutant must violate WritesMatchAcceptedAttempts."""
        result = explore_assignment_state_space_python(
            enforce_generation=True,
            inject_rejected_write=True,
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["violated_invariant"], REJECTED_WRITE_MUTANT_INVARIANT)
        self.assertIsNotNone(result["counterexample"])
        trace = result["counterexample"]
        self.assertEqual(len(trace), 3)
        # Final state must violate count of accepted attempts vs writes
        final_state = trace[-1]["state"]
        accepted_count = sum(1 for a in final_state.attempts if a)
        self.assertNotEqual(len(final_state.writes), accepted_count)

    def test_intentionally_violated_invariants_cause_failure(self) -> None:
        """Intentionally injected invariant violations must cause failure."""
        # 1. ActiveAssignmentHasIssuedToken violation:
        # Assigned worker has no matching token in issued list
        bad_active_state = AssignmentState(
            generation=1,
            assigned=True,
            owner="workerA",
            issued=(),
            writes=(),
            attempts=(),
            steps=0,
        )
        result = explore_assignment_state_space_python(initial_state=bad_active_state)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violated_invariant"], "ActiveAssignmentHasIssuedToken")
        self.assertIsNotNone(result["counterexample"])

        # 2. TypeOK violation (negative generation):
        bad_type_gen = AssignmentState(
            generation=-1,
            assigned=False,
            owner="noWorker",
            issued=(),
            writes=(),
            attempts=(),
            steps=0,
        )
        result = explore_assignment_state_space_python(initial_state=bad_type_gen)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violated_invariant"], "TypeOK")

        # 3. TypeOK violation (assigned=False with owner="workerA"):
        bad_type_owner = AssignmentState(
            generation=1,
            assigned=False,
            owner="workerA",
            issued=(),
            writes=(),
            attempts=(),
            steps=0,
        )
        result = explore_assignment_state_space_python(initial_state=bad_type_owner)
        self.assertFalse(result["passed"])
        self.assertEqual(result["violated_invariant"], "TypeOK")

    def test_pure_python_rejects_receipt_out_flag(self) -> None:
        """--pure-python does not support --receipt-out."""
        result = subprocess.run(
            [sys.executable, str(CHECKER_SCRIPT), "--pure-python", "--receipt-out", "/tmp/receipts"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("--receipt-out requires --tlc-jar", result.stderr)

    def test_verify_pure_python_model_passes(self) -> None:
        """verify_pure_python_model function returns 0 when all checks pass."""
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = verify_pure_python_model()
        self.assertEqual(code, 0)
        output = buf.getvalue()
        self.assertIn("Bounded assignment-generation pure-Python model: PASS", output)
        self.assertIn("Baseline: PASS", output)
        self.assertIn(f"detected violation of {MUTANT_INVARIANT}", output)
        self.assertIn(f"detected violation of {REJECTED_WRITE_MUTANT_INVARIANT}", output)

    def test_cli_pure_python_flag_exit_code_zero(self) -> None:
        """Running with --pure-python exits with code 0 on valid model."""
        res = subprocess.run(
            [sys.executable, str(CHECKER_SCRIPT), "--pure-python"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Bounded assignment-generation pure-Python model: PASS", res.stdout)

    def test_self_test_does_not_claim_model_verification(self) -> None:
        """Running --self-test tests receipt contracts and does not claim model verification."""
        res = subprocess.run(
            [sys.executable, str(CHECKER_SCRIPT), "--self-test"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("TLC parser and receipt contract self-test: PASS", res.stdout)
        self.assertNotIn("Bounded assignment-generation pure-Python model: PASS", res.stdout)


if __name__ == "__main__":
    unittest.main()
