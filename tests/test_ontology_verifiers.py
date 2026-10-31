#!/usr/bin/env python3
"""Regression tests for ontology verifiers and enforcement in validate.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import validate

PLAN_VERIFIER = ROOT / "skills" / "patpat-plan" / "scripts" / "verify_plan.py"
REVIEW_VERIFIER = ROOT / "skills" / "patpat-review" / "scripts" / "verify_review.py"
DELIVERY_VERIFIER = ROOT / "skills" / "patpat-ship" / "scripts" / "verify_delivery.py"

PLAN_DIR = ROOT / "skills" / "patpat-plan" / "scripts"
REVIEW_DIR = ROOT / "skills" / "patpat-review" / "scripts"
DELIVERY_DIR = ROOT / "skills" / "patpat-ship" / "scripts"

for p in (PLAN_DIR, REVIEW_DIR, DELIVERY_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import verify_plan
import verify_review
import verify_delivery

DUMMY_SHA = "a" * 40


def _create_test_git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, check=True)
    (path / "file.txt").write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial commit"], cwd=path, check=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True)
    return res.stdout.strip()


class TestOntologyVerifiersDirect(unittest.TestCase):
    """Direct execution tests for bundled verifiers."""

    def test_plan_verifier_self_test(self) -> None:
        result = subprocess.run(
            [sys.executable, str(PLAN_VERIFIER), "--self-test"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Plan verifier self-test passed.", result.stdout)

    def test_plan_verifier_missing_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing execution plan", result.stderr)

    def test_plan_verifier_invalid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_file = Path(temp) / ".patpat" / "plan.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_file.write_text(json.dumps({"schema": "unknown"}), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertTrue(
                "plan must contain exactly" in result.stderr or "schema_version" in result.stderr,
                f"Unexpected stderr: {result.stderr}",
            )

    def test_plan_verifier_valid_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_file = Path(temp) / ".patpat" / "plan.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_data = verify_plan.example_plan()
            plan_file.write_text(json.dumps(plan_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Execution plan verified:", result.stdout)

    def test_plan_verifier_rejects_dag_cycle_in_supported_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_file = Path(temp) / ".patpat" / "plan.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_data = verify_plan.example_plan()
            # Create a 2-node cycle: contract -> consumer -> contract
            plan_data["units"][0]["depends_on"] = ["consumer"]
            plan_file.write_text(json.dumps(plan_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("unit dependency graph must be acyclic", result.stderr)

    def test_plan_verifier_rejects_unknown_dependency_in_supported_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_file = Path(temp) / ".patpat" / "plan.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_data = verify_plan.example_plan()
            plan_data["units"][1]["depends_on"] = ["non-existent-unit"]
            plan_file.write_text(json.dumps(plan_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("has unknown dependencies", result.stderr)

    def test_plan_verifier_rejects_ownership_overlap_in_supported_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plan_file = Path(temp) / ".patpat" / "plan.json"
            plan_file.parent.mkdir(parents=True, exist_ok=True)
            plan_data = verify_plan.example_plan()
            # Make units unordered and overlap on files
            plan_data["units"][1]["depends_on"] = []
            plan_data["units"][0]["files"] = ["src/*"]
            plan_data["units"][1]["files"] = ["src/consumer.py"]
            plan_file.write_text(json.dumps(plan_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(PLAN_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("overlapping ownership", result.stderr)

    def test_plan_verifier_standalone_without_canonical_validator(self) -> None:
        """Prove DAG, dependency-reference, and ownership checks work without canonical_plan_validator."""
        with patch.object(verify_plan, "canonical_plan_validator", None):
            with tempfile.TemporaryDirectory() as temp:
                dummy_path = Path(temp) / "plan.json"

                # 1. Valid plan passes
                valid_data = verify_plan.example_plan()
                res = verify_plan.verify_plan_data(valid_data, dummy_path)
                self.assertEqual(len(res["units"]), 2)

                # 2. Cycle is rejected
                cycle_data = verify_plan.example_plan()
                cycle_data["units"][0]["depends_on"] = ["consumer"]
                with self.assertRaises(verify_plan.PlanVerificationError) as ctx:
                    verify_plan.verify_plan_data(cycle_data, dummy_path)
                self.assertIn("unit dependency graph must be acyclic", str(ctx.exception))

                # 3. Unknown dependency is rejected
                unknown_dep_data = verify_plan.example_plan()
                unknown_dep_data["units"][1]["depends_on"] = ["missing-unit"]
                with self.assertRaises(verify_plan.PlanVerificationError) as ctx:
                    verify_plan.verify_plan_data(unknown_dep_data, dummy_path)
                self.assertIn("has unknown dependencies", str(ctx.exception))

                # 4. Overlapping ownership between unordered units is rejected
                overlap_data = verify_plan.example_plan()
                overlap_data["units"][1]["depends_on"] = []
                overlap_data["units"][0]["files"] = ["src/*"]
                overlap_data["units"][1]["files"] = ["src/consumer.py"]
                with self.assertRaises(verify_plan.PlanVerificationError) as ctx:
                    verify_plan.verify_plan_data(overlap_data, dummy_path)
                self.assertIn("overlapping ownership", str(ctx.exception))

    def test_review_verifier_self_test(self) -> None:
        result = subprocess.run(
            [sys.executable, str(REVIEW_VERIFIER), "--self-test"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Review verifier self-test passed.", result.stdout)

    def test_review_verifier_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(REVIEW_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing review receipt", result.stderr)

    def test_review_verifier_failing_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / ".patpat" / "review-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-review-receipt",
                "verdict": "fail",
                "actor": "reviewer",
                "summary": "issues found",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(REVIEW_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("expected 'pass'", result.stderr)

    def test_review_verifier_matching_head_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            real_sha = _create_test_git_repo(Path(temp))
            receipt_file = Path(temp) / ".patpat" / "review-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-review-receipt",
                "verdict": "pass",
                "actor": "patpat-reviewer",
                "summary": "All checks cleared",
                "head_sha": real_sha,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(REVIEW_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Review cleared:", result.stdout)

    def test_review_verifier_non_git_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / ".patpat" / "review-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-review-receipt",
                "verdict": "pass",
                "actor": "patpat-reviewer",
                "summary": "All checks cleared",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(REVIEW_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("failed to establish git HEAD", result.stderr)

    def test_review_verifier_git_command_failure_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / "review.json"
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-review-receipt",
                "verdict": "pass",
                "actor": "patpat-reviewer",
                "summary": "All checks cleared",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            with patch("subprocess.run", side_effect=OSError("git not found")):
                with self.assertRaises(verify_review.ReviewVerificationError) as ctx:
                    verify_review.verify_review(receipt_file, root=Path(temp))
                self.assertIn("failed to establish git HEAD", str(ctx.exception))

    def test_review_verifier_git_head_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _create_test_git_repo(Path(temp))
            receipt_file = Path(temp) / ".patpat" / "review-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-review-receipt",
                "verdict": "pass",
                "actor": "patpat-reviewer",
                "summary": "All checks cleared",
                "head_sha": "b" * 40,  # Mismatched SHA!
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(REVIEW_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("does not match workspace git HEAD", result.stderr)

    def test_delivery_verifier_self_test(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DELIVERY_VERIFIER), "--self-test"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Delivery verifier self-test passed.", result.stdout)

    def test_delivery_verifier_missing_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = subprocess.run(
                [sys.executable, str(DELIVERY_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("missing delivery receipt", result.stderr)

    def test_delivery_verifier_invalid_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / ".patpat" / "delivery-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-delivery-receipt",
                "status": "draft",
                "pr_number": 12,
                "pr_url": "https://example.com/pr/12",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DELIVERY_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("expected 'ready' or 'merged'", result.stderr)

    def test_delivery_verifier_matching_head_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            real_sha = _create_test_git_repo(Path(temp))
            receipt_file = Path(temp) / ".patpat" / "delivery-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-delivery-receipt",
                "status": "ready",
                "pr_number": 42,
                "pr_url": "https://github.com/goiltpatpat/patpat/pull/42",
                "head_sha": real_sha,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DELIVERY_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Delivery PR ready:", result.stdout)

    def test_delivery_verifier_non_git_directory_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / ".patpat" / "delivery-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-delivery-receipt",
                "status": "ready",
                "pr_number": 42,
                "pr_url": "https://github.com/goiltpatpat/patpat/pull/42",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DELIVERY_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("failed to establish git HEAD", result.stderr)

    def test_delivery_verifier_git_command_failure_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            receipt_file = Path(temp) / "delivery.json"
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-delivery-receipt",
                "status": "ready",
                "pr_number": 42,
                "pr_url": "https://github.com/goiltpatpat/patpat/pull/42",
                "head_sha": DUMMY_SHA,
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            with patch("subprocess.run", side_effect=OSError("git not found")):
                with self.assertRaises(verify_delivery.DeliveryVerificationError) as ctx:
                    verify_delivery.verify_delivery(receipt_file, root=Path(temp))
                self.assertIn("failed to establish git HEAD", str(ctx.exception))

    def test_delivery_verifier_git_head_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            _create_test_git_repo(Path(temp))
            receipt_file = Path(temp) / ".patpat" / "delivery-receipt.json"
            receipt_file.parent.mkdir(parents=True, exist_ok=True)
            receipt_data = {
                "schema_version": 1,
                "kind": "patpat-delivery-receipt",
                "status": "ready",
                "pr_number": 42,
                "pr_url": "https://github.com/goiltpatpat/patpat/pull/42",
                "head_sha": "b" * 40,  # Mismatched SHA!
            }
            receipt_file.write_text(json.dumps(receipt_data), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(DELIVERY_VERIFIER), "--root", temp],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("does not match workspace git HEAD", result.stderr)


class TestValidateOntologyEnforcement(unittest.TestCase):
    """Tests that validate.py rejects generic commands and missing verifiers."""

    def test_generic_command_rejected_for_declared_state(self) -> None:
        for generic_cmd in ("git status", "git status --short", "git diff", "git diff --check"):
            with self.subTest(cmd=generic_cmd):
                ontology = {
                    "schema": "patpat-ontology/v1",
                    "mutation_level": "READ_ONLY",
                    "target_entity": "EngineeringTask",
                    "requires_state": [],
                    "produces_state": ["execution-plan-settled"],
                    "verification_cmd": generic_cmd,
                }
                errors: list[str] = []
                validate.validate_skill_ontology(
                    {"metadata": {"patpat.ontology": json.dumps(ontology)}},
                    Path("skills/patpat-plan/SKILL.md"),
                    "read-only",
                    errors,
                )
                self.assertTrue(
                    any("cannot prove" in err for err in errors),
                    f"Expected rejection for generic cmd {generic_cmd}, got: {errors}",
                )

    def test_enforced_verifier_commands_mismatch(self) -> None:
        skill_checks = [
            (
                "skills/patpat-plan/SKILL.md",
                "READ_ONLY",
                "read-only",
                ["execution-plan-settled"],
                "verify_something_else.py",
                "plan verification_cmd must invoke its bundled verifier",
            ),
            (
                "skills/patpat-review/SKILL.md",
                "READ_ONLY",
                "read-only",
                ["delivery-review-cleared"],
                "echo ok",
                "review verification_cmd must invoke its bundled verifier",
            ),
            (
                "skills/patpat-ship/SKILL.md",
                "DESTRUCTIVE",
                "mutating",
                ["delivery-pr-ready"],
                "git commit",
                "delivery verification_cmd must invoke its bundled verifier",
            ),
        ]
        for path_str, mutation_level, policy, produces, bad_cmd, expected_error in skill_checks:
            with self.subTest(skill=path_str):
                ontology = {
                    "schema": "patpat-ontology/v1",
                    "mutation_level": mutation_level,
                    "target_entity": "EngineeringTask",
                    "requires_state": [],
                    "produces_state": produces,
                    "verification_cmd": bad_cmd,
                }
                errors: list[str] = []
                validate.validate_skill_ontology(
                    {"metadata": {"patpat.ontology": json.dumps(ontology)}},
                    Path(path_str),
                    policy,
                    errors,
                )
                self.assertTrue(
                    any(expected_error in err for err in errors),
                    f"Expected '{expected_error}' for {path_str}, got: {errors}",
                )

    def test_missing_bundled_verifier_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            temp_root = Path(temp)
            errors: list[str] = []
            validate.validate_workspace_mapper_resource(temp_root, errors)
            self.assertTrue(any("missing plan verifier" in err for err in errors))
            self.assertTrue(any("missing review verifier" in err for err in errors))
            self.assertTrue(any("missing delivery verifier" in err for err in errors))
            self.assertTrue(any("missing workspace mapper verifier" in err for err in errors))

    def test_actual_repo_skills_pass_ontology_validation(self) -> None:
        errors: list[str] = []
        skills_root = ROOT / "skills"
        ontology_records: dict[str, tuple[dict[str, object], Path]] = {}
        for skill_dir in validate.skill_directories(skills_root):
            skill_file = skill_dir / "SKILL.md"
            frontmatter, _ = validate.parse_frontmatter(skill_file)
            role = validate.SKILL_POLICIES.get(skill_dir.name)
            ontology = validate.validate_skill_ontology(frontmatter, skill_file, role, errors)
            if ontology is not None:
                ontology_records[skill_dir.name] = (ontology, skill_file)
        self.assertEqual(errors, [], f"Active repo skills failed ontology validation: {errors}")
        validate.validate_ontology_graph(ontology_records, errors)
        self.assertEqual(errors, [], f"Active repo ontology graph failed validation: {errors}")


if __name__ == "__main__":
    unittest.main()
