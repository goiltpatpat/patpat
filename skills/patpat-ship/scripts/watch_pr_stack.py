#!/usr/bin/env python3
"""Watch a frozen, bottom-to-top GitHub pull-request stack without mutating it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import github_observe
import pr_watch


SCHEMA_VERSION = 2
KIND = "patpat.pr_stack_watch.verdict"
MAX_STACK_SIZE = 20
MAX_MANIFEST_BYTES = 64 * 1024
MAX_OBSERVATIONS = 100
MAX_ATTEMPTS_PER_PR = 100
MAX_WATCH_DURATION_SECONDS = 24 * 60 * 60
MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 3600
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class WatchError(ValueError):
    """Raised when a frozen PR stack or watch budget is invalid."""


def _string(value: Any, field: str, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WatchError(f"{field} must be a non-empty string")
    result = value.strip()
    if len(result) > maximum:
        raise WatchError(f"{field} must be at most {maximum} characters")
    return result


def _positive_integer(value: Any, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise WatchError(f"{field} must be an integer from 1 to {maximum}")
    return value


def _manifest_sha256(document: Any) -> str:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stack_input_sha256(
    pr_input_sha256: str, base_ref_oid: str, base_oid_source: str
) -> str:
    payload = json.dumps(
        {
            "kind": KIND,
            "schema_version": SCHEMA_VERSION,
            "pr_input_sha256": pr_input_sha256,
            "base_ref_oid": base_ref_oid,
            "base_oid_source": base_oid_source,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _read_manifest(source: str) -> Any:
    path = Path(source)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size > MAX_MANIFEST_BYTES
        ):
            raise WatchError("manifest must be a unique bounded regular file")
        payload = bytearray()
        while len(payload) <= MAX_MANIFEST_BYTES:
            chunk = os.read(descriptor, min(8192, MAX_MANIFEST_BYTES + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
        if len(payload) > MAX_MANIFEST_BYTES:
            raise WatchError(f"manifest must not exceed {MAX_MANIFEST_BYTES} bytes")
    finally:
        os.close(descriptor)
    try:
        document = json.loads(payload)
        pr_watch._validate_json_shape(document)
        return document
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError, pr_watch.ContractError) as error:
        raise WatchError("manifest must be bounded valid JSON") from error


def validate_manifest(document: Any) -> tuple[str, list[dict[str, Any]]]:
    if not isinstance(document, dict) or set(document) != {
        "schema_version",
        "repository",
        "pull_requests",
    }:
        raise WatchError("manifest must contain only schema_version, repository, and pull_requests")
    if type(document["schema_version"]) is not int or document["schema_version"] != SCHEMA_VERSION:
        raise WatchError(f"schema_version must equal {SCHEMA_VERSION}")
    repository = _string(document["repository"], "repository")
    if github_observe.REPOSITORY.fullmatch(repository) is None:
        raise WatchError("repository must be OWNER/REPO")
    entries = document["pull_requests"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_STACK_SIZE:
        raise WatchError(f"pull_requests must contain 1 to {MAX_STACK_SIZE} entries")

    targets: list[dict[str, Any]] = []
    seen: set[int] = set()
    expected_keys = {
        "pull_request",
        "expected_head",
        "expected_base",
        "expected_base_sha",
        "required_checks",
        "require_review",
    }
    for index, entry in enumerate(entries):
        label = f"pull_requests[{index}]"
        if not isinstance(entry, dict) or set(entry) != expected_keys:
            raise WatchError(f"{label} must contain exactly {', '.join(sorted(expected_keys))}")
        number = _positive_integer(entry["pull_request"], f"{label}.pull_request", 1_000_000)
        if number in seen:
            raise WatchError(f"pull_requests contains duplicate PR {number}")
        seen.add(number)
        head = _string(entry["expected_head"], f"{label}.expected_head", 40).lower()
        if SHA_PATTERN.fullmatch(head) is None:
            raise WatchError(f"{label}.expected_head must be a full 40-character SHA")
        base = _string(entry["expected_base"], f"{label}.expected_base", 128)
        base_sha = _string(entry["expected_base_sha"], f"{label}.expected_base_sha", 40).lower()
        if SHA_PATTERN.fullmatch(base_sha) is None:
            raise WatchError(f"{label}.expected_base_sha must be a full 40-character SHA")
        if targets and base_sha != targets[-1]["expected_head"]:
            raise WatchError(
                f"{label}.expected_base_sha must equal the previous PR's expected_head"
            )
        checks = entry["required_checks"]
        if not isinstance(checks, list) or not checks or len(checks) > pr_watch.MAX_CHECKS:
            raise WatchError(f"{label}.required_checks must contain 1 to {pr_watch.MAX_CHECKS} names")
        normalized_checks = [
            _string(name, f"{label}.required_checks[{check_index}]", 128)
            for check_index, name in enumerate(checks)
        ]
        if len(set(normalized_checks)) != len(normalized_checks):
            raise WatchError(f"{label}.required_checks must be unique")
        require_review = entry["require_review"]
        if not isinstance(require_review, bool):
            raise WatchError(f"{label}.require_review must be a boolean")
        targets.append(
            {
                "pull_request": number,
                "expected_head": head,
                "expected_base": base,
                "expected_base_sha": base_sha,
                "_last_observed_base_sha": None,
                "_last_observed_base_source": None,
                "_last_stack_input_sha256": None,
                "required_checks": normalized_checks,
                "require_review": require_review,
            }
        )
    return repository, targets


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_deadline(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise WatchError("deadline must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise WatchError("deadline must be a valid RFC3339 UTC timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise WatchError("deadline must use UTC")
    return parsed


def _reasons(verdict: dict[str, Any]) -> set[str]:
    reasons = verdict.get("reasons")
    if not isinstance(reasons, list):
        return set()
    return {
        item.get("code")
        for item in reasons
        if isinstance(item, dict) and isinstance(item.get("code"), str)
    }


def _confirmed_merged(verdict: dict[str, Any]) -> bool:
    evidence = verdict.get("evidence")
    return (
        verdict.get("verdict") == "blocked"
        and isinstance(evidence, dict)
        and evidence.get("state") == "merged"
        and "pull_request_not_open" in _reasons(verdict)
    )


def _state_rows(
    targets: list[dict[str, Any]],
    attempts: list[int],
    statuses: list[str],
    input_hashes: list[str | None],
) -> list[dict[str, Any]]:
    return [
        {
            "pull_request": target["pull_request"],
            "expected_head": target["expected_head"],
            "expected_base": target["expected_base"],
            "expected_base_sha": target["expected_base_sha"],
            "attempts": attempts[index],
            "status": statuses[index],
            "last_input_sha256": input_hashes[index],
            "last_observed_base_sha": target["_last_observed_base_sha"],
            "last_observed_base_source": target["_last_observed_base_source"],
            "last_stack_input_sha256": target["_last_stack_input_sha256"],
        }
        for index, target in enumerate(targets)
    ]


def _emit_event(
    emit: Callable[[dict[str, Any]], None],
    *,
    repository: str,
    manifest_sha256: str,
    sequence: int,
    observed_at: datetime,
    status: str,
    target: dict[str, Any] | None,
    targets: list[dict[str, Any]],
    attempts: list[int],
    statuses: list[str],
    input_hashes: list[str | None],
    pr_verdict: dict[str, Any] | None = None,
    reason: str | None = None,
    reason_code: str | None = None,
) -> None:
    terminal = status in {"complete", "blocked", "stale", "incomplete"}
    next_action = {
        "pending": "wait",
        "frontier_ready": "wait_for_provider_merge",
        "merged": "observe_next_frontier",
        "complete": "report",
        "blocked": "stop",
        "stale": "rebind_after_confirmation",
        "incomplete": "stop",
    }[status]
    event = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "repository": repository,
        "manifest_sha256": manifest_sha256,
        "sequence": sequence,
        "observed_at": _rfc3339(observed_at),
        "status": status,
        "terminal": terminal,
        "next_action": next_action,
        "frontier": (
            {
                "pull_request": target["pull_request"],
                "head_sha": target["expected_head"],
                "base_ref": target["expected_base"],
                "expected_base_sha": target["expected_base_sha"],
                "observed_base_sha": target["_last_observed_base_sha"],
                "observed_base_source": target["_last_observed_base_source"],
                "stack_input_sha256": target["_last_stack_input_sha256"],
            }
            if target is not None
            else None
        ),
        "pull_requests": _state_rows(targets, attempts, statuses, input_hashes),
        "pr_verdict": pr_verdict,
        "reasons": ([{"code": reason_code or status, "detail": reason}] if reason else []),
        "mutations_performed": [],
    }
    emit(event)


def run_watch(
    args: argparse.Namespace,
    document: Any,
    *,
    fetch: Callable[[str, int], Any] = github_observe.fetch_github,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[dict[str, Any]], None],
) -> int:
    repository, targets = validate_manifest(document)
    max_attempts = _positive_integer(
        args.max_attempts_per_pr, "max attempts per PR", MAX_ATTEMPTS_PER_PR
    )
    max_observations = _positive_integer(
        args.max_observations, "max observations", MAX_OBSERVATIONS
    )
    if max_observations < len(targets):
        raise WatchError("max observations must allow at least one observation per PR")
    interval = _positive_integer(args.interval_seconds, "interval seconds", MAX_INTERVAL_SECONDS)
    if interval < MIN_INTERVAL_SECONDS:
        raise WatchError(f"interval seconds must be at least {MIN_INTERVAL_SECONDS}")
    max_age = _positive_integer(
        args.max_observation_age_seconds,
        "max observation age seconds",
        pr_watch.MAX_OBSERVATION_AGE_SECONDS,
    )
    deadline = _parse_deadline(args.deadline)
    started = now()
    if started.tzinfo != timezone.utc:
        raise WatchError("watch clock must return UTC timestamps")
    if started >= deadline:
        raise WatchError("deadline must be in the future")
    if (deadline - started).total_seconds() > MAX_WATCH_DURATION_SECONDS:
        raise WatchError("deadline must be within 24 hours")

    for target in targets:
        observer_args = argparse.Namespace(
            repository=repository,
            pull_request=target["pull_request"],
            expected_head=target["expected_head"],
            expected_base=target["expected_base"],
            required_check=target["required_checks"],
            allow_no_required_checks=False,
            require_review=target["require_review"],
            max_attempts=max_attempts,
            attempt=1,
            max_observation_age_seconds=max_age,
            deadline=args.deadline,
        )
        github_observe.validate_arguments(observer_args)
        target["expected_head"] = observer_args.expected_head

    manifest_sha256 = _manifest_sha256(document)
    attempts = [0] * len(targets)
    statuses = ["queued"] * len(targets)
    input_hashes: list[str | None] = [None] * len(targets)
    index = 0
    sequence = 0

    while index < len(targets):
        current = now()
        if current >= deadline:
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=current,
                status="incomplete",
                target=targets[index],
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                reason="deadline reached before the stack completed",
                reason_code="deadline_exceeded",
            )
            return 2
        if sequence >= max_observations:
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=current,
                status="incomplete",
                target=targets[index],
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                reason="total observation budget exhausted",
                reason_code="observation_budget_exhausted",
            )
            return 2

        target = targets[index]
        attempts[index] += 1
        sequence += 1
        statuses[index] = "observing"
        try:
            response = fetch(repository, target["pull_request"])
            document_observation = github_observe.observation_document(
                response,
                repository=repository,
                pull_request=target["pull_request"],
                expected_head=target["expected_head"],
                expected_base=target["expected_base"],
                required_checks=target["required_checks"],
                allow_no_required_checks=False,
                required_review=target["require_review"],
                max_attempts=max_attempts,
                attempt=attempts[index],
                max_observation_age_seconds=max_age,
                deadline=args.deadline,
                observed_at=_rfc3339(now()),
            )
            observed_base_sha, base_oid_source = github_observe.provider_base_commit_oid(response)
            target["_last_observed_base_sha"] = observed_base_sha
            target["_last_observed_base_source"] = base_oid_source
            input_hashes[index] = _manifest_sha256(document_observation)
            target["_last_stack_input_sha256"] = _stack_input_sha256(
                input_hashes[index], observed_base_sha, base_oid_source
            )
            if observed_base_sha != target["expected_base_sha"]:
                statuses[index] = "stale"
                _emit_event(
                    emit,
                    repository=repository,
                    manifest_sha256=manifest_sha256,
                    sequence=sequence,
                    observed_at=now(),
                    status="stale",
                    target=target,
                    targets=targets,
                    attempts=attempts,
                    statuses=statuses,
                    input_hashes=input_hashes,
                    reason=(
                        "provider base commit does not match the frozen binding: expected "
                        f"{target['expected_base_sha']}, observed {observed_base_sha}"
                    ),
                    reason_code="base_commit_changed",
                )
                return 2
            pr_verdict = pr_watch.evaluate(document_observation, evaluated_at=now())
            if pr_verdict.get("input_sha256") != input_hashes[index]:
                raise WatchError("PR evaluator input digest does not match the stack observation")
        except github_observe.ObserverError:
            statuses[index] = "incomplete"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="incomplete",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                reason="provider observation failed; inspect stderr for diagnostics",
                reason_code="provider_observation_failed",
            )
            raise
        underlying = pr_verdict.get("verdict")
        verdict_reasons = _reasons(pr_verdict)

        if "deadline_exceeded" in verdict_reasons:
            statuses[index] = "incomplete"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="incomplete",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                pr_verdict=pr_verdict,
                reason="deadline reached during provider observation",
                reason_code="deadline_exceeded",
            )
            return 2
        if "attempt_limit_reached" in verdict_reasons:
            statuses[index] = "incomplete"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="incomplete",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                pr_verdict=pr_verdict,
                reason="per-PR observation budget exhausted before provider merge",
                reason_code="attempt_budget_exhausted",
            )
            return 2

        if _confirmed_merged(pr_verdict):
            statuses[index] = "merged"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="merged",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                pr_verdict=pr_verdict,
            )
            index += 1
            if index == len(targets):
                _emit_event(
                    emit,
                    repository=repository,
                    manifest_sha256=manifest_sha256,
                    sequence=sequence,
                    observed_at=now(),
                    status="complete",
                    target=None,
                    targets=targets,
                    attempts=attempts,
                    statuses=statuses,
                    input_hashes=input_hashes,
                )
                return 0
            continue

        if underlying == "ready":
            status = "frontier_ready"
        elif underlying == "pending":
            status = "pending"
        elif underlying == "stale":
            status = "stale"
        else:
            status = "blocked"
        statuses[index] = status
        _emit_event(
            emit,
            repository=repository,
            manifest_sha256=manifest_sha256,
            sequence=sequence,
            observed_at=now(),
            status=status,
            target=target,
            targets=targets,
            attempts=attempts,
            statuses=statuses,
            input_hashes=input_hashes,
            pr_verdict=pr_verdict,
        )
        if status in {"stale", "blocked"}:
            return 2
        if attempts[index] >= max_attempts:
            statuses[index] = "incomplete"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="incomplete",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                reason="per-PR observation budget exhausted before provider merge",
                reason_code="attempt_budget_exhausted",
            )
            return 2

        if sequence >= max_observations:
            statuses[index] = "incomplete"
            _emit_event(
                emit,
                repository=repository,
                manifest_sha256=manifest_sha256,
                sequence=sequence,
                observed_at=now(),
                status="incomplete",
                target=target,
                targets=targets,
                attempts=attempts,
                statuses=statuses,
                input_hashes=input_hashes,
                reason="total observation budget exhausted before the stack completed",
                reason_code="observation_budget_exhausted",
            )
            return 2

        remaining = (deadline - now()).total_seconds()
        if remaining > 0:
            sleep(min(interval, remaining))

    return 0


def _fixture_response(target: dict[str, Any], *, state: str = "OPEN", head: str | None = None,
                      base: str | None = None, base_sha: str | None = None,
                      merged_base_sha: str | None = None) -> dict[str, Any]:
    response = github_observe.fixture()
    repository = response["data"]["repository"]
    repository["nameWithOwner"] = "example/project"
    pull_request = repository["pullRequest"]
    pull_request["number"] = target["pull_request"]
    pull_request["headRefOid"] = head or target["expected_head"]
    pull_request["baseRefName"] = base or target["expected_base"]
    pull_request["baseRefOid"] = merged_base_sha or target["expected_base_sha"]
    pull_request["baseRef"] = {
        "name": base or target["expected_base"],
        "target": {
            "__typename": "Commit",
            "oid": base_sha or target["expected_base_sha"],
        },
        "branchProtectionRule": None,
        "rules": {
            "nodes": [],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }
    pull_request["state"] = state
    pull_request["merged"] = state == "MERGED"
    pull_request["reviewThreads"]["nodes"] = [{"isResolved": True}]
    pull_request["commits"]["nodes"][0]["commit"]["oid"] = pull_request["headRefOid"]
    contexts = pull_request["commits"]["nodes"][0]["commit"]["statusCheckRollup"][
        "contexts"
    ]["nodes"]
    for check in contexts:
        check["status"] = "COMPLETED"
        check["conclusion"] = "SUCCESS"
        if "state" in check:
            check["state"] = "SUCCESS"
    return response


def _fixture_target(number: int, head: str, base: str) -> dict[str, Any]:
    return {
        "pull_request": number,
        "expected_head": head,
        "expected_base": base,
        "expected_base_sha": "0" * 40 if number == 17 else "a" * 40,
        "required_checks": ["tests", "policy"],
        "require_review": True,
    }


def _fixture_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "repository": "example/project",
        "pull_requests": [
            _fixture_target(17, "a" * 40, "main"),
            _fixture_target(18, "b" * 40, "feature/17"),
        ],
    }


def self_test() -> None:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    current = [start]
    document = _fixture_manifest()
    target_one, target_two = document["pull_requests"]
    responses = {
        17: [_fixture_response(target_one), _fixture_response(target_one, state="MERGED")],
        18: [_fixture_response(target_two), _fixture_response(target_two, state="MERGED")],
    }
    calls: list[int] = []
    emitted: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def fetch(_: str, number: int) -> Any:
        calls.append(number)
        return responses[number].pop(0)

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    args = argparse.Namespace(
        max_attempts_per_pr=3,
        max_observations=10,
        interval_seconds=10,
        max_observation_age_seconds=900,
        deadline=_rfc3339(start + timedelta(minutes=1)),
    )
    invalid_chain = _fixture_manifest()
    invalid_chain["pull_requests"][1]["expected_base_sha"] = "c" * 40
    expect_error(
        lambda: validate_manifest(invalid_chain),
        "must equal the previous PR's expected_head",
    )
    invalid_base_sha = _fixture_manifest()
    invalid_base_sha["pull_requests"][0]["expected_base_sha"] = "not-a-sha"
    expect_error(
        lambda: validate_manifest(invalid_base_sha),
        "expected_base_sha must be a full 40-character SHA",
    )
    legacy_manifest = _fixture_manifest()
    legacy_manifest["schema_version"] = 1
    expect_error(
        lambda: validate_manifest(legacy_manifest),
        "schema_version must equal 2",
    )

    status = run_watch(
        args,
        document,
        fetch=fetch,
        now=lambda: current[0],
        sleep=sleep,
        emit=emitted.append,
    )
    assert status == 0
    assert calls == [17, 17, 18, 18]
    assert [event["status"] for event in emitted] == [
        "frontier_ready",
        "merged",
        "frontier_ready",
        "merged",
        "complete",
    ]
    assert all(event["mutations_performed"] == [] for event in emitted)
    assert sleeps == [10, 10]
    assert emitted[-1]["pull_requests"][-1]["status"] == "merged"
    assert emitted[-1]["pull_requests"][0]["last_observed_base_sha"] == "0" * 40
    assert emitted[-1]["pull_requests"][1]["last_observed_base_sha"] == "a" * 40
    assert emitted[0]["frontier"]["observed_base_source"] == "live_base_ref_target"
    assert emitted[1]["frontier"]["observed_base_source"] == "pr_associated_base_ref_oid"
    assert all(
        len(row["last_stack_input_sha256"]) == 64
        for row in emitted[-1]["pull_requests"]
    )

    rebase_after_merge = _fixture_manifest()
    rebase_events: list[dict[str, Any]] = []
    rebase_calls: list[int] = []

    def fetch_after_stack_merge(_: str, number: int) -> Any:
        rebase_calls.append(number)
        if number == 17:
            return _fixture_response(rebase_after_merge["pull_requests"][0], state="MERGED")
        return _fixture_response(
            rebase_after_merge["pull_requests"][1],
            head="d" * 40,
            base="main",
            base_sha="c" * 40,
        )

    rebase_status = run_watch(
        args,
        rebase_after_merge,
        fetch=fetch_after_stack_merge,
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("retargeted stack must stop stale")),
        emit=rebase_events.append,
    )
    assert rebase_status == 2
    assert rebase_calls == [17, 18]
    assert [event["status"] for event in rebase_events] == ["merged", "stale"]
    assert rebase_events[-1]["reasons"][0]["code"] == "base_commit_changed"
    assert rebase_events[-1]["frontier"]["observed_base_sha"] == "c" * 40

    stale_document = _fixture_manifest()
    stale_events: list[dict[str, Any]] = []
    stale_calls: list[int] = []
    stale_status = run_watch(
        args,
        stale_document,
        fetch=lambda _repo, number: (
            stale_calls.append(number)
            or _fixture_response(stale_document["pull_requests"][0], head="c" * 40)
        ),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("stale stack must stop")),
        emit=stale_events.append,
    )
    assert stale_status == 2
    assert stale_calls == [17]
    assert stale_events[0]["status"] == "stale"
    assert stale_events[0]["pr_verdict"]["reasons"][0]["code"] == "head_changed"

    changed_base = _fixture_manifest()
    base_events: list[dict[str, Any]] = []
    base_status = run_watch(
        args,
        changed_base,
        fetch=lambda _repo, number: _fixture_response(
            changed_base["pull_requests"][0], base="release"
        ),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("stale base must stop")),
        emit=base_events.append,
    )
    assert base_status == 2
    assert base_events[0]["status"] == "stale"
    assert base_events[0]["pr_verdict"]["reasons"][0]["code"] == "base_changed"

    changed_base_sha = _fixture_manifest()
    base_sha_events: list[dict[str, Any]] = []
    base_sha_calls: list[int] = []
    base_sha_status = run_watch(
        args,
        changed_base_sha,
        fetch=lambda _repo, number: (
            base_sha_calls.append(number)
            or _fixture_response(
                changed_base_sha["pull_requests"][0], base_sha="d" * 40
            )
        ),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("stale base commit must stop")),
        emit=base_sha_events.append,
    )
    assert base_sha_status == 2
    assert base_sha_calls == [17]
    assert base_sha_events[0]["status"] == "stale"
    assert base_sha_events[0]["reasons"][0]["code"] == "base_commit_changed"
    assert base_sha_events[0]["frontier"]["expected_base_sha"] == "0" * 40
    assert base_sha_events[0]["frontier"]["observed_base_sha"] == "d" * 40
    assert base_sha_events[0]["pr_verdict"] is None
    assert len(base_sha_events[0]["frontier"]["stack_input_sha256"]) == 64
    assert len(base_sha_events[0]["pull_requests"][0]["last_input_sha256"]) == 64
    assert base_sha_events[0]["pull_requests"][0]["last_observed_base_sha"] == "d" * 40

    merged_base_changed = _fixture_manifest()
    merged_base_changed["pull_requests"] = [merged_base_changed["pull_requests"][0]]
    merged_base_events: list[dict[str, Any]] = []
    merged_base_status = run_watch(
        args,
        merged_base_changed,
        fetch=lambda _repo, _number: _fixture_response(
            merged_base_changed["pull_requests"][0],
            state="MERGED",
            merged_base_sha="e" * 40,
        ),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("merged base change must stop")),
        emit=merged_base_events.append,
    )
    assert merged_base_status == 2
    assert merged_base_events[0]["status"] == "stale"
    assert merged_base_events[0]["reasons"][0]["code"] == "base_commit_changed"
    assert merged_base_events[0]["frontier"]["observed_base_sha"] == "e" * 40
    assert (
        merged_base_events[0]["frontier"]["observed_base_source"]
        == "pr_associated_base_ref_oid"
    )

    closed_document = _fixture_manifest()
    closed_calls: list[int] = []
    closed_events: list[dict[str, Any]] = []
    closed_status = run_watch(
        args,
        closed_document,
        fetch=lambda _repo, number: (
            closed_calls.append(number)
            or _fixture_response(closed_document["pull_requests"][0], state="CLOSED")
        ),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("closed PR must stop")),
        emit=closed_events.append,
    )
    assert closed_status == 2
    assert closed_calls == [17]
    assert closed_events[0]["status"] == "blocked"
    assert closed_events[0]["pr_verdict"]["evidence"]["state"] == "closed"

    exhausted_document = _fixture_manifest()
    exhausted_args = argparse.Namespace(
        max_attempts_per_pr=3,
        max_observations=2,
        interval_seconds=10,
        max_observation_age_seconds=900,
        deadline=_rfc3339(start + timedelta(minutes=1)),
    )
    exhausted_responses = {
        17: [
            _fixture_response(exhausted_document["pull_requests"][0]),
            _fixture_response(exhausted_document["pull_requests"][0], state="MERGED"),
        ]
    }
    exhausted_calls: list[int] = []
    exhausted_events: list[dict[str, Any]] = []
    exhausted_status = run_watch(
        exhausted_args,
        exhausted_document,
        fetch=lambda _repo, number: (
            exhausted_calls.append(number) or exhausted_responses[number].pop(0)
        ),
        now=lambda: start,
        sleep=lambda _: None,
        emit=exhausted_events.append,
    )
    assert exhausted_status == 2
    assert exhausted_calls == [17, 17]
    assert exhausted_events[-1]["status"] == "incomplete"
    assert exhausted_events[-1]["reasons"][0]["code"] == "observation_budget_exhausted"

    attempt_document = _fixture_manifest()
    attempt_document["pull_requests"] = [attempt_document["pull_requests"][0]]
    attempt_args = argparse.Namespace(
        max_attempts_per_pr=1,
        max_observations=1,
        interval_seconds=10,
        max_observation_age_seconds=900,
        deadline=_rfc3339(start + timedelta(minutes=1)),
    )
    attempt_events: list[dict[str, Any]] = []

    def pending_attempt_response() -> dict[str, Any]:
        response = _fixture_response(attempt_document["pull_requests"][0])
        contexts = response["data"]["repository"]["pullRequest"]["commits"]["nodes"][0][
            "commit"
        ]["statusCheckRollup"]["contexts"]["nodes"]
        contexts[0]["status"] = "IN_PROGRESS"
        contexts[0]["conclusion"] = None
        return response

    attempt_status = run_watch(
        attempt_args,
        attempt_document,
        fetch=lambda _repo, _number: pending_attempt_response(),
        now=lambda: start,
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("exhausted attempt budget must stop")),
        emit=attempt_events.append,
    )
    assert attempt_status == 2
    assert attempt_events[-1]["status"] == "incomplete"
    assert attempt_events[-1]["reasons"][0]["code"] == "attempt_budget_exhausted"
    assert "attempt_limit_reached" in {
        reason["code"] for reason in attempt_events[-1]["pr_verdict"]["reasons"]
    }

    crossing_deadline = start + timedelta(seconds=10)
    clock_calls = [0]

    def crossing_clock() -> datetime:
        clock_calls[0] += 1
        return crossing_deadline + timedelta(seconds=1) if clock_calls[0] >= 4 else start

    deadline_events: list[dict[str, Any]] = []
    deadline_args = argparse.Namespace(
        max_attempts_per_pr=3,
        max_observations=2,
        interval_seconds=10,
        max_observation_age_seconds=900,
        deadline=_rfc3339(crossing_deadline),
    )
    deadline_status = run_watch(
        deadline_args,
        attempt_document,
        fetch=lambda _repo, _number: _fixture_response(attempt_document["pull_requests"][0]),
        now=crossing_clock,
        sleep=lambda _: None,
        emit=deadline_events.append,
    )
    assert deadline_status == 2
    assert deadline_events[-1]["status"] == "incomplete"
    assert deadline_events[-1]["reasons"][0]["code"] == "deadline_exceeded"
    assert deadline_events[-1]["pr_verdict"]["reasons"][0]["code"] == "deadline_exceeded"

    observer_events: list[dict[str, Any]] = []
    try:
        run_watch(
            attempt_args,
            attempt_document,
            fetch=lambda *_: (_ for _ in ()).throw(
                github_observe.ObserverError("fixture provider error")
            ),
            now=lambda: start,
            sleep=lambda _: None,
            emit=observer_events.append,
        )
    except github_observe.ObserverError:
        pass
    else:
        raise AssertionError("provider observation error must be reported to the caller")
    assert observer_events[-1]["status"] == "incomplete"
    assert observer_events[-1]["terminal"] is True
    assert observer_events[-1]["reasons"][0]["code"] == "provider_observation_failed"

    limited = _fixture_manifest()
    limited_args = argparse.Namespace(
        max_attempts_per_pr=3,
        max_observations=1,
        interval_seconds=10,
        max_observation_age_seconds=900,
        deadline=_rfc3339(start + timedelta(minutes=1)),
    )
    expect_error(
        lambda: run_watch(limited_args, limited, fetch=lambda *_: None, now=lambda: start,
                          sleep=lambda _: None, emit=lambda _: None),
        "at least one observation per PR",
    )


def expect_error(action: Callable[[], Any], expected: str) -> None:
    try:
        action()
    except WatchError as error:
        if expected not in str(error):
            raise AssertionError(f"expected {expected!r} in {str(error)!r}") from error
    else:
        raise AssertionError(f"expected WatchError containing {expected!r}")


def _positive_interval(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer number of seconds") from error
    if not MIN_INTERVAL_SECONDS <= parsed <= MAX_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS} seconds"
        )
    return parsed


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--input", help="frozen stack manifest JSON path")
    command.add_argument("--deadline", help="RFC3339 UTC hard stop, at most 24 hours from start")
    command.add_argument("--max-attempts-per-pr", type=int, default=3)
    command.add_argument("--max-observations", type=int, default=100)
    command.add_argument("--max-observation-age-seconds", type=int, default=900)
    command.add_argument("--interval-seconds", type=_positive_interval, default=60)
    command.add_argument("--self-test", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        self_test()
        print("GitHub PR stack watch self-test passed.")
        return 0
    if not args.input or not args.deadline:
        command.error("--input and --deadline are required unless --self-test is used")
    try:
        document = _read_manifest(args.input)
        return run_watch(
            args,
            document,
            emit=lambda event: print(json.dumps(event, sort_keys=True), flush=True),
        )
    except (OSError, WatchError, github_observe.ObserverError) as error:
        print(f"GitHub PR stack watch stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
