#!/usr/bin/env python3
"""Evaluate a provider-neutral pull-request observation without mutating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
KIND = "patpat.pr_watch.verdict"
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
CHECK_STATES = {"queued", "in_progress", "completed"}
CHECK_CONCLUSIONS = {
    "success",
    "failure",
    "cancelled",
    "timed_out",
    "action_required",
    "neutral",
    "skipped",
}
PASSING_CONCLUSIONS = {"success"}
FAILING_CONCLUSIONS = CHECK_CONCLUSIONS - PASSING_CONCLUSIONS
REVIEW_DECISIONS = {
    "approved",
    "changes_requested",
    "review_required",
    "not_required",
}
MERGEABILITY = {"mergeable", "conflicting", "unknown"}


class ContractError(ValueError):
    """Raised when an observation cannot satisfy the watcher contract."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{field} must be an object")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def _integer(value: Any, field: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractError(f"{field} must be a boolean")
    return value


def _timestamp(value: Any, field: str) -> datetime:
    raw = _string(value, field)
    if not raw.endswith("Z"):
        raise ContractError(f"{field} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{field} must be a valid RFC3339 UTC timestamp") from exc
    if parsed.tzinfo != timezone.utc:
        raise ContractError(f"{field} must use UTC")
    return parsed


def _sha(value: Any, field: str) -> str:
    raw = _string(value, field).lower()
    if not SHA_PATTERN.fullmatch(raw):
        raise ContractError(f"{field} must be a full 40-character commit SHA")
    return raw


def _enum(value: Any, field: str, allowed: set[str]) -> str:
    raw = _string(value, field)
    if raw not in allowed:
        raise ContractError(f"{field} has unsupported value: {raw}")
    return raw


def _reason(code: str, detail: str) -> dict[str, str]:
    return {"code": code, "detail": detail}


def _binding_hint(document: Any) -> dict[str, Any]:
    binding = document.get("binding", {}) if isinstance(document, dict) else {}
    if not isinstance(binding, dict):
        binding = {}
    return {
        "repository": binding.get("repository"),
        "pull_request": binding.get("pull_request"),
        "head_sha": binding.get("head_sha"),
    }


def _verdict(
    *,
    document: Any,
    binding: dict[str, Any],
    observed_at: Any,
    attempt: Any,
    verdict: str,
    reasons: list[dict[str, str]],
    evidence: dict[str, Any],
) -> dict[str, Any]:
    terminal = verdict in {"blocked", "ready", "stale"}
    next_action = {
        "pending": "reobserve",
        "blocked": "stop",
        "ready": "handoff",
        "stale": "rebind",
    }[verdict]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "binding": binding,
        "observation": {"observed_at": observed_at, "attempt": attempt},
        "verdict": verdict,
        "terminal": terminal,
        "next_action": next_action,
        "reasons": reasons,
        "evidence": evidence,
        "input_sha256": _digest(document),
        "mutations_performed": [],
    }


def evaluate(document: Any) -> dict[str, Any]:
    """Return an auditable verdict for one immutable PR observation."""
    try:
        root = _mapping(document, "root")
        if root.get("schema_version") != SCHEMA_VERSION:
            raise ContractError(f"schema_version must equal {SCHEMA_VERSION}")

        binding_input = _mapping(root.get("binding"), "binding")
        binding = {
            "repository": _string(binding_input.get("repository"), "binding.repository"),
            "pull_request": _integer(
                binding_input.get("pull_request"), "binding.pull_request"
            ),
            "head_sha": _sha(binding_input.get("head_sha"), "binding.head_sha"),
        }

        policy = _mapping(root.get("policy"), "policy")
        max_attempts = _integer(policy.get("max_attempts"), "policy.max_attempts")
        deadline_raw = _string(policy.get("deadline"), "policy.deadline")
        deadline = _timestamp(deadline_raw, "policy.deadline")
        required_review = _boolean(
            policy.get("required_review"), "policy.required_review"
        )
        required_checks_input = policy.get("required_checks")
        if not isinstance(required_checks_input, list):
            raise ContractError("policy.required_checks must be an array")
        required_checks = [
            _string(name, f"policy.required_checks[{index}]")
            for index, name in enumerate(required_checks_input)
        ]
        if len(set(required_checks)) != len(required_checks):
            raise ContractError("policy.required_checks must contain unique names")

        observation = _mapping(root.get("observation"), "observation")
        observed_at_raw = _string(
            observation.get("observed_at"), "observation.observed_at"
        )
        observed_at = _timestamp(observed_at_raw, "observation.observed_at")
        attempt = _integer(observation.get("attempt"), "observation.attempt")
        observed_sha = _sha(observation.get("head_sha"), "observation.head_sha")
        draft = _boolean(observation.get("draft"), "observation.draft")
        review = _enum(
            observation.get("review_decision"),
            "observation.review_decision",
            REVIEW_DECISIONS,
        )
        mergeability = _enum(
            observation.get("mergeability"),
            "observation.mergeability",
            MERGEABILITY,
        )

        checks_input = observation.get("checks")
        if not isinstance(checks_input, list):
            raise ContractError("observation.checks must be an array")
        checks: dict[str, dict[str, str | None]] = {}
        for index, raw_check in enumerate(checks_input):
            check = _mapping(raw_check, f"observation.checks[{index}]")
            name = _string(check.get("name"), f"observation.checks[{index}].name")
            if name in checks:
                raise ContractError(f"observation.checks contains duplicate name: {name}")
            state = _enum(
                check.get("state"),
                f"observation.checks[{index}].state",
                CHECK_STATES,
            )
            conclusion = check.get("conclusion")
            if state == "completed":
                conclusion = _enum(
                    conclusion,
                    f"observation.checks[{index}].conclusion",
                    CHECK_CONCLUSIONS,
                )
            elif conclusion is not None:
                raise ContractError(
                    f"observation.checks[{index}].conclusion must be null unless completed"
                )
            checks[name] = {"state": state, "conclusion": conclusion}

        evidence = {
            "required_checks": required_checks,
            "observed_checks": sorted(checks),
            "required_review": required_review,
            "review_decision": review,
            "mergeability": mergeability,
            "draft": draft,
            "deadline": deadline_raw,
            "max_attempts": max_attempts,
        }

        if observed_sha != binding["head_sha"]:
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="stale",
                reasons=[
                    _reason(
                        "head_changed",
                        f"observed head {observed_sha} does not match bound head {binding['head_sha']}",
                    )
                ],
                evidence=evidence,
            )

        if observed_at > deadline:
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="blocked",
                reasons=[_reason("deadline_exceeded", deadline_raw)],
                evidence=evidence,
            )
        if attempt > max_attempts:
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="blocked",
                reasons=[
                    _reason("attempt_limit_exceeded", str(max_attempts))
                ],
                evidence=evidence,
            )

        blocked: list[dict[str, str]] = []
        pending: list[dict[str, str]] = []
        missing = sorted(set(required_checks) - set(checks))
        if missing:
            pending.append(_reason("missing_required_checks", ", ".join(missing)))
        if draft:
            blocked.append(_reason("draft_pull_request", "pull request is draft"))
        if mergeability == "conflicting":
            blocked.append(_reason("merge_conflict", "provider reports conflicts"))
        elif mergeability == "unknown":
            pending.append(_reason("mergeability_pending", "mergeability is unknown"))
        if review == "changes_requested":
            blocked.append(_reason("changes_requested", "review requests changes"))
        elif required_review and review != "approved":
            pending.append(_reason("review_pending", "approval is required"))

        for name in required_checks:
            if name not in checks:
                continue
            check = checks[name]
            if check["state"] != "completed":
                pending.append(_reason("check_pending", name))
            elif check["conclusion"] in FAILING_CONCLUSIONS:
                blocked.append(
                    _reason("check_failed", f"{name}: {check['conclusion']}")
                )

        if blocked:
            verdict = "blocked"
            reasons = blocked
        elif pending and attempt >= max_attempts:
            verdict = "blocked"
            reasons = pending + [
                _reason("attempt_limit_reached", str(max_attempts))
            ]
        elif pending:
            verdict = "pending"
            reasons = pending
        else:
            verdict = "ready"
            reasons = [_reason("all_gates_passed", "observation satisfies policy")]

        return _verdict(
            document=document,
            binding=binding,
            observed_at=observed_at_raw,
            attempt=attempt,
            verdict=verdict,
            reasons=reasons,
            evidence=evidence,
        )
    except ContractError as exc:
        return _verdict(
            document=document,
            binding=_binding_hint(document),
            observed_at=None,
            attempt=None,
            verdict="blocked",
            reasons=[_reason("invalid_observation", str(exc))],
            evidence={"contract_valid": False},
        )


def _fixture(**overrides: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "binding": {
            "repository": "example/project",
            "pull_request": 17,
            "head_sha": "a" * 40,
        },
        "policy": {
            "required_checks": ["contracts", "tests"],
            "required_review": True,
            "max_attempts": 3,
            "deadline": "2026-08-29T00:00:00Z",
        },
        "observation": {
            "observed_at": "2026-08-28T12:00:00Z",
            "attempt": 1,
            "head_sha": "a" * 40,
            "draft": False,
            "review_decision": "approved",
            "mergeability": "mergeable",
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "success"},
                {"name": "tests", "state": "completed", "conclusion": "success"},
            ],
        },
    }
    for section, values in overrides.items():
        document[section].update(values)
    return document


def self_test() -> None:
    ready = _fixture()
    first = evaluate(ready)
    assert first["verdict"] == "ready"
    assert first["binding"]["head_sha"] == "a" * 40
    assert first["mutations_performed"] == []
    assert first == evaluate(ready)

    pending = _fixture(
        observation={
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "success"},
                {"name": "tests", "state": "in_progress", "conclusion": None},
            ]
        }
    )
    assert evaluate(pending)["verdict"] == "pending"

    stale = _fixture(observation={"head_sha": "b" * 40})
    assert evaluate(stale)["verdict"] == "stale"

    failed = _fixture(
        observation={
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "failure"},
                {"name": "tests", "state": "completed", "conclusion": "success"},
            ]
        }
    )
    assert evaluate(failed)["verdict"] == "blocked"

    for inconclusive in ("neutral", "skipped"):
        not_proven = _fixture(
            observation={
                "checks": [
                    {
                        "name": "contracts",
                        "state": "completed",
                        "conclusion": inconclusive,
                    },
                    {"name": "tests", "state": "completed", "conclusion": "success"},
                ]
            }
        )
        assert evaluate(not_proven)["verdict"] == "blocked"

    changes_requested = _fixture(
        policy={"required_review": False},
        observation={"review_decision": "changes_requested"},
    )
    assert evaluate(changes_requested)["verdict"] == "blocked"

    missing = _fixture(
        observation={
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "success"}
            ]
        }
    )
    missing_result = evaluate(missing)
    assert missing_result["verdict"] == "pending"
    assert missing_result["reasons"][0]["code"] == "missing_required_checks"
    missing["observation"]["attempt"] = 3
    assert evaluate(missing)["verdict"] == "blocked"

    exhausted = _fixture(
        observation={
            "attempt": 3,
            "checks": [
                {"name": "contracts", "state": "completed", "conclusion": "success"},
                {"name": "tests", "state": "queued", "conclusion": None},
            ],
        }
    )
    assert evaluate(exhausted)["verdict"] == "blocked"

    expired = _fixture(observation={"observed_at": "2026-08-29T00:00:01Z"})
    assert evaluate(expired)["reasons"][0]["code"] == "deadline_exceeded"

    invalid = _fixture()
    del invalid["observation"]["mergeability"]
    invalid_result = evaluate(invalid)
    assert invalid_result["verdict"] == "blocked"
    assert invalid_result["reasons"][0]["code"] == "invalid_observation"

    print("pr_watch self-test: PASS")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="Observation JSON path, or - for stdin")
    parser.add_argument(
        "--print-example", action="store_true", help="Print a valid observation contract"
    )
    parser.add_argument("--self-test", action="store_true", help="Run contract checks")
    return parser.parse_args(argv)


def _read_document(source: str) -> Any:
    if source == "-":
        return json.load(sys.stdin)
    return json.loads(Path(source).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        self_test()
        return 0
    if args.print_example:
        print(json.dumps(_fixture(), indent=2))
        return 0
    if not args.input:
        print(
            "error: --input is required unless --self-test or --print-example is used",
            file=sys.stderr,
        )
        return 2
    try:
        document = _read_document(args.input)
    except (OSError, json.JSONDecodeError) as exc:
        result = _verdict(
            document={"unreadable_input": True},
            binding={"repository": None, "pull_request": None, "head_sha": None},
            observed_at=None,
            attempt=None,
            verdict="blocked",
            reasons=[_reason("invalid_json", str(exc))],
            evidence={"contract_valid": False},
        )
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 2
    result = evaluate(document)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["verdict"] in {"pending", "ready", "stale"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
