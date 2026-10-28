#!/usr/bin/env python3
"""Exercise the task ontology and its packaged canonical guidance."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import validate


class GeneralTaskOntologyTests(unittest.TestCase):
    def test_target_vocabulary_and_mutation_gate(self):
        for target, level, expected_valid in (
            ("Task", "LOCAL_MUTATION", True),
            ("EngineeringTask", "LOCAL_MUTATION", True),
            ("UnknownTask", "LOCAL_MUTATION", False),
            ("Task", "READ_ONLY", False),
        ):
            with self.subTest(target=target, level=level):
                ontology = {
                    "schema": "patpat-ontology/v1", "mutation_level": level,
                    "target_entity": target, "requires_state": [],
                    "produces_state": [], "verification_cmd": "",
                }
                errors = []
                validate.validate_skill_ontology(
                    {"metadata": {"patpat.ontology": json.dumps(ontology)}},
                    Path("skills/patpat-loop/SKILL.md"), "router", errors,
                )
                self.assertEqual(not errors, expected_valid, errors)

    def test_native_and_portable_packages_include_current_guidance(self):
        relative = Path("skills/patpat-loop/references/general-task-judgment.md")
        expected = (ROOT / relative).read_bytes()
        with tempfile.TemporaryDirectory(prefix="patpat-general-task-test-") as temp:
            for name, script in (
                ("native", "stage_plugin.py"),
                ("portable", "stage_agent_plugin.py"),
            ):
                with self.subTest(package=name):
                    target = Path(temp) / name
                    subprocess.run(
                        [sys.executable, str(ROOT / "scripts" / script), "--target", str(target)],
                        cwd=ROOT, check=True, capture_output=True, text=True,
                    )
                    self.assertEqual((target / relative).read_bytes(), expected)
                    for skill in ("patpat", "patpat-loop"):
                        text = (target / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
                        self.assertIn('"target_entity":"Task"', text)


if __name__ == "__main__":
    unittest.main()
