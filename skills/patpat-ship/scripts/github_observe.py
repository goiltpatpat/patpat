#!/usr/bin/env python3
"""Capture one bounded read-only GitHub pull-request observation for pr_watch."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 3
MAX_API_BYTES = 1024 * 1024
MAX_CHECKS = 100
MAX_NAME_LENGTH = 128
REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
)
SHA = re.compile(r"^[0-9a-f]{40}$")
GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequest(number: $number) {
      number
      headRefOid
      baseRefName
      isDraft
      state
      merged
      mergeable
      reviewDecision
      reviewThreads(first: 100) {
        nodes { isResolved }
        pageInfo { hasNextPage endCursor }
      }
      commits(last: 1) {
        nodes {
          commit {
            oid
            statusCheckRollup {
              contexts(first: 100) {
                nodes {
                  __typename
                  ... on CheckRun { name status conclusion }
                  ... on StatusContext { context state }
                }
                pageInfo { hasNextPage endCursor }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


class ObserverError(ValueError):
    """Raised when GitHub cannot provide one complete bounded observation."""


def mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ObserverError(f"{field} must be an object")
    return value


def nodes(value: Any, field: str) -> list[Any]:
    connection = mapping(value, field)
    page_info = mapping(connection.get("pageInfo"), f"{field}.pageInfo")
    if page_info.get("hasNextPage") is not False:
        raise ObserverError(f"{field} exceeds the bounded first 100 entries")
    result = connection.get("nodes")
    if not isinstance(result, list) or len(result) > MAX_CHECKS:
        raise ObserverError(f"{field}.nodes must be a bounded array")
    return result


def bounded_string(value: Any, field: str, maximum: int = MAX_NAME_LENGTH) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ObserverError(f"{field} must be a bounded non-empty string")
    return value


def normalize_check(raw: Any, index: int) -> dict[str, str | None]:
    check = mapping(raw, f"checks[{index}]")
    kind = check.get("__typename")
    if kind == "CheckRun":
        name = bounded_string(check.get("name"), f"checks[{index}].name")
        status = bounded_string(check.get("status"), f"checks[{index}].status").upper()
        state = {
            "QUEUED": "queued",
            "IN_PROGRESS": "in_progress",
            "COMPLETED": "completed",
            "WAITING": "queued",
            "PENDING": "queued",
            "REQUESTED": "queued",
        }.get(status)
        if state is None:
            raise ObserverError(f"checks[{index}].status is unsupported: {status}")
        conclusion: str | None = None
        if state == "completed":
            raw_conclusion = bounded_string(
                check.get("conclusion"), f"checks[{index}].conclusion"
            ).lower()
            conclusion = {
                "startup_failure": "failure",
                "stale": "stale",
            }.get(raw_conclusion, raw_conclusion)
        elif check.get("conclusion") is not None:
            raise ObserverError(f"checks[{index}].conclusion appeared before completion")
        return {"name": name, "state": state, "conclusion": conclusion}
    if kind == "StatusContext":
        name = bounded_string(check.get("context"), f"checks[{index}].context")
        status = bounded_string(check.get("state"), f"checks[{index}].state").upper()
        state, conclusion = {
            "EXPECTED": ("queued", None),
            "PENDING": ("in_progress", None),
            "SUCCESS": ("completed", "success"),
            "FAILURE": ("completed", "failure"),
            "ERROR": ("completed", "failure"),
        }.get(status, (None, None))
        if state is None:
            raise ObserverError(f"checks[{index}].state is unsupported: {status}")
        return {"name": name, "state": state, "conclusion": conclusion}
    raise ObserverError(f"checks[{index}] has unsupported type: {kind!r}")


def observation_document(
    response: Any,
    *,
    repository: str,
    pull_request: int,
    expected_head: str,
    expected_base: str,
    required_checks: list[str],
    required_review: bool,
    max_attempts: int,
    attempt: int,
    max_observation_age_seconds: int,
    deadline: str,
    observed_at: str,
) -> dict[str, Any]:
    root = mapping(response, "response")
    errors = root.get("errors")
    if errors:
        raise ObserverError("GitHub GraphQL returned errors")
    repository_data = mapping(mapping(root.get("data"), "data").get("repository"), "repository")
    provider_repository = bounded_string(
        repository_data.get("nameWithOwner"), "repository.nameWithOwner", 256
    )
    pr = mapping(repository_data.get("pullRequest"), "repository.pullRequest")
    provider_number = pr.get("number")
    if isinstance(provider_number, bool) or not isinstance(provider_number, int):
        raise ObserverError("pull request number is invalid")
    provider_head = bounded_string(pr.get("headRefOid"), "pullRequest.headRefOid", 40).lower()
    if SHA.fullmatch(provider_head) is None:
        raise ObserverError("pull request head is not a full commit SHA")
    provider_base = bounded_string(pr.get("baseRefName"), "pullRequest.baseRefName")

    thread_nodes = nodes(pr.get("reviewThreads"), "pullRequest.reviewThreads")
    unresolved_threads = 0
    for index, thread in enumerate(thread_nodes):
        resolved = mapping(thread, f"reviewThreads[{index}]").get("isResolved")
        if not isinstance(resolved, bool):
            raise ObserverError(f"reviewThreads[{index}].isResolved must be a boolean")
        unresolved_threads += int(not resolved)

    commits = mapping(pr.get("commits"), "pullRequest.commits").get("nodes")
    if not isinstance(commits, list) or len(commits) != 1:
        raise ObserverError("pull request must expose exactly one latest commit")
    commit = mapping(mapping(commits[0], "pullRequest.commits[0]").get("commit"), "commit")
    if commit.get("oid") != provider_head:
        raise ObserverError("latest commit does not match the provider head")
    rollup = commit.get("statusCheckRollup")
    raw_checks: list[Any] = []
    if rollup is not None:
        raw_checks = nodes(mapping(rollup, "statusCheckRollup").get("contexts"), "checks")
    checks = [normalize_check(raw, index) for index, raw in enumerate(raw_checks)]
    check_names = [str(check["name"]) for check in checks]
    if len(check_names) != len(set(check_names)):
        raise ObserverError("GitHub returned duplicate check names; observation is ambiguous")

    raw_state = bounded_string(pr.get("state"), "pullRequest.state").upper()
    merged = pr.get("merged")
    if not isinstance(merged, bool):
        raise ObserverError("pullRequest.merged must be a boolean")
    state = "merged" if merged else {"OPEN": "open", "CLOSED": "closed"}.get(raw_state)
    if state is None:
        raise ObserverError(f"pullRequest.state is unsupported: {raw_state}")
    draft = pr.get("isDraft")
    if not isinstance(draft, bool):
        raise ObserverError("pullRequest.isDraft must be a boolean")
    mergeability = {
        "MERGEABLE": "mergeable",
        "CONFLICTING": "conflicting",
        "UNKNOWN": "unknown",
    }.get(bounded_string(pr.get("mergeable"), "pullRequest.mergeable").upper())
    if mergeability is None:
        raise ObserverError("pullRequest.mergeable is unsupported")
    raw_review = pr.get("reviewDecision")
    review_decision = {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes_requested",
        "REVIEW_REQUIRED": "review_required",
        None: "review_required" if required_review else "not_required",
    }.get(raw_review)
    if review_decision is None:
        raise ObserverError(f"pullRequest.reviewDecision is unsupported: {raw_review!r}")

    return {
        "schema_version": SCHEMA_VERSION,
        "binding": {
            "repository": repository,
            "pull_request": pull_request,
            "head_sha": expected_head,
            "base_ref": expected_base,
        },
        "policy": {
            "required_checks": required_checks,
            "required_review": required_review,
            "max_attempts": max_attempts,
            "max_observation_age_seconds": max_observation_age_seconds,
            "deadline": deadline,
        },
        "observation": {
            "observed_at": observed_at,
            "attempt": attempt,
            "head_sha": provider_head,
            "provider_repository": provider_repository,
            "provider_pull_request": provider_number,
            "provider_head_sha": provider_head,
            "state": state,
            "unresolved_threads": unresolved_threads,
            "base_ref": provider_base,
            "draft": draft,
            "review_decision": review_decision,
            "mergeability": mergeability,
            "checks": checks,
        },
    }


def github_command(executable: str, repository: str, pull_request: int) -> list[str]:
    owner, name = repository.split("/", 1)
    return [
        executable,
        "api",
        "graphql",
        "--hostname",
        "github.com",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"number={pull_request}",
        "-f",
        f"query={GRAPHQL_QUERY}",
    ]


def fetch_github(repository: str, pull_request: int) -> Any:
    executable = shutil.which("gh")
    if executable is None:
        raise ObserverError("GitHub CLI is required")
    try:
        result = subprocess.run(
            github_command(executable, repository, pull_request),
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ObserverError(f"GitHub observation failed: {error}") from error
    if result.returncode != 0:
        raise ObserverError(f"GitHub CLI exited with status {result.returncode}")
    if len(result.stdout) > MAX_API_BYTES:
        raise ObserverError("GitHub observation exceeds the byte limit")
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ObserverError("GitHub returned invalid bounded JSON") from error


def validate_arguments(args: argparse.Namespace) -> None:
    if REPOSITORY.fullmatch(args.repository or "") is None:
        raise ObserverError("repository must be OWNER/REPO")
    if args.pull_request < 1 or args.pull_request > 1_000_000:
        raise ObserverError("pull request number is out of range")
    args.expected_head = args.expected_head.lower()
    if SHA.fullmatch(args.expected_head) is None:
        raise ObserverError("expected head must be a full 40-character commit SHA")
    bounded_string(args.expected_base, "expected base")
    if not 1 <= args.attempt <= 1_000_000 or not 1 <= args.max_attempts <= 1_000_000:
        raise ObserverError("attempt values must be positive bounded integers")
    if not 1 <= args.max_observation_age_seconds <= 3600:
        raise ObserverError("maximum observation age must be between 1 and 3600 seconds")
    if not args.required_check and not args.allow_no_required_checks:
        raise ObserverError(
            "at least one required check is required; use --allow-no-required-checks only when repository policy proves CI is not required"
        )
    if args.required_check and args.allow_no_required_checks:
        raise ObserverError("--allow-no-required-checks cannot be combined with --required-check")
    if len(args.required_check) > MAX_CHECKS or len(args.required_check) != len(set(args.required_check)):
        raise ObserverError("required checks must be at most 100 unique names")
    for index, name in enumerate(args.required_check):
        bounded_string(name, f"required check {index}")
    try:
        parsed = datetime.fromisoformat(args.deadline.replace("Z", "+00:00"))
    except ValueError as error:
        raise ObserverError("deadline must be an RFC3339 UTC timestamp") from error
    if not args.deadline.endswith("Z") or parsed.tzinfo != timezone.utc:
        raise ObserverError("deadline must be an RFC3339 UTC timestamp ending in Z")


def fixture() -> dict[str, Any]:
    return {
        "data": {
            "repository": {
                "nameWithOwner": "example/project",
                "pullRequest": {
                    "number": 17,
                    "headRefOid": "a" * 40,
                    "baseRefName": "main",
                    "isDraft": False,
                    "state": "OPEN",
                    "merged": False,
                    "mergeable": "MERGEABLE",
                    "reviewDecision": "APPROVED",
                    "reviewThreads": {
                        "nodes": [{"isResolved": True}, {"isResolved": False}],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    },
                    "commits": {
                        "nodes": [
                            {
                                "commit": {
                                    "oid": "a" * 40,
                                    "statusCheckRollup": {
                                        "contexts": {
                                            "nodes": [
                                                {
                                                    "__typename": "CheckRun",
                                                    "name": "tests",
                                                    "status": "COMPLETED",
                                                    "conclusion": "SUCCESS",
                                                },
                                                {
                                                    "__typename": "StatusContext",
                                                    "context": "policy",
                                                    "state": "PENDING",
                                                },
                                            ],
                                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                                        }
                                    },
                                }
                            }
                        ]
                    },
                },
            }
        }
    }


def self_test() -> None:
    common = {
        "repository": "example/project",
        "pull_request": 17,
        "expected_head": "a" * 40,
        "expected_base": "main",
        "required_checks": ["tests", "policy"],
        "required_review": True,
        "max_attempts": 3,
        "attempt": 1,
        "max_observation_age_seconds": 900,
        "deadline": "2026-08-30T00:00:00Z",
        "observed_at": "2026-08-29T12:00:00Z",
    }
    document = observation_document(fixture(), **common)
    assert document["observation"]["unresolved_threads"] == 1
    assert document["observation"]["checks"] == [
        {"name": "tests", "state": "completed", "conclusion": "success"},
        {"name": "policy", "state": "in_progress", "conclusion": None},
    ]
    from pr_watch import evaluate

    blocked = evaluate(document, evaluated_at=common["observed_at"])
    assert blocked["verdict"] == "blocked"
    assert blocked["reasons"][0]["code"] == "unresolved_review_threads"

    ready_fixture = fixture()
    ready_pr = ready_fixture["data"]["repository"]["pullRequest"]
    ready_pr["reviewThreads"]["nodes"] = []
    ready_contexts = ready_pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"][
        "contexts"
    ]["nodes"]
    ready_contexts[1]["state"] = "SUCCESS"
    ready_document = observation_document(ready_fixture, **common)
    assert evaluate(ready_document, evaluated_at=common["observed_at"])["verdict"] == "ready"

    paged = fixture()
    paged["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"] = True
    try:
        observation_document(paged, **common)
    except ObserverError as error:
        assert "exceeds" in str(error)
    else:
        raise AssertionError("truncated review threads were accepted")

    duplicate = fixture()
    contexts = duplicate["data"]["repository"]["pullRequest"]["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"]
    contexts[1] = {
        "__typename": "StatusContext",
        "context": "tests",
        "state": "SUCCESS",
    }
    try:
        observation_document(duplicate, **common)
    except ObserverError as error:
        assert "duplicate check" in str(error)
    else:
        raise AssertionError("ambiguous duplicate checks were accepted")

    missing = fixture()
    missing["data"]["repository"]["pullRequest"] = None
    try:
        observation_document(missing, **common)
    except ObserverError:
        pass
    else:
        raise AssertionError("missing pull request was accepted")

    command = github_command("/usr/bin/gh", "example/project", 17)
    assert command[:5] == [
        "/usr/bin/gh",
        "api",
        "graphql",
        "--hostname",
        "github.com",
    ]

    empty_policy = parser().parse_args(
        [
            "--repository", "example/project",
            "--pull-request", "17",
            "--expected-head", "a" * 40,
            "--expected-base", "main",
            "--deadline", "2026-08-30T00:00:00Z",
        ]
    )
    try:
        validate_arguments(empty_policy)
    except ObserverError as error:
        assert "at least one required check" in str(error)
    else:
        raise AssertionError("empty required-check policy was accepted without an explicit override")
    empty_policy.allow_no_required_checks = True
    validate_arguments(empty_policy)
    print("GitHub PR observer self-test passed.")


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--repository")
    command.add_argument("--pull-request", type=int)
    command.add_argument("--expected-head")
    command.add_argument("--expected-base")
    command.add_argument("--required-check", action="append", default=[])
    command.add_argument("--allow-no-required-checks", action="store_true")
    command.add_argument("--require-review", action="store_true")
    command.add_argument("--max-attempts", type=int, default=3)
    command.add_argument("--attempt", type=int, default=1)
    command.add_argument("--max-observation-age-seconds", type=int, default=900)
    command.add_argument("--deadline")
    command.add_argument("--self-test", action="store_true")
    return command


def main() -> int:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        return 0
    required = (args.repository, args.pull_request, args.expected_head, args.expected_base, args.deadline)
    if any(value is None for value in required):
        parser().error(
            "--repository, --pull-request, --expected-head, --expected-base, and --deadline are required"
        )
    try:
        validate_arguments(args)
        response = fetch_github(args.repository, args.pull_request)
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        document = observation_document(
            response,
            repository=args.repository,
            pull_request=args.pull_request,
            expected_head=args.expected_head,
            expected_base=args.expected_base,
            required_checks=args.required_check,
            required_review=args.require_review,
            max_attempts=args.max_attempts,
            attempt=args.attempt,
            max_observation_age_seconds=args.max_observation_age_seconds,
            deadline=args.deadline,
            observed_at=observed_at,
        )
    except ObserverError as error:
        print(f"GitHub observation refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(document, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
