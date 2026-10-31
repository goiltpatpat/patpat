"""Receipt-to-Python replay checks for the AssignmentGeneration pilot."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "patpat-run" / "scripts" / "replay_assignment_counterexample.py"
SPEC = importlib.util.spec_from_file_location("replay_assignment_counterexample", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
replay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replay)


def _state(
    generation: int,
    assigned: bool,
    owner: str,
    issued: str,
    writes: str,
    attempts: str,
    steps: int,
) -> dict[str, str]:
    return {
        "assigned": "TRUE" if assigned else "FALSE",
        "attempts": attempts,
        "generation": str(generation),
        "issued": issued,
        "owner": owner,
        "steps": str(steps),
        "writes": writes,
    }


def _trace() -> list[dict[str, object]]:
    states = [
        _state(0, False, "noWorker", "<<>>", "<<>>", "<<>>", 0),
        _state(1, True, "workerA", "<<[token |-> 1, worker |-> workerA]>>", "<<>>", "<<>>", 1),
        _state(
            2,
            True,
            "workerB",
            "<<[token |-> 1, worker |-> workerA], [token |-> 2, worker |-> workerB]>>",
            "<<>>",
            "<<>>",
            2,
        ),
        _state(
            2,
            True,
            "workerB",
            "<<[token |-> 1, worker |-> workerA], [token |-> 2, worker |-> workerB]>>",
            "<<[token |-> 1, current |-> 2]>>",
            "<<[accepted |-> TRUE]>>",
            3,
        ),
    ]
    actions = [
        "Initial predicate",
        "Next line 87, col 5 to line 91, col 41 of module AssignmentGeneration",
        "Next line 87, col 5 to line 91, col 41 of module AssignmentGeneration",
        "Next line 87, col 5 to line 91, col 41 of module AssignmentGeneration",
    ]
    trace: list[dict[str, object]] = []
    previous: dict[str, str] | None = None
    for index, (action, state) in enumerate(zip(actions, states), 1):
        changed = (
            []
            if previous is None
            else sorted(key for key in previous.keys() | state.keys() if previous.get(key) != state.get(key))
        )
        trace.append({"index": index, "action": action, "changed_keys": changed, "state": state})
        previous = state
    return trace


def _receipt() -> dict[str, object]:
    model = ROOT / replay.MODEL_RELATIVE
    config = ROOT / replay.CONFIG_RELATIVE
    return {
        "bounds": dict(replay.EXPECTED_BOUNDS),
        "case": "stale-generation",
        "checker": {
            "name": "TLC",
            "version": "TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)",
        },
        "configuration": {
            "constants": {
                "EnforceGeneration": False,
                "InjectRejectedWrite": False,
                "MaxGeneration": 3,
                "MaxSteps": 6,
                "NoWorker": "noWorker",
                "Workers": ["workerA", "workerB"],
            },
            "path": replay.CONFIG_RELATIVE,
            "sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        },
        "kind": "patpat-model-check-receipt",
        "model": {
            "path": replay.MODEL_RELATIVE,
            "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        },
        "mutant": dict(replay.EXPECTED_MUTANT),
        "properties": [
            {
                "name": "NoStaleWrites",
                "outcome": "counterexample",
                "counterexample_count": 1,
                "trace_selection": "shortest; canonical JSON breaks ties",
                "trace": _trace(),
            }
        ],
        "result": {"outcome": "counterexample", "tlc_exit_code": 0},
        "schema_version": 1,
    }


def _rejected_write_trace() -> list[dict[str, object]]:
    states = [
        _state(0, False, "noWorker", "<<>>", "<<>>", "<<>>", 0),
        _state(1, True, "workerA", "<<[token |-> 1, worker |-> workerA]>>", "<<>>", "<<>>", 1),
        _state(
            1,
            True,
            "workerA",
            "<<[token |-> 1, worker |-> workerA]>>",
            "<<[token |-> 1, current |-> 1]>>",
            "<<[accepted |-> FALSE]>>",
            2,
        ),
    ]
    actions = [
        "Initial predicate",
        "Next line 87, col 5 to line 91, col 41 of module AssignmentGeneration",
        "Next line 87, col 5 to line 91, col 41 of module AssignmentGeneration",
    ]
    trace: list[dict[str, object]] = []
    previous: dict[str, str] | None = None
    for index, (action, state) in enumerate(zip(actions, states), 1):
        changed = (
            []
            if previous is None
            else sorted(key for key in previous.keys() | state.keys() if previous.get(key) != state.get(key))
        )
        trace.append({"index": index, "action": action, "changed_keys": changed, "state": state})
        previous = state
    return trace


def _rejected_write_receipt() -> dict[str, object]:
    model = ROOT / replay.MODEL_RELATIVE
    config_rel = replay.SUPPORTED_MUTANTS["rejected-write"]["config_relative"]
    config = ROOT / config_rel
    return {
        "bounds": dict(replay.EXPECTED_BOUNDS),
        "case": "rejected-write",
        "checker": {
            "name": "TLC",
            "version": "TLC2 Version 2.19 of 08 August 2024 (rev: 5a47802)",
        },
        "configuration": {
            "constants": {
                "EnforceGeneration": True,
                "InjectRejectedWrite": True,
                "MaxGeneration": 3,
                "MaxSteps": 6,
                "NoWorker": "noWorker",
                "Workers": ["workerA", "workerB"],
            },
            "path": config_rel,
            "sha256": hashlib.sha256(config.read_bytes()).hexdigest(),
        },
        "kind": "patpat-model-check-receipt",
        "model": {
            "path": replay.MODEL_RELATIVE,
            "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        },
        "mutant": {
            "changed_constants": {"InjectRejectedWrite": True},
            "id": "rejected-write",
            "target_property": "WritesMatchAcceptedAttempts",
        },
        "properties": [
            {
                "counterexample_count": 1,
                "name": "WritesMatchAcceptedAttempts",
                "outcome": "counterexample",
                "trace": _rejected_write_trace(),
                "trace_selection": "shortest; canonical JSON breaks ties",
            }
        ],
        "result": {
            "distinct_states": 30,
            "outcome": "counterexample",
            "tlc_exit_code": 0,
            "total_states": 75,
        },
        "schema_version": 1,
    }


def _write_receipt(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class AssignmentGenerationReplayTests(unittest.TestCase):
    def test_saved_mutant_trace_replays_against_real_program_state_api(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_path = tmp_path / "stale-generation.json"
            _write_receipt(receipt_path, _receipt())

            report = replay.replay_receipt(receipt_path)

            model_evidence = report["evidence_layers"]["bounded_model_tlc"]
            runtime_evidence = report["evidence_layers"]["implementation_replay"]
            self.assertEqual(model_evidence["status"], "counterexample")
            self.assertEqual(model_evidence["bounds"], {"MaxGeneration": 3, "MaxSteps": 6})
            self.assertEqual(model_evidence["selected_trace_states"], 4)
            self.assertEqual(runtime_evidence["status"], "pass")
            self.assertEqual(runtime_evidence["outcome"], "rejected-as-expected")
            self.assertEqual(runtime_evidence["observed_error"], "stale assignment generation")
            self.assertTrue(runtime_evidence["assignment_prefix_matches_model"])
            self.assertTrue(runtime_evidence["persisted_state_unchanged"])
            self.assertEqual(runtime_evidence["state_sha256_before"], runtime_evidence["state_sha256_after"])
            self.assertTrue(runtime_evidence["actor_authentication"].startswith("not-exercised;"))

    def test_replay_rejects_a_trace_with_incorrect_changed_keys(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt = _receipt()
            receipt["properties"][0]["trace"][3]["changed_keys"] = ["writes"]
            receipt_path = tmp_path / "invalid.json"
            _write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(replay.ReplayError, "changed_keys"):
                replay.replay_receipt(receipt_path)

    def test_replay_rejects_a_stale_token_that_was_never_issued(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt = _receipt()
            receipt["properties"][0]["trace"][3]["state"]["writes"] = "<<[token |-> 3, current |-> 2]>>"
            receipt_path = tmp_path / "unissued-token.json"
            _write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(replay.ReplayError, "token was not issued"):
                replay.replay_receipt(receipt_path)

    def test_replay_rejects_malformed_result_object(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt = _receipt()
            receipt["result"] = []
            receipt_path = tmp_path / "malformed-result.json"
            _write_receipt(receipt_path, receipt)

            with self.assertRaisesRegex(replay.ReplayError, "does not report a counterexample"):
                replay.replay_receipt(receipt_path)

    def test_receipt_size_limit_stops_after_one_byte_over_limit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            receipt_path = tmp_path / "oversized.json"
            receipt_path.write_bytes(b"123456")
            with unittest.mock.patch.object(replay, "MAX_RECEIPT_BYTES", 4):
                with self.assertRaisesRegex(replay.ReplayError, "exceeds the 4-byte limit"):
                    replay._load_json_bytes(receipt_path)

    def test_replay_report_never_overwrites_an_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp_path = Path(td)
            destination = tmp_path / "report.json"
            destination.write_text("keep\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                replay.write_report(destination, {"kind": replay.REPLAY_KIND})

            self.assertEqual(destination.read_text(encoding="utf-8"), "keep\n")



    def test_replay_valid_rejected_write_counterexample_end_to_end(self) -> None:
        """A valid rejected-write receipt must parse, replay, and confirm persisted state unchanged."""
        receipt_data = _rejected_write_receipt()
        with tempfile.TemporaryDirectory() as td:
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")
            raw_states, parsed_states = replay.parse_receipt(receipt_path)
            self.assertEqual(len(parsed_states), 3)

            report = replay.replay_receipt(receipt_path)
            self.assertEqual(report["verdict"], "pass")
            self.assertEqual(report["evidence_layers"]["bounded_model_tlc"]["property"], "WritesMatchAcceptedAttempts")
            runtime = report["evidence_layers"]["implementation_replay"]
            self.assertEqual(runtime["status"], "pass")
            self.assertEqual(runtime["outcome"], "rejected-as-expected")
            self.assertTrue(runtime["persisted_state_unchanged"])
            self.assertTrue(runtime["persisted_head_is_none"])
            self.assertEqual(runtime["state_sha256_before"], runtime["state_sha256_after"])

    def test_replay_rejects_malformed_rejected_write_trace(self) -> None:
        """Rejected-write replay rejects traces with fewer than 3 states or invalid transitions."""
        receipt_data = _rejected_write_receipt()
        # Fewer than 3 states
        receipt_data["properties"][0]["trace"] = _rejected_write_trace()[:2]
        with tempfile.TemporaryDirectory() as td:
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")
            with self.assertRaises(replay.ReplayError) as ctx:
                replay.parse_receipt(receipt_path)
            self.assertIn("3-state counterexample trace", str(ctx.exception))

    def test_replay_rejects_rejected_write_trace_without_invariant_violation(self) -> None:
        """Trace that does not violate WritesMatchAcceptedAttempts is rejected."""
        receipt_data = _rejected_write_receipt()
        # Non-mutant rejected write has 0 writes and 0 accepted attempts -> len(writes) == accepted_count
        trace = _rejected_write_trace()
        trace[2]["state"]["writes"] = "<<>>"
        trace[2]["changed_keys"] = sorted(["attempts", "steps"])
        receipt_data["properties"][0]["trace"] = trace
        with tempfile.TemporaryDirectory() as td:
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")
            with self.assertRaises(replay.ReplayError) as ctx:
                replay.parse_receipt(receipt_path)
            self.assertIn("does not violate WritesMatchAcceptedAttempts", str(ctx.exception))

    def test_replay_rejects_rejected_write_incorrect_changed_keys(self) -> None:
        """Rejected-write trace with bogus changed_keys is rejected."""
        receipt_data = _rejected_write_receipt()
        trace = _rejected_write_trace()
        trace[2]["changed_keys"] = ["bogus"]
        receipt_data["properties"][0]["trace"] = trace
        with tempfile.TemporaryDirectory() as td:
            receipt_path = Path(td) / "receipt.json"
            receipt_path.write_text(json.dumps(receipt_data), encoding="utf-8")
            with self.assertRaises(replay.ReplayError) as ctx:
                replay.parse_receipt(receipt_path)
            self.assertIn("changed_keys do not match", str(ctx.exception))

    def test_cascading_invalidation_advances_downstream_generation(self) -> None:
        import subprocess
        import sys
        sys.path.insert(0, str(ROOT / "skills" / "patpat-run" / "scripts"))
        import program_state
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=root, check=True)
            (root / "README.md").write_text("# Test\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True)
            head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            plan = program_state.example_plan()
            plan["delivery"] = {"authority": "none", "actions": []}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            program_id = "test-dag"
            state = program_state.initialize(root, program_id, plan_path)

            # Bind gate evidence
            ev_path = root / "ev.txt"
            ev_path.write_text("ev\n", encoding="utf-8")
            ev = program_state.bind_parallel_gate_evidence(ev_path)
            receipt = {
                "schema_version": 2,
                "kind": program_state.PARALLEL_GATE_KIND,
                "program_id": program_id,
                "plan_digest": state["plan_digest"],
                "integration_owner": "coord",
                "checks": {name: True for name in program_state.PARALLEL_GATE_CHECKS},
                "supporting_evidence": {name: [dict(ev)] for name in program_state.PARALLEL_GATE_CHECKS},
                "isolation_identities": {"contract": "w1", "consumer": "w2"},
            }
            receipt_path = root / "gate.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            program_state.set_gate(root, program_id, "dispatch", True, "open", receipt_path, "coord")

            # Assign upstream unit contract
            c_res = program_state.assign_unit(root, program_id, "contract", "workerA", "w1", 0)
            self.assertEqual(c_res["units"]["contract"]["assignment"]["generation"], 1)

            # Re-assign contract to workerB (invalidates generation 1 and advances to 2)
            c_res2 = program_state.assign_unit(root, program_id, "contract", "workerB", "w1", 1)
            self.assertEqual(c_res2["units"]["contract"]["assignment"]["generation"], 2)

            # Stale workerA attempting to set head with generation 1 must fail
            with self.assertRaises(program_state.ProgramStateError) as ctx:
                program_state.set_head(root, program_id, "contract", head, None, 1)
            self.assertIn("stale assignment generation", str(ctx.exception))

            # Dispatch close cascades invalidation to all active assignments, advancing generation
            program_state.set_gate(root, program_id, "dispatch", False, "close gate", receipt_path, "coord")
            closed_state = program_state.load_state(root, program_id)
            self.assertIsNone(program_state.assignment_snapshot(closed_state["units"]["contract"]))
            self.assertEqual(closed_state["units"]["contract"]["assignment"]["generation"], 3)

    def test_rejected_write_preserves_preexisting_non_empty_head_sha(self) -> None:
        """A rejected write with an unissued token preserves pre-existing, non-null head_sha and state bytes."""
        import subprocess
        import sys
        sys.path.insert(0, str(ROOT / "skills" / "patpat-run" / "scripts"))
        import program_state

        with tempfile.TemporaryDirectory(prefix="patpat-test-preexisting-head-") as td:
            root = Path(td)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.email", "test@test.local"], cwd=root, check=True)
            (root / "README.md").write_text("# Test\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True)
            initial_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()

            plan = program_state.example_plan()
            plan["delivery"] = {"authority": "none", "actions": []}
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            program_id = "test-preexisting-head"
            state = program_state.initialize(root, program_id, plan_path)

            # Bind gate evidence and open dispatch
            ev_path = root / "ev.txt"
            ev_path.write_text("ev\n", encoding="utf-8")
            ev = program_state.bind_parallel_gate_evidence(ev_path)
            receipt = {
                "schema_version": 2,
                "kind": program_state.PARALLEL_GATE_KIND,
                "program_id": program_id,
                "plan_digest": state["plan_digest"],
                "integration_owner": "coord",
                "checks": {name: True for name in program_state.PARALLEL_GATE_CHECKS},
                "supporting_evidence": {name: [dict(ev)] for name in program_state.PARALLEL_GATE_CHECKS},
                "isolation_identities": {"contract": "w1", "consumer": "w2"},
            }
            receipt_path = root / "gate.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            program_state.set_gate(root, program_id, "dispatch", True, "open", receipt_path, "coord")

            # Assign unit contract to workerA (generation 0 -> 1)
            assign_res = program_state.assign_unit(root, program_id, "contract", "workerA", "w1", 0)
            self.assertEqual(assign_res["units"]["contract"]["assignment"]["generation"], 1)

            # Establish pre-existing non-null head_sha via supported API
            written_state = program_state.set_head(root, program_id, "contract", initial_head, None, 1)
            self.assertEqual(written_state["units"]["contract"]["head_sha"], initial_head)
            self.assertEqual(len(initial_head), 40)

            # Create a second real commit in Git to represent a new candidate head
            (root / "second.txt").write_text("second\n", encoding="utf-8")
            subprocess.run(["git", "add", "second.txt"], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "second commit"], cwd=root, check=True)
            new_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
            self.assertNotEqual(initial_head, new_head)
            self.assertEqual(len(new_head), 40)

            # Record persisted state bytes before the rejected write attempt
            persisted_file = program_state.state_path(root, program_id)
            bytes_before = persisted_file.read_bytes()

            # Attempt rejected write with unissued generation token 0
            with self.assertRaises(program_state.ProgramStateError) as ctx:
                program_state.set_head(root, program_id, "contract", new_head, initial_head, 0)
            self.assertIn("stale assignment generation", str(ctx.exception))

            # Attempt rejected write with unissued generation token 99
            with self.assertRaises(program_state.ProgramStateError) as ctx:
                program_state.set_head(root, program_id, "contract", new_head, initial_head, 99)
            self.assertIn("stale assignment generation", str(ctx.exception))

            # Assert head_sha remains exactly unchanged
            persisted_after = program_state.load_state(root, program_id)
            self.assertEqual(persisted_after["units"]["contract"]["head_sha"], initial_head)

            # Assert persisted state bytes remain completely unchanged
            bytes_after = persisted_file.read_bytes()
            self.assertEqual(bytes_before, bytes_after)


if __name__ == "__main__":
    unittest.main()
