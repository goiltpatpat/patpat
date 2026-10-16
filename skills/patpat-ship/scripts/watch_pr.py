#!/usr/bin/env python3
"""Reobserve and evaluate one GitHub pull request within explicit bounds."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import github_observe
import pr_watch


MAX_WATCH_ATTEMPTS = 100
MAX_WATCH_DURATION_SECONDS = 24 * 60 * 60
MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 3600


class WatchError(ValueError):
    """Raised when a bounded PR watch cannot safely start or continue."""


def _positive_interval(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer number of seconds") from error
    if parsed < MIN_INTERVAL_SECONDS or parsed > MAX_INTERVAL_SECONDS:
        raise argparse.ArgumentTypeError(
            f"must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS} seconds"
        )
    return parsed


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit_json(verdict: dict[str, Any]) -> None:
    print(json.dumps(verdict, sort_keys=True, separators=(",", ":")))


def _exit_code(verdict: dict[str, Any]) -> int:
    return 0 if verdict["verdict"] in {"ready", "stale"} else 2


def run_watch(
    args: argparse.Namespace,
    *,
    fetch: Callable[[str, int], Any] = github_observe.fetch_github,
    now: Callable[[], datetime] = _utc_now,
    sleep: Callable[[float], None] = time.sleep,
    emit: Callable[[dict[str, Any]], None] = _emit_json,
) -> int:
    if type(args.max_attempts) is not int or not 1 <= args.max_attempts <= MAX_WATCH_ATTEMPTS:
        raise WatchError(f"max attempts must be between 1 and {MAX_WATCH_ATTEMPTS}")
    if (
        type(args.interval_seconds) is not int
        or not MIN_INTERVAL_SECONDS <= args.interval_seconds <= MAX_INTERVAL_SECONDS
    ):
        raise WatchError(
            f"poll interval must be between {MIN_INTERVAL_SECONDS} and {MAX_INTERVAL_SECONDS} seconds"
        )

    observer_args = argparse.Namespace(
        repository=args.repository,
        pull_request=args.pull_request,
        expected_head=args.expected_head,
        expected_base=args.expected_base,
        required_check=args.required_check,
        allow_no_required_checks=args.allow_no_required_checks,
        require_review=args.require_review,
        max_attempts=args.max_attempts,
        attempt=1,
        max_observation_age_seconds=args.max_observation_age_seconds,
        deadline=args.deadline,
    )
    github_observe.validate_arguments(observer_args)

    deadline = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    started_at = now()
    if started_at >= deadline:
        raise WatchError("deadline must be in the future")
    if (deadline - started_at).total_seconds() > MAX_WATCH_DURATION_SECONDS:
        raise WatchError("deadline must be within 24 hours")

    last_document: dict[str, Any] | None = None
    for attempt in range(1, args.max_attempts + 1):
        current = now()
        if current >= deadline:
            if last_document is None:
                raise WatchError("deadline expired before the first observation")
            evaluated_at = max(current, deadline + timedelta(microseconds=1))
            verdict = pr_watch.evaluate(last_document, evaluated_at=evaluated_at)
            emit(verdict)
            return _exit_code(verdict)

        response = fetch(args.repository, args.pull_request)
        observed_at = _rfc3339(now())
        last_document = github_observe.observation_document(
            response,
            repository=args.repository,
            pull_request=args.pull_request,
            expected_head=observer_args.expected_head,
            expected_base=args.expected_base,
            required_checks=args.required_check,
            allow_no_required_checks=args.allow_no_required_checks,
            required_review=args.require_review,
            max_attempts=args.max_attempts,
            attempt=attempt,
            max_observation_age_seconds=args.max_observation_age_seconds,
            deadline=args.deadline,
            observed_at=observed_at,
        )
        verdict = pr_watch.evaluate(last_document, evaluated_at=now())
        emit(verdict)
        if verdict["verdict"] != "pending":
            return _exit_code(verdict)

        remaining = (deadline - now()).total_seconds()
        if remaining > 0:
            sleep(min(args.interval_seconds, remaining))

    raise WatchError("watch exhausted its attempt budget without a terminal verdict")


def _fixture_args(*, deadline: datetime, max_attempts: int = 3) -> argparse.Namespace:
    return argparse.Namespace(
        repository="example/project",
        pull_request=17,
        expected_head="a" * 40,
        expected_base="main",
        required_check=["tests", "policy"],
        allow_no_required_checks=False,
        require_review=True,
        max_attempts=max_attempts,
        max_observation_age_seconds=900,
        deadline=_rfc3339(deadline),
        interval_seconds=10,
    )


def _pending_fixture() -> dict[str, Any]:
    response = github_observe.fixture()
    pull_request = response["data"]["repository"]["pullRequest"]
    pull_request["reviewThreads"]["nodes"] = [
        {"isResolved": True},
        {"isResolved": True},
    ]
    return response


def _ready_fixture() -> dict[str, Any]:
    response = _pending_fixture()
    pull_request = response["data"]["repository"]["pullRequest"]
    contexts = pull_request["commits"]["nodes"][0]["commit"]["statusCheckRollup"][
        "contexts"
    ]["nodes"]
    contexts[1]["state"] = "SUCCESS"
    return response


def self_test() -> None:
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    current = [start]
    responses = [_pending_fixture(), _ready_fixture()]
    emitted: list[dict[str, Any]] = []
    sleeps: list[float] = []

    def fetch(_: str, __: int) -> Any:
        return responses.pop(0)

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        current[0] += timedelta(seconds=seconds)

    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1)),
        fetch=fetch,
        now=lambda: current[0],
        sleep=sleep,
        emit=emitted.append,
    )
    assert status == 0
    assert [result["verdict"] for result in emitted] == ["pending", "ready"]
    assert [result["observation"]["attempt"] for result in emitted] == [1, 2]
    assert sleeps == [10]

    current[0] = start
    blocked_merge = _ready_fixture()
    blocked_merge["data"]["repository"]["pullRequest"]["mergeStateStatus"] = "BLOCKED"
    blocked_results: list[dict[str, Any]] = []
    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1)),
        fetch=lambda *_: blocked_merge,
        now=lambda: current[0],
        sleep=lambda _: (_ for _ in ()).throw(
            AssertionError("blocked provider state must stop the watch")
        ),
        emit=blocked_results.append,
    )
    assert status == 2
    assert blocked_results[0]["verdict"] == "blocked"
    assert blocked_results[0]["reasons"][0]["code"] == "provider_merge_state_blocked"

    current[0] = start
    blocked_pending_review = _ready_fixture()
    blocked_pending_review["data"]["repository"]["pullRequest"]["mergeStateStatus"] = "BLOCKED"
    blocked_pending_review["data"]["repository"]["pullRequest"][
        "reviewDecision"
    ] = "REVIEW_REQUIRED"
    pending_review_results: list[dict[str, Any]] = []
    review_responses = [blocked_pending_review, _ready_fixture()]
    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1)),
        fetch=lambda *_: review_responses.pop(0),
        now=lambda: current[0],
        sleep=sleep,
        emit=pending_review_results.append,
    )
    assert status == 0
    assert [result["verdict"] for result in pending_review_results] == ["pending", "ready"]

    current[0] = start
    unstable_pending_check = _ready_fixture()
    unstable_pr = unstable_pending_check["data"]["repository"]["pullRequest"]
    unstable_pr["mergeStateStatus"] = "UNSTABLE"
    unstable_contexts = unstable_pr["commits"]["nodes"][0]["commit"][
        "statusCheckRollup"
    ]["contexts"]["nodes"]
    unstable_contexts[0]["status"] = "IN_PROGRESS"
    unstable_contexts[0]["conclusion"] = None
    pending_check_results: list[dict[str, Any]] = []
    check_responses = [unstable_pending_check, _ready_fixture()]
    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1)),
        fetch=lambda *_: check_responses.pop(0),
        now=lambda: current[0],
        sleep=sleep,
        emit=pending_check_results.append,
    )
    assert status == 0
    assert [result["verdict"] for result in pending_check_results] == ["pending", "ready"]

    current[0] = start
    changed_head = _ready_fixture()
    pull_request = changed_head["data"]["repository"]["pullRequest"]
    changed_sha = "b" * 40
    pull_request["headRefOid"] = changed_sha
    pull_request["commits"]["nodes"][0]["commit"]["oid"] = changed_sha
    stale_results: list[dict[str, Any]] = []
    fetch_count = [0]

    def fetch_stale(_: str, __: int) -> Any:
        fetch_count[0] += 1
        return changed_head

    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1)),
        fetch=fetch_stale,
        now=lambda: current[0],
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("stale watch must stop")),
        emit=stale_results.append,
    )
    assert status == 0
    assert fetch_count == [1]
    assert stale_results[0]["verdict"] == "stale"
    assert stale_results[0]["binding"]["head_sha"] == "a" * 40

    current[0] = start
    deadline_results: list[dict[str, Any]] = []

    def sleep_to_deadline(seconds: float) -> None:
        current[0] += timedelta(seconds=seconds)

    status = run_watch(
        _fixture_args(deadline=start + timedelta(seconds=5)),
        fetch=lambda _repository, _pull_request: _pending_fixture(),
        now=lambda: current[0],
        sleep=sleep_to_deadline,
        emit=deadline_results.append,
    )
    assert status == 2
    assert [result["verdict"] for result in deadline_results] == ["pending", "blocked"]
    assert deadline_results[-1]["reasons"][0]["code"] == "deadline_exceeded"

    current[0] = start
    attempt_results: list[dict[str, Any]] = []
    status = run_watch(
        _fixture_args(deadline=start + timedelta(minutes=1), max_attempts=1),
        fetch=lambda _repository, _pull_request: _pending_fixture(),
        now=lambda: current[0],
        sleep=lambda _: (_ for _ in ()).throw(AssertionError("exhausted watch must stop")),
        emit=attempt_results.append,
    )
    assert status == 2
    assert attempt_results[0]["verdict"] == "blocked"
    assert attempt_results[0]["reasons"][-1]["code"] == "attempt_limit_reached"


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--repository")
    command.add_argument("--pull-request", type=int)
    command.add_argument("--expected-head")
    command.add_argument("--expected-base")
    command.add_argument("--required-check", action="append", default=[])
    command.add_argument("--allow-no-required-checks", action="store_true")
    command.add_argument("--require-review", action="store_true")
    command.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help=f"maximum observations from 1 to {MAX_WATCH_ATTEMPTS} (default: 3)",
    )
    command.add_argument(
        "--max-observation-age-seconds",
        type=int,
        default=900,
        help="maximum accepted observation age from 1 to 3600 seconds (default: 900)",
    )
    command.add_argument(
        "--deadline",
        help="RFC3339 UTC hard stop, at most 24 hours from start",
    )
    command.add_argument(
        "--interval-seconds",
        type=_positive_interval,
        default=60,
        help=(
            f"poll interval from {MIN_INTERVAL_SECONDS} to {MAX_INTERVAL_SECONDS} "
            "seconds (default: 60)"
        ),
    )
    command.add_argument("--self-test", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        self_test()
        print("GitHub PR watch self-test passed.")
        return 0
    required = (
        args.repository,
        args.pull_request,
        args.expected_head,
        args.expected_base,
        args.deadline,
    )
    if any(value is None for value in required):
        command.error(
            "--repository, --pull-request, --expected-head, --expected-base, and --deadline are required"
        )
    try:
        return run_watch(args)
    except (WatchError, github_observe.ObserverError) as error:
        print(f"GitHub PR watch stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
