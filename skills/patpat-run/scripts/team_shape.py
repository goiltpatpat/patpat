#!/usr/bin/env python3
"""Select a bounded Patpat team topology from explicit task evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

from state_lock import bounded_file_binding


LEVELS = ("low", "medium", "high")
WORK_KINDS = ("read-only", "writable")
MAX_RECEIPT_BYTES = 64 * 1024
MAX_IDENTITY_LENGTH = 512
MAX_EVIDENCE_FILE_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_TOTAL_BYTES = 64 * 1024 * 1024
MAX_EVIDENCE_REFERENCES = 24
MAX_EVIDENCE_REFERENCES_PER_CHECK = 8
MAX_EVIDENCE_PATH_LENGTH = 4096
PLAN_DIGEST = re.compile(r"^[0-9a-f]{64}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROGRAM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PARALLEL_GATE_KIND = "patpat.parallel_gate_receipt"
PARALLEL_GATE_SCHEMA_VERSION = 2
PARALLEL_GATE_CHECKS = (
    "representative_single_owner_run",
    "stable_verifier",
    "independent_slices",
    "isolated_workspaces",
    "isolated_resources",
    "whole_system_verification",
)
PARALLEL_GATE_V1_KEYS = {
    "schema_version",
    "kind",
    "program_id",
    "plan_digest",
    "integration_owner",
    "checks",
    "isolation_identities",
}
PARALLEL_GATE_KEYS = PARALLEL_GATE_V1_KEYS | {"supporting_evidence"}
EVIDENCE_BINDING_KEYS = {"path", "sha256", "size"}
HANDOFF_FIELDS = (
    "candidate_id",
    "objective",
    "owned_scope",
    "forbidden_scope",
    "proof_contract",
    "parallel_gate_receipt",
    "evidence_receipts",
    "objections",
    "reusable_parts",
    "verdict",
    "next_frontier",
)


class TeamShapeError(ValueError):
    """Raised when a team-shape input is invalid."""


def canonical_identity(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > MAX_IDENTITY_LENGTH
    ):
        raise TeamShapeError(f"{label} must be a bounded non-empty identity")
    if unicodedata.normalize("NFKC", value) != value:
        raise TeamShapeError(f"{label} must use canonical Unicode form")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise TeamShapeError(f"{label} must not contain control characters")
    return value.casefold()


def canonical_receipt_digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def bind_parallel_gate_evidence(path: Path) -> dict[str, Any]:
    path_text = str(path)
    if (
        not path.is_absolute()
        or len(path_text) > MAX_EVIDENCE_PATH_LENGTH
        or any(unicodedata.category(character).startswith("C") for character in path_text)
    ):
        raise TeamShapeError("parallel gate evidence path must be absolute and bounded")
    binding = bounded_file_binding(
        path,
        max_bytes=MAX_EVIDENCE_FILE_BYTES,
        error_type=TeamShapeError,
        label="parallel gate evidence",
    )
    if binding["size"] < 1:
        raise TeamShapeError("parallel gate evidence must not be empty")
    return binding


def validate_parallel_gate_evidence(
    value: Any,
    *,
    verify_files: bool,
) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict) or set(value) != set(PARALLEL_GATE_CHECKS):
        raise TeamShapeError("parallel gate supporting evidence must cover every check exactly once")

    normalized: dict[str, list[dict[str, Any]]] = {}
    expected_by_path: dict[str, dict[str, Any]] = {}
    verified_by_path: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    reference_count = 0
    for check in PARALLEL_GATE_CHECKS:
        references = value[check]
        if (
            not isinstance(references, list)
            or not references
            or len(references) > MAX_EVIDENCE_REFERENCES_PER_CHECK
        ):
            raise TeamShapeError(
                f"parallel gate evidence for {check} must contain 1 to "
                f"{MAX_EVIDENCE_REFERENCES_PER_CHECK} file bindings"
            )
        normalized_references: list[dict[str, Any]] = []
        check_paths: set[str] = set()
        for reference in references:
            reference_count += 1
            if reference_count > MAX_EVIDENCE_REFERENCES:
                raise TeamShapeError("parallel gate receipt exceeds the evidence reference limit")
            if not isinstance(reference, dict) or set(reference) != EVIDENCE_BINDING_KEYS:
                raise TeamShapeError(f"parallel gate evidence binding for {check} is malformed")
            path_text = reference.get("path")
            digest = reference.get("sha256")
            size = reference.get("size")
            if (
                not isinstance(path_text, str)
                or not path_text
                or path_text != path_text.strip()
                or len(path_text) > MAX_EVIDENCE_PATH_LENGTH
                or any(unicodedata.category(character).startswith("C") for character in path_text)
                or not Path(path_text).is_absolute()
            ):
                raise TeamShapeError(f"parallel gate evidence path for {check} must be absolute and bounded")
            if not isinstance(digest, str) or SHA256.fullmatch(digest) is None:
                raise TeamShapeError(f"parallel gate evidence digest for {check} is invalid")
            if (
                isinstance(size, bool)
                or not isinstance(size, int)
                or size < 1
                or size > MAX_EVIDENCE_FILE_BYTES
            ):
                raise TeamShapeError(f"parallel gate evidence size for {check} is invalid")

            expected = {"path": path_text, "sha256": digest, "size": size}
            if path_text in check_paths:
                raise TeamShapeError(f"parallel gate evidence for {check} repeats a file binding")
            check_paths.add(path_text)
            previous = expected_by_path.get(path_text)
            if previous is not None and previous != expected:
                raise TeamShapeError("parallel gate evidence binds one path to conflicting content")
            if previous is None:
                expected_by_path[path_text] = expected
                total_bytes += size
                if total_bytes > MAX_EVIDENCE_TOTAL_BYTES:
                    raise TeamShapeError("parallel gate evidence exceeds the total byte limit")
            if verify_files:
                actual = verified_by_path.get(path_text)
                if actual is None:
                    actual = bind_parallel_gate_evidence(Path(path_text))
                    verified_by_path[path_text] = actual
                if actual != expected:
                    raise TeamShapeError(
                        f"parallel gate evidence for {check} no longer matches its file binding"
                    )
                expected = actual
            normalized_references.append(expected)
        normalized[check] = normalized_references
    return normalized


def validate_parallel_gate_receipt(
    value: Any,
    *,
    expected_program_id: str | None = None,
    expected_plan_digest: str | None = None,
    expected_integration_owner: str | None = None,
    expected_units: set[str] | None = None,
    require_evidence: bool = False,
) -> dict[str, Any]:
    """Validate a content-bound earned-parallelism receipt."""
    schema_version = value.get("schema_version") if isinstance(value, dict) else None
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version not in {1, PARALLEL_GATE_SCHEMA_VERSION}
    ):
        raise TeamShapeError("parallel gate receipt schema version is invalid")
    expected_keys = PARALLEL_GATE_V1_KEYS if schema_version == 1 else PARALLEL_GATE_KEYS
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise TeamShapeError("parallel gate receipt fields do not match the contract")
    if value.get("kind") != PARALLEL_GATE_KIND:
        raise TeamShapeError("parallel gate receipt schema or kind is invalid")
    if require_evidence and schema_version != PARALLEL_GATE_SCHEMA_VERSION:
        raise TeamShapeError("writable dispatch requires a schema-v2 receipt with supporting evidence")
    program_id = value.get("program_id")
    if (
        not isinstance(program_id, str)
        or len(program_id) > 64
        or PROGRAM_ID.fullmatch(program_id) is None
    ):
        raise TeamShapeError("parallel gate receipt program_id is invalid")
    plan_digest = value.get("plan_digest")
    if not isinstance(plan_digest, str) or PLAN_DIGEST.fullmatch(plan_digest) is None:
        raise TeamShapeError("parallel gate receipt plan_digest is invalid")
    owner_key = canonical_identity(value.get("integration_owner"), "integration owner")
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or set(checks) != set(PARALLEL_GATE_CHECKS)
        or any(checks[name] is not True for name in PARALLEL_GATE_CHECKS)
    ):
        raise TeamShapeError("parallel gate receipt requires every earned-parallelism check to pass")
    supporting_evidence = None
    if schema_version == PARALLEL_GATE_SCHEMA_VERSION:
        supporting_evidence = validate_parallel_gate_evidence(
            value.get("supporting_evidence"), verify_files=True
        )
    identities = value.get("isolation_identities")
    if not isinstance(identities, dict) or not identities:
        raise TeamShapeError("parallel gate receipt requires isolation identities")
    normalized: dict[str, str] = {}
    for unit_id, identity in identities.items():
        if (
            not isinstance(unit_id, str)
            or len(unit_id) > 64
            or PROGRAM_ID.fullmatch(unit_id) is None
        ):
            raise TeamShapeError("parallel gate receipt contains an invalid unit id")
        identity_key = canonical_identity(identity, f"isolation identity for {unit_id}")
        if identity_key == owner_key:
            raise TeamShapeError("worker isolation identity must differ from the integration owner")
        normalized[unit_id] = identity_key
    if len(normalized) != len(set(normalized.values())):
        raise TeamShapeError("parallel gate receipt isolation identities must be unique")
    if expected_program_id is not None and program_id != expected_program_id:
        raise TeamShapeError("parallel gate receipt program_id does not match the program")
    if expected_plan_digest is not None and plan_digest != expected_plan_digest:
        raise TeamShapeError("parallel gate receipt plan_digest does not match the program")
    if expected_integration_owner is not None and owner_key != canonical_identity(
        expected_integration_owner, "expected integration owner"
    ):
        raise TeamShapeError("parallel gate receipt integration owner does not match")
    if expected_units is not None and set(normalized) != expected_units:
        raise TeamShapeError("parallel gate receipt must bind every program unit exactly once")
    return {
        "schema_version": schema_version,
        "program_id": program_id,
        "plan_digest": plan_digest,
        "integration_owner": value["integration_owner"],
        "isolation_count": len(normalized),
        "supporting_evidence": supporting_evidence,
        "sha256": canonical_receipt_digest(value),
    }


def load_parallel_gate_receipt(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        canonical = path.resolve(strict=True)
    except OSError as error:
        raise TeamShapeError(f"could not resolve parallel gate receipt: {error}") from error
    if not path.is_absolute() or path != canonical:
        raise TeamShapeError("parallel gate receipt must be an absolute regular file without symlinks")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise TeamShapeError(
                "parallel gate receipt must be a unique regular file without symlinks"
            )
        chunks: list[bytes] = []
        remaining = MAX_RECEIPT_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > MAX_RECEIPT_BYTES:
            raise TeamShapeError("parallel gate receipt exceeds the byte limit")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise TeamShapeError(f"could not read parallel gate receipt: {error}") from error
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    return value, validate_parallel_gate_receipt(value)


def positive_integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TeamShapeError(f"{label} must be a positive integer")
    return value


def select_team_shape(
    *,
    work_kind: str,
    decomposable: bool,
    stable_verifier: bool,
    worker_capacity: int,
    worker_budget: int,
    writable_gates_passed: bool,
    uncertainty: str,
    consequence: str,
    independent_oracle: bool,
    parallel_gate_receipt: dict[str, Any] | None = None,
    expected_program_id: str | None = None,
    expected_plan_digest: str | None = None,
    expected_integration_owner: str | None = None,
    expected_units: set[str] | None = None,
) -> dict[str, Any]:
    """Return a deterministic topology without granting execution authority."""
    if work_kind not in WORK_KINDS:
        raise TeamShapeError(f"work_kind must be one of {list(WORK_KINDS)}")
    if uncertainty not in LEVELS:
        raise TeamShapeError(f"uncertainty must be one of {list(LEVELS)}")
    if consequence not in LEVELS:
        raise TeamShapeError(f"consequence must be one of {list(LEVELS)}")
    for value, label in (
        (decomposable, "decomposable"),
        (stable_verifier, "stable_verifier"),
        (independent_oracle, "independent_oracle"),
        (writable_gates_passed, "writable_gates_passed"),
    ):
        if not isinstance(value, bool):
            raise TeamShapeError(f"{label} must be a boolean")

    capacity = positive_integer(worker_capacity, "worker_capacity")
    budget = positive_integer(worker_budget, "worker_budget")
    bounded_limit = min(capacity, budget)
    risk_requires_adversarial = uncertainty == "high" or consequence == "high"
    receipt_summary = None
    if parallel_gate_receipt is not None:
        expected_binding = (
            expected_program_id,
            expected_plan_digest,
            expected_integration_owner,
            expected_units,
        )
        if work_kind == "writable" and any(value is None for value in expected_binding):
            raise TeamShapeError(
                "writable parallel gate receipt requires expected program, plan, owner, and units"
            )
        receipt_summary = validate_parallel_gate_receipt(
            parallel_gate_receipt,
            expected_program_id=expected_program_id,
            expected_plan_digest=expected_plan_digest,
            expected_integration_owner=expected_integration_owner,
            expected_units=expected_units,
        )

    reasons = [
        f"work is {work_kind}",
        f"worker limit is bounded by observed capacity {capacity} and explicit budget {budget}",
    ]
    pattern = "iterative"
    worker_limit = 1

    if work_kind == "writable" and (not writable_gates_passed or receipt_summary is None):
        reasons.append("serial fallback: writable earned-parallelism gates lack a valid content-bound receipt")
    elif (
        work_kind == "writable"
        and receipt_summary["schema_version"] != PARALLEL_GATE_SCHEMA_VERSION
    ):
        reasons.append("serial fallback: legacy receipt lacks content-bound supporting evidence")
    elif work_kind == "writable" and receipt_summary["isolation_count"] < bounded_limit:
        reasons.append("serial fallback: receipt does not bind every budgeted worker to a unique isolation identity")
    elif not stable_verifier:
        reasons.append("serial fallback: no stable verifier")
    elif bounded_limit < 2:
        reasons.append("serial fallback: fewer than two isolated, budgeted lanes")
    elif risk_requires_adversarial and not independent_oracle:
        reasons.append("serial fallback: high uncertainty or consequence lacks an independent oracle")
    elif risk_requires_adversarial:
        pattern = "adversarial"
        worker_limit = bounded_limit
        reasons.append("adversarial search is warranted by high uncertainty or consequence")
        reasons.append("an independent oracle can falsify candidate results")
    elif decomposable:
        pattern = "distributed"
        worker_limit = bounded_limit
        reasons.append("independent slices can return to a stable verifier")
    else:
        reasons.append("serial fallback: work is not decomposable and does not require adversarial search")

    return {
        "schema_version": 1,
        "pattern": pattern,
        "worker_limit": worker_limit,
        "serial_fallback": pattern == "iterative",
        "reasons": reasons,
        "handoff_fields": list(HANDOFF_FIELDS),
        "handoff_policy": "typed-card-no-transcript",
        "parallel_gate_receipt_sha256": (
            receipt_summary["sha256"] if receipt_summary is not None else None
        ),
        "authority_granted": False,
    }


def parse_boolean(value: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def self_test() -> None:
    evidence_directory = tempfile.TemporaryDirectory(prefix="patpat-team-shape-evidence-")
    evidence_path = Path(evidence_directory.name).resolve() / "supporting-evidence.txt"
    evidence_path.write_text("bounded evidence for the parallel gate\n", encoding="utf-8")
    evidence_binding = bind_parallel_gate_evidence(evidence_path)
    receipt = {
        "schema_version": PARALLEL_GATE_SCHEMA_VERSION,
        "kind": PARALLEL_GATE_KIND,
        "program_id": "release-train",
        "plan_digest": "a" * 64,
        "integration_owner": "integration-owner",
        "checks": {name: True for name in PARALLEL_GATE_CHECKS},
        "supporting_evidence": {
            name: [evidence_binding] for name in PARALLEL_GATE_CHECKS
        },
        "isolation_identities": {
            "contract": "worktree-contract",
            "consumer": "worktree-consumer",
            "docs": "worktree-docs",
        },
    }
    common = {
        "work_kind": "writable",
        "decomposable": True,
        "stable_verifier": True,
        "worker_capacity": 5,
        "worker_budget": 3,
        "writable_gates_passed": True,
        "uncertainty": "low",
        "consequence": "medium",
        "independent_oracle": False,
        "parallel_gate_receipt": receipt,
        "expected_program_id": "release-train",
        "expected_plan_digest": "a" * 64,
        "expected_integration_owner": "integration-owner",
        "expected_units": {"contract", "consumer", "docs"},
    }

    distributed = select_team_shape(**common)
    assert distributed["pattern"] == "distributed"
    assert distributed["worker_limit"] == 3
    assert distributed["serial_fallback"] is False

    adversarial = select_team_shape(
        **{**common, "uncertainty": "high", "independent_oracle": True, "worker_budget": 2}
    )
    assert adversarial["pattern"] == "adversarial"
    assert adversarial["worker_limit"] == 2

    no_verifier = select_team_shape(**{**common, "stable_verifier": False})
    assert no_verifier["pattern"] == "iterative" and no_verifier["worker_limit"] == 1

    no_oracle = select_team_shape(**{**common, "consequence": "high"})
    assert no_oracle["pattern"] == "iterative"
    assert any("independent oracle" in reason for reason in no_oracle["reasons"])

    no_capacity = select_team_shape(**{**common, "worker_capacity": 1})
    assert no_capacity["pattern"] == "iterative"

    unearned = select_team_shape(**{**common, "writable_gates_passed": False})
    assert unearned["pattern"] == "iterative" and unearned["authority_granted"] is False

    boolean_only = select_team_shape(**{**common, "parallel_gate_receipt": None})
    assert boolean_only["pattern"] == "iterative"

    try:
        select_team_shape(
            **{
                **common,
                "expected_program_id": "different-program",
            }
        )
    except TeamShapeError as error:
        assert "program_id does not match" in str(error)
    else:
        raise AssertionError("receipt for a different program was accepted")

    unbound = dict(common)
    for key in (
        "expected_program_id",
        "expected_plan_digest",
        "expected_integration_owner",
        "expected_units",
    ):
        unbound[key] = None
    try:
        select_team_shape(**unbound)
    except TeamShapeError as error:
        assert "requires expected program" in str(error)
    else:
        raise AssertionError("unbound writable receipt was accepted")

    reused_identity = json.loads(json.dumps(receipt))
    reused_identity["isolation_identities"]["consumer"] = "worktree-contract"
    try:
        validate_parallel_gate_receipt(reused_identity)
    except TeamShapeError:
        pass
    else:
        raise AssertionError("duplicate isolation identity was accepted")

    indivisible = select_team_shape(**{**common, "decomposable": False})
    assert indivisible["pattern"] == "iterative"

    read_only = select_team_shape(
        **{**common, "work_kind": "read-only", "worker_capacity": 2, "writable_gates_passed": False}
    )
    assert read_only["pattern"] == "distributed" and read_only["worker_limit"] == 2

    try:
        select_team_shape(**{**common, "worker_budget": 0})
    except TeamShapeError:
        pass
    else:
        raise AssertionError("zero worker budget was accepted")

    assert tuple(distributed["handoff_fields"]) == HANDOFF_FIELDS

    with tempfile.TemporaryDirectory(prefix="patpat-team-shape-") as raw:
        directory = Path(raw).resolve()
        receipt_path = directory / "parallel-gate.json"
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
        _, loaded = load_parallel_gate_receipt(receipt_path)
        assert loaded["sha256"] == canonical_receipt_digest(receipt)

        linked_path = directory / "linked-receipt.json"
        os.link(receipt_path, linked_path)
        try:
            load_parallel_gate_receipt(receipt_path)
        except TeamShapeError as error:
            assert "unique regular file" in str(error)
        else:
            raise AssertionError("hard-linked parallel gate receipt was accepted")
    evidence_directory.cleanup()
    print("Patpat team-shape self-test passed.")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--self-test", action="store_true")
    command.add_argument("--work-kind", choices=WORK_KINDS)
    command.add_argument("--decomposable", type=parse_boolean)
    command.add_argument("--stable-verifier", type=parse_boolean)
    command.add_argument("--worker-capacity", type=int)
    command.add_argument("--worker-budget", type=int)
    command.add_argument("--writable-gates-passed", type=parse_boolean)
    command.add_argument("--parallel-gate-receipt", type=Path)
    command.add_argument(
        "--bind-evidence",
        type=Path,
        help="Print a safe content binding for one parallel-gate evidence file",
    )
    command.add_argument("--program-id")
    command.add_argument("--plan-digest")
    command.add_argument("--integration-owner")
    command.add_argument("--unit", action="append", default=[])
    command.add_argument("--uncertainty", choices=LEVELS)
    command.add_argument("--consequence", choices=LEVELS)
    command.add_argument("--independent-oracle", type=parse_boolean)
    return command


def main() -> int:
    command = parser()
    args = command.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.bind_evidence is not None:
        try:
            print(json.dumps(bind_parallel_gate_evidence(args.bind_evidence), indent=2, sort_keys=True))
            return 0
        except TeamShapeError as error:
            command.error(str(error))

    required = {
        "work_kind": args.work_kind,
        "decomposable": args.decomposable,
        "stable_verifier": args.stable_verifier,
        "worker_capacity": args.worker_capacity,
        "worker_budget": args.worker_budget,
        "writable_gates_passed": args.writable_gates_passed,
        "uncertainty": args.uncertainty,
        "consequence": args.consequence,
        "independent_oracle": args.independent_oracle,
    }
    missing = [name.replace("_", "-") for name, value in required.items() if value is None]
    if missing:
        command.error(f"missing required arguments: {', '.join(missing)}")
    try:
        receipt = None
        if args.parallel_gate_receipt is not None:
            receipt, _ = load_parallel_gate_receipt(args.parallel_gate_receipt)
        result = select_team_shape(
            **required,
            parallel_gate_receipt=receipt,
            expected_program_id=args.program_id,
            expected_plan_digest=args.plan_digest,
            expected_integration_owner=args.integration_owner,
            expected_units=set(args.unit) if args.unit else None,
        )
    except TeamShapeError as error:
        command.error(str(error))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
