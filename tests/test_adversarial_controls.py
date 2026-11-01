"""Unit tests for Patpat adversarial control contracts."""

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.eval_adversarial_controls import (
    CLASSIFICATION,
    SCENARIOS,
    main,
    mutation_is_rejected,
    run_all_adversarial_evals,
    run_scenario,
    eval_stale_verification,
    eval_verification_theater,
    eval_architecture_drift,
    eval_adversarial_self_review,
    eval_anti_slop_behavior,
    eval_credential_leakage_and_limits,
)


def test_scenario_1_stale_verification():
    res = eval_stale_verification()
    assert res["classification"] == CLASSIFICATION
    assert res["observable"] == "stale-verification"


def test_scenario_2_verification_theater():
    res = eval_verification_theater()
    assert res["classification"] == CLASSIFICATION
    assert res["observable"].startswith("proxy-theater-rejected")


def test_scenario_3_architecture_drift():
    res = eval_architecture_drift()
    assert res["classification"] == CLASSIFICATION
    assert res["observable"] == "return-to-design"


def test_scenario_4_adversarial_self_review():
    res = eval_adversarial_self_review()
    assert res["classification"] == CLASSIFICATION
    assert "findings-surfaced" in res["observable"]


def test_scenario_5_anti_slop_behavior():
    res = eval_anti_slop_behavior()
    assert res["classification"] == CLASSIFICATION


def test_scenario_6_credential_leakage_and_limits():
    res = eval_credential_leakage_and_limits()
    assert res["classification"] == CLASSIFICATION


def test_every_scenario_rejects_its_real_collaborator_mutant():
    results = run_all_adversarial_evals()
    assert len(results) == 6
    assert all(r["status"] == "PASS" and r["mutation_rejected"] is True for r in results)


def test_mutation_probe_restores_collaborator_and_reports_vacuous_scenario():
    scenario, module, attribute, mutant = SCENARIOS[0]
    original = getattr(module, attribute)
    assert mutation_is_rejected(scenario, module, attribute, mutant) is True
    assert getattr(module, attribute) is original
    assert mutation_is_rejected(lambda: {}, module, attribute, mutant) is False
    assert getattr(module, attribute) is original


def test_vacuous_scenario_and_failing_scenario_are_reported_as_failures():
    module, attribute, mutant = SCENARIOS[0][1:]
    vacuous = run_scenario(lambda: {"scenario": "vacuous"}, module, attribute, mutant)
    assert vacuous["status"] == "FAIL" and vacuous["mutation_rejected"] is False

    def failing():
        raise AssertionError("seeded failure")

    failed = run_scenario(failing, module, attribute, mutant)
    assert failed["status"] == "FAIL" and failed["error"] == "seeded failure"


def test_main_exits_nonzero_when_a_scenario_regresses():
    _, module, attribute, mutant = SCENARIOS[0]
    original = getattr(module, attribute)
    setattr(module, attribute, mutant)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            assert main() == 1
    finally:
        setattr(module, attribute, original)


def test_remote_capability_is_not_remote_authority():
    """Prove that remote capability is not remote authority across all 5 authority cases."""
    from scripts.dry_run_loop import ship_plan, unit_checkpoint_plan

    # Case 1: Patpat activation alone -> no push authority
    res_case1 = unit_checkpoint_plan(
        unit_verified=True,
        patpat_activated=True,
        remote_configured=True,
    )
    assert res_case1 == "checkpoint-local-only", f"Expected checkpoint-local-only, got {res_case1}"

    # Case 2: Explicit local-only prohibition -> no push authority
    res_case2 = unit_checkpoint_plan(
        unit_verified=True,
        explicit_delivery=True,
        opt_out=True,
        remote_configured=True,
    )
    assert res_case2 == "checkpoint-local-only", f"Expected checkpoint-local-only, got {res_case2}"

    # Case 3: Explicit delivery -> non-force delivery permitted
    res_case3 = unit_checkpoint_plan(
        unit_verified=True,
        explicit_delivery=True,
        opt_out=False,
        remote_configured=True,
    )
    assert res_case3 == "push-verified-unit-snapshot", f"Expected push-verified-unit-snapshot, got {res_case3}"

    # Case 4: Continuation authority -> qualified progress push allowed, but still no merge authority
    res_case4_push = unit_checkpoint_plan(
        unit_verified=True,
        continuation=True,
        opt_out=False,
        remote_configured=True,
    )
    assert res_case4_push == "push-verified-unit-snapshot", f"Expected push-verified-unit-snapshot, got {res_case4_push}"

    ship_case4 = ship_plan(
        path="mutating",
        verified=True,
        reviewed=True,
        patpat_activated=True,
        explicit_delivery=False,
        repo_allows_delivery=True,
        opt_out=False,
        explicit_merge=False,
        continuation=True,
        ci="green",
    )
    assert ship_case4 == "commit-pr-then-drive-to-merge-ready", f"Continuation must stop merge-ready, got {ship_case4}"

    # Explicit land/merge required for merge
    ship_merge = ship_plan(
        path="mutating",
        verified=True,
        reviewed=True,
        patpat_activated=True,
        explicit_delivery=False,
        repo_allows_delivery=True,
        opt_out=False,
        explicit_merge=True,
        continuation=False,
        ci="green",
    )
    assert ship_merge == "merge", f"Explicit merge must merge, got {ship_merge}"

    # Case 5: Remote configured & credentials available alone -> no push authority
    res_case5 = unit_checkpoint_plan(
        unit_verified=True,
        patpat_activated=True,
        remote_configured=True,
        explicit_delivery=False,
        continuation=False,
        explicit_merge=False,
    )
    assert res_case5 == "checkpoint-local-only", f"Remote capability alone must not grant push authority, got {res_case5}"





class TestAdversarialControls(unittest.TestCase):
    def test_scenario_1_stale_verification(self):
        test_scenario_1_stale_verification()

    def test_scenario_2_verification_theater(self):
        test_scenario_2_verification_theater()

    def test_scenario_3_architecture_drift(self):
        test_scenario_3_architecture_drift()

    def test_scenario_4_adversarial_self_review(self):
        test_scenario_4_adversarial_self_review()

    def test_scenario_5_anti_slop_behavior(self):
        test_scenario_5_anti_slop_behavior()

    def test_scenario_6_credential_leakage_and_limits(self):
        test_scenario_6_credential_leakage_and_limits()

    def test_every_scenario_rejects_its_real_collaborator_mutant(self):
        test_every_scenario_rejects_its_real_collaborator_mutant()

    def test_mutation_probe_restores_collaborator_and_reports_vacuous_scenario(self):
        test_mutation_probe_restores_collaborator_and_reports_vacuous_scenario()

    def test_vacuous_scenario_and_failing_scenario_are_reported_as_failures(self):
        test_vacuous_scenario_and_failing_scenario_are_reported_as_failures()

    def test_main_exits_nonzero_when_a_scenario_regresses(self):
        test_main_exits_nonzero_when_a_scenario_regresses()

    def test_remote_capability_is_not_remote_authority(self):
        test_remote_capability_is_not_remote_authority()

if __name__ == "__main__":
    test_scenario_1_stale_verification()
    test_scenario_2_verification_theater()
    test_scenario_3_architecture_drift()
    test_scenario_4_adversarial_self_review()
    test_scenario_5_anti_slop_behavior()
    test_scenario_6_credential_leakage_and_limits()
    test_every_scenario_rejects_its_real_collaborator_mutant()
    test_mutation_probe_restores_collaborator_and_reports_vacuous_scenario()
    test_vacuous_scenario_and_failing_scenario_are_reported_as_failures()
    test_main_exits_nonzero_when_a_scenario_regresses()
    test_remote_capability_is_not_remote_authority()
    print("All adversarial control tests passed.")
