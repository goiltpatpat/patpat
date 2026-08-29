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


SCHEMA_VERSION = 2
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
PULL_REQUEST_STATES = {"open", "closed", "merged"}
MAX_CHECKS = 100
MAX_NAME_LENGTH = 128
MAX_REPOSITORY_LENGTH = 256


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


def _string(value: Any, field: str, max_length: int | None = None) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    result = value.strip()
    if max_length is not None and len(result) > max_length:
        raise ContractError(f"{field} must be at most {max_length} characters")
    return result


def _integer(value: Any, field: str, minimum: int = 1, maximum: int = 1_000_000) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ContractError(f"{field} must be an integer >= {minimum}")
    if value > maximum:
        raise ContractError(f"{field} must be an integer <= {maximum}")
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

    def safe_string(value: Any, maximum: int) -> str | None:
        if not isinstance(value, str):
            return None
        result = value.strip()
        return result if result and len(result) <= maximum else None

    pull_request = binding.get("pull_request")
    if isinstance(pull_request, bool) or not isinstance(pull_request, int) or not 1 <= pull_request <= 1_000_000:
        pull_request = None
    head_sha = safe_string(binding.get("head_sha"), 40)
    if head_sha is None or SHA_PATTERN.fullmatch(head_sha.lower()) is None:
        head_sha = None
    return {
        "repository": safe_string(binding.get("repository"), MAX_REPOSITORY_LENGTH),
        "pull_request": pull_request,
        "head_sha": head_sha,
        "base_ref": safe_string(binding.get("base_ref"), MAX_NAME_LENGTH),
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
            "repository": _string(
                binding_input.get("repository"), "binding.repository", MAX_REPOSITORY_LENGTH
            ),
            "pull_request": _integer(
                binding_input.get("pull_request"), "binding.pull_request"
            ),
            "head_sha": _sha(binding_input.get("head_sha"), "binding.head_sha"),
            "base_ref": _string(binding_input.get("base_ref"), "binding.base_ref", MAX_NAME_LENGTH),
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
        if len(required_checks_input) > MAX_CHECKS:
            raise ContractError(f"policy.required_checks must contain at most {MAX_CHECKS} names")
        required_checks = [
            _string(name, f"policy.required_checks[{index}]", MAX_NAME_LENGTH)
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
        provider_repository = _string(
            observation.get("provider_repository"),
            "observation.provider_repository",
            MAX_REPOSITORY_LENGTH,
        )
        provider_pull_request = _integer(
            observation.get("provider_pull_request"), "observation.provider_pull_request"
        )
        provider_head_sha = _sha(
            observation.get("provider_head_sha"), "observation.provider_head_sha"
        )
        pull_request_state = _enum(
            observation.get("state"),
            "observation.state",
            PULL_REQUEST_STATES,
        )
        unresolved_threads = _integer(
            observation.get("unresolved_threads"),
            "observation.unresolved_threads",
            minimum=0,
        )
        base_ref = _string(observation.get("base_ref"), "observation.base_ref", MAX_NAME_LENGTH)
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
        if len(checks_input) > MAX_CHECKS:
            raise ContractError(f"observation.checks must contain at most {MAX_CHECKS} entries")
        checks: dict[str, dict[str, str | None]] = {}
        for index, raw_check in enumerate(checks_input):
            check = _mapping(raw_check, f"observation.checks[{index}]")
            name = _string(
                check.get("name"), f"observation.checks[{index}].name", MAX_NAME_LENGTH
            )
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
            "state": pull_request_state,
            "unresolved_threads": unresolved_threads,
            "base_ref": base_ref,
            "provider_head_sha": provider_head_sha,
            "provider_repository": provider_repository,
            "provider_pull_request": provider_pull_request,
        }

        if (
            provider_repository != binding["repository"]
            or provider_pull_request != binding["pull_request"]
        ):
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="stale",
                reasons=[
                    _reason(
                        "provider_binding_changed",
                        "provider repository or pull request does not match the bound target",
                    )
                ],
                evidence=evidence,
            )

        if observed_sha != binding["head_sha"] or provider_head_sha != observed_sha:
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="stale",
                reasons=[
                    _reason(
                        "head_changed",
                        "provider, observed, and bound heads do not match: "
                        f"provider={provider_head_sha}, observed={observed_sha}, "
                        f"bound={binding['head_sha']}",
                    )
                ],
                evidence=evidence,
            )
        if base_ref != binding["base_ref"]:
            return _verdict(
                document=document,
                binding=binding,
                observed_at=observed_at_raw,
                attempt=attempt,
                verdict="stale",
                reasons=[
                    _reason(
                        "base_changed",
                        f"observed base {base_ref} does not match bound base {binding['base_ref']}",
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
            preview = ", ".join(missing[:8])
            pending.append(
                _reason(
                    "missing_required_checks",
                    f"{len(missing)} missing; preview: {preview}",
                )
            )
        if pull_request_state != "open":
            blocked.append(
                _reason(
                    "pull_request_not_open",
                    f"pull request state is {pull_request_state}",
                )
            )
        if unresolved_threads:
            blocked.append(
                _reason(
                    "unresolved_review_threads",
                    str(unresolved_threads),
                )
            )
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
        "schema_version": SCHEMA_VERSION,
        "binding": {
            "repository": "example/project",
            "pull_request": 17,
            "head_sha": "a" * 40,
            "base_ref": "main",
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
            "provider_repository": "example/project",
            "provider_pull_request": 17,
            "provider_head_sha": "a" * 40,
            "state": "open",
            "unresolved_threads": 0,
            "base_ref": "main",
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

    provider_stale = _fixture(observation={"provider_head_sha": "b" * 40})
    assert evaluate(provider_stale)["verdict"] == "stale"

    wrong_base = _fixture(observation={"base_ref": "release"})
    wrong_base_result = evaluate(wrong_base)
    assert wrong_base_result["verdict"] == "stale"
    assert wrong_base_result["reasons"][0]["code"] == "base_changed"

    wrong_repository = _fixture(observation={"provider_repository": "other/project"})
    assert evaluate(wrong_repository)["reasons"][0]["code"] == "provider_binding_changed"
    wrong_pull_request = _fixture(observation={"provider_pull_request": 999})
    assert evaluate(wrong_pull_request)["reasons"][0]["code"] == "provider_binding_changed"

    for state in ("closed", "merged"):
        not_open = _fixture(observation={"state": state})
        not_open_result = evaluate(not_open)
        assert not_open_result["verdict"] == "blocked"
        assert not_open_result["reasons"][0]["code"] == "pull_request_not_open"

    unresolved = _fixture(observation={"unresolved_threads": 2})
    unresolved_result = evaluate(unresolved)
    assert unresolved_result["verdict"] == "blocked"
    assert unresolved_result["reasons"][0]["code"] == "unresolved_review_threads"

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

    missing_provider_head = _fixture()
    del missing_provider_head["observation"]["provider_head_sha"]
    missing_provider_result = evaluate(missing_provider_head)
    assert missing_provider_result["verdict"] == "blocked"
    assert missing_provider_result["reasons"][0]["code"] == "invalid_observation"

    invalid_base = _fixture(observation={"base_ref": ""})
    invalid_base_result = evaluate(invalid_base)
    assert invalid_base_result["verdict"] == "blocked"
    assert invalid_base_result["reasons"][0]["code"] == "invalid_observation"

    excessive_checks = _fixture(policy={"required_checks": [f"check-{index}" for index in range(101)]})
    excessive_result = evaluate(excessive_checks)
    assert excessive_result["verdict"] == "blocked"
    assert len(json.dumps(excessive_result)) < 4096

    invalid_hint = {"schema_version": SCHEMA_VERSION, "binding": {"repository": "x" * 250_000}}
    hint_result = evaluate(invalid_hint)
    assert hint_result["verdict"] == "blocked"
    assert len(json.dumps(hint_result)) < 4096

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
    except (OSError, ValueError) as exc:
        result = _verdict(
            document={"unreadable_input": True},
            binding={
                "repository": None,
                "pull_request": None,
                "head_sha": None,
                "base_ref": None,
            },
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
