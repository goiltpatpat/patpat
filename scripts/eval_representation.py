#!/usr/bin/env python3
"""Deterministic contract eval for earned representation. No git writes."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dry_run_loop  # noqa: E402


EARNED = ROOT / "skills" / "patpat-loop" / "references" / "earned-representation.md"
HOW_REPORT = ROOT / "skills" / "patpat-inspect" / "references" / "how-report.md"
INSPECT_SKILL = ROOT / "skills" / "patpat-inspect" / "SKILL.md"
ARCHITECT_SKILL = ROOT / "skills" / "patpat-architect" / "SKILL.md"
REVIEW_SKILL = ROOT / "skills" / "patpat-review" / "SKILL.md"
INVESTIGATION = ROOT / "skills" / "patpat-loop" / "playbooks" / "investigation.md"
ARCHITECTURE_CHANGE = ROOT / "skills" / "patpat-loop" / "playbooks" / "architecture-change.md"
INDEPENDENT_REVIEW = ROOT / "skills" / "patpat-loop" / "playbooks" / "independent-review.md"
PROTOCOL = ROOT / "skills" / "patpat-loop" / "references" / "operating-protocol.md"
CHANGE_SKILL = ROOT / "skills" / "patpat-change" / "SKILL.md"
DEBUG_SKILL = ROOT / "skills" / "patpat-debug" / "SKILL.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def assert_earned_reference() -> None:
    if not EARNED.is_file():
        raise AssertionError("missing earned-representation.md")
    blob = _text(EARNED)
    for needle in (
        "smallest representation",
        "compact pseudocode",
        "call tree",
        "shallow tree",
        "component tree",
        "sequence or flow",
        "diff-shaped",
        "focused artifact",
        "Do not visualize by default",
        "/show-me",
    ):
        if needle.lower() not in blob.lower() and needle not in blob:
            # allow hyphen/spacing variants already covered by lower()
            if needle not in blob:
                raise AssertionError(f"earned-representation missing phrase {needle!r}")
    if "/show-me" not in blob:
        raise AssertionError("earned-representation must forbid /show-me")
    forbidders = ("visual mode", "presentation subsystem", "top-level route")
    lower = blob.lower()
    for phrase in forbidders:
        if phrase not in lower:
            raise AssertionError(f"earned-representation must forbid {phrase!r}")


def assert_surfaces_link() -> None:
    surfaces = {
        "how-report": HOW_REPORT,
        "inspect SKILL": INSPECT_SKILL,
        "architect SKILL": ARCHITECT_SKILL,
        "review SKILL": REVIEW_SKILL,
        "investigation playbook": INVESTIGATION,
        "architecture-change playbook": ARCHITECTURE_CHANGE,
        "independent-review playbook": INDEPENDENT_REVIEW,
        "operating-protocol": PROTOCOL,
    }
    for label, path in surfaces.items():
        text = _text(path)
        if "earned-representation" not in text and "earned representation" not in text.lower():
            raise AssertionError(f"{label} must link or mention earned-representation")


def assert_change_debug_not_mandated() -> None:
    for label, path in (("change", CHANGE_SKILL), ("debug", DEBUG_SKILL)):
        text = _text(path).lower()
        for banned in (
            "must diagram",
            "mandatory visualization",
            "must visualize",
            "require diagram",
            "required diagram",
        ):
            if banned in text:
                raise AssertionError(f"patpat-{label} must not mandate diagrams ({banned!r})")


def assert_representation_matrix() -> None:
    factual = dry_run_loop.representation_plan(kind="factual", structure_hard_in_prose=True)
    assert factual["form"] == "prose" and factual["visualize"] is False
    runtime = dry_run_loop.representation_plan(kind="runtime_flow", structure_hard_in_prose=True)
    assert runtime["form"] == "call-tree" and runtime["visualize"] is True
    ownership = dry_run_loop.representation_plan(kind="ownership", structure_hard_in_prose=True)
    assert ownership["form"] == "shallow-tree" and ownership["visualize"] is True
    arch = dry_run_loop.representation_plan(kind="architecture_delta", structure_hard_in_prose=True)
    assert arch["form"] == "structural-comparison" and arch["visualize"] is True
    shape = dry_run_loop.representation_plan(kind="shape_review", structure_hard_in_prose=True)
    assert shape["form"] == "diff-shaped" and shape["visualize"] is True
    complex_simple = dry_run_loop.representation_plan(
        kind="complex_visual", simpler_forms_insufficient=False
    )
    assert complex_simple["form"] != "focused-artifact"
    complex_artifact = dry_run_loop.representation_plan(
        kind="complex_visual", simpler_forms_insufficient=True
    )
    assert complex_artifact["form"] == "focused-artifact"
    trivial = dry_run_loop.representation_plan(kind="trivial_mutation")
    assert trivial["form"] == "prose"
    assert trivial["adds_planning_ceremony"] is False
    assert trivial["adds_reporting_ceremony"] is False
    for sample in (
        factual,
        runtime,
        ownership,
        arch,
        shape,
        complex_simple,
        complex_artifact,
        trivial,
    ):
        assert sample["adds_planning_ceremony"] is False
        assert sample["adds_reporting_ceremony"] is False
    clear_local = dry_run_loop.start_plan(clear_bounded_reversible_local=True, mutating=True)
    assert clear_local["kind"] == "lightweight-start"
    assert dry_run_loop.representation_plan(kind="trivial_mutation")["form"] == "prose"


def prose_fixture() -> str:
    return (
        "Auth reaches the handler through the router: `route()` matches how/placement "
        "phrases and returns `inspect`; `ship_plan(path='read-only')` returns `no-ship`."
    )


def call_tree_fixture() -> str:
    return """call tree (instruction-contract fixture, not live proof):
route(prompt)
└─ inspect match ("how does" / placement)
   └─ ship_plan(path="read-only")
      └─ no-ship
"""


def shallow_tree_fixture() -> str:
    return """shallow tree (instruction-contract fixture, not live proof):
scripts/
└─ dry_run_loop.py          # owner: test/router layer
skills/patpat-inspect/
└─ SKILL.md + how-report    # owner: inspect explanation
skills/patpat-loop/playbooks/
└─ investigation.md         # owner: how-equivalent playbook
"""


def run_self_test() -> None:
    assert_earned_reference()
    assert_surfaces_link()
    assert_change_debug_not_mandated()
    assert_representation_matrix()
    print("Patpat representation eval self-test passed.")
    print()
    print("== fixture: prose (simple factual) ==")
    print(prose_fixture())
    print()
    print("== fixture: call-tree (runtime flow hard in prose) ==")
    print(call_tree_fixture())
    print()
    print("== fixture: shallow-tree (ownership hard in prose) ==")
    print(shallow_tree_fixture())
    print()
    print("== note ==")
    print("Fixtures are instruction-contract examples, not live-agent proof.")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        return 0
    print("Usage: python3 scripts/eval_representation.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
