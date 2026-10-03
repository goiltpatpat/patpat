"""Unit tests for Patpat adversarial controls and behavioral invariants."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.eval_adversarial_controls import (
    eval_stale_verification,
    eval_verification_theater,
    eval_architecture_drift,
    eval_adversarial_self_review,
    eval_anti_slop_behavior,
    eval_credential_leakage_and_limits,
)


def test_scenario_1_stale_verification():
    res = eval_stale_verification()
    assert res["status"] == "PASS"
    assert res["observable"] == "stale-verification"


def test_scenario_2_verification_theater():
    res = eval_verification_theater()
    assert res["status"] == "PASS"
    assert res["observable"] == "proxy-theater-rejected"


def test_scenario_3_architecture_drift():
    res = eval_architecture_drift()
    assert res["status"] == "PASS"
    assert res["observable"] == "return-to-design"


def test_scenario_4_adversarial_self_review():
    res = eval_adversarial_self_review()
    assert res["status"] == "PASS"
    assert "findings-surfaced" in res["observable"]


def test_scenario_5_anti_slop_behavior():
    res = eval_anti_slop_behavior()
    assert res["status"] == "PASS"


def test_scenario_6_credential_leakage_and_limits():
    res = eval_credential_leakage_and_limits()
    assert res["status"] == "PASS"


if __name__ == "__main__":
    test_scenario_1_stale_verification()
    test_scenario_2_verification_theater()
    test_scenario_3_architecture_drift()
    test_scenario_4_adversarial_self_review()
    test_scenario_5_anti_slop_behavior()
    test_scenario_6_credential_leakage_and_limits()
    print("All 6 adversarial control tests passed.")
