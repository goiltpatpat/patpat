#!/usr/bin/env python3
"""Capture one bounded read-only GitHub pull-request observation for pr_watch."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any


SCHEMA_VERSION = 5
MAX_API_BYTES = 1024 * 1024
MAX_CHECKS = 100
MAX_REVIEW_PAGES = 10
MAX_REVIEW_THREADS = MAX_REVIEW_PAGES * 100
MAX_FETCH_SECONDS = 30
MAX_NAME_LENGTH = 128
MERGE_STATE_STATUSES = {
    "BEHIND",
    "BLOCKED",
    "CLEAN",
    "DIRTY",
    "DRAFT",
    "HAS_HOOKS",
    "UNKNOWN",
    "UNSTABLE",
}
REPOSITORY = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9._-]{1,100}$"
)
SHA = re.compile(r"^[0-9a-f]{40}$")
GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequest(number: $number) {
      number
      headRefOid
      baseRefName
      baseRefOid
      isDraft
      state
      merged
      mergeable
      reviewDecision
      mergeStateStatus
      baseRef {
        name
        target {
          __typename
          oid
        }
        branchProtectionRule {
          requiresApprovingReviews
          requiredApprovingReviewCount
          requiresCodeOwnerReviews
          requireLastPushApproval
        }
        rules(first: 100) {
          nodes {
            type
            parameters {
              __typename
              ... on PullRequestParameters {
                requiredApprovingReviewCount
                requireCodeOwnerReview
                requireLastPushApproval
                requiredReviewers { minimumApprovals }
              }
            }
          }
          pageInfo { hasNextPage endCursor }
        }
      }
      reviewThreads(first: 100, after: $after) {
        totalCount
        nodes { id isResolved }
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


def nodes(value: Any, field: str, maximum: int = MAX_CHECKS) -> list[Any]:
    connection = mapping(value, field)
    page_info = mapping(connection.get("pageInfo"), f"{field}.pageInfo")
    if page_info.get("hasNextPage") is not False:
        raise ObserverError(f"{field} exceeds the complete bounded observation")
    result = connection.get("nodes")
    if not isinstance(result, list) or len(result) > maximum:
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


def normalized_pull_request_state(raw_state: Any, merged: Any) -> str:
    state = bounded_string(raw_state, "pullRequest.state").upper()
    if state not in {"OPEN", "CLOSED", "MERGED"}:
        raise ObserverError(f"pullRequest.state is unsupported: {state}")
    if not isinstance(merged, bool):
        raise ObserverError("pullRequest.merged must be a boolean")
    normalized = {
        ("OPEN", False): "open",
        ("CLOSED", False): "closed",
        ("MERGED", True): "merged",
    }.get((state, merged))
    if normalized is None:
        raise ObserverError("pullRequest.state conflicts with pullRequest.merged")
    return normalized


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


def provider_review_not_required(pr: dict[str, Any], base: str) -> bool:
    """Recognize only complete, same-response no-approval policy; never infer it from jobs."""
    if "reviewDecision" not in pr or pr["reviewDecision"] is not None:
        return False
    # Also require GitHub's aggregate gate, not MERGEABLE or viewer bypass rights.
    if pr.get("mergeStateStatus") != "CLEAN":
        return False
    ref = pr.get("baseRef")
    if not isinstance(ref, dict) or ref.get("name") != base or "branchProtectionRule" not in ref:
        return False
    classic = ref["branchProtectionRule"]
    if classic is not None:
        if not isinstance(classic, dict) or not (
            classic.get("requiresApprovingReviews") is False
            and type(classic.get("requiredApprovingReviewCount")) is int
            and classic["requiredApprovingReviewCount"] == 0
            and classic.get("requiresCodeOwnerReviews") is False
            and classic.get("requireLastPushApproval") is False
        ):
            return False
    for raw in nodes(ref.get("rules"), "baseRef.rules"):
        rule = mapping(raw, "baseRef.rules.node")
        if rule.get("type") in {"DELETION", "NON_FAST_FORWARD", "REQUIRED_STATUS_CHECKS"}:
            continue
        if rule.get("type") != "PULL_REQUEST":
            return False  # Uninterpreted rule types cannot earn an exemption.
        params = rule.get("parameters")
        if not isinstance(params, dict) or not (
            params.get("__typename") == "PullRequestParameters"
            and type(params.get("requiredApprovingReviewCount")) is int
            and params["requiredApprovingReviewCount"] == 0
            and params.get("requireCodeOwnerReview") is False
            and params.get("requireLastPushApproval") is False
            and params.get("requiredReviewers") == []
        ):
            return False
    return True


def observation_document(
    response: Any,
    *,
    repository: str,
    pull_request: int,
    expected_head: str,
    expected_base: str,
    required_checks: list[str],
    allow_no_required_checks: bool,
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

    thread_nodes = nodes(pr.get("reviewThreads"), "pullRequest.reviewThreads", MAX_REVIEW_THREADS)
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

    merged = pr.get("merged")
    state = normalized_pull_request_state(pr.get("state"), merged)
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
    merge_state_status = bounded_string(
        pr.get("mergeStateStatus"), "pullRequest.mergeStateStatus"
    ).upper()
    if merge_state_status not in MERGE_STATE_STATUSES:
        raise ObserverError("pullRequest.mergeStateStatus is unsupported")
    raw_review = pr.get("reviewDecision")
    review_decision = {
        "APPROVED": "approved",
        "CHANGES_REQUESTED": "changes_requested",
        "REVIEW_REQUIRED": "review_required",
        None: "review_required",
    }.get(raw_review)
    if review_decision is None:
        raise ObserverError(f"pullRequest.reviewDecision is unsupported: {raw_review!r}")
    policy_proven = provider_review_not_required(pr, provider_base)
    if policy_proven:
        review_decision = "not_required"

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
            "allow_no_required_checks": allow_no_required_checks,
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
            **({"review_policy": {
                "base_ref": pr["baseRef"],
                "merge_state_status": pr["mergeStateStatus"],
            }} if policy_proven else {}),
            "mergeability": mergeability,
            "merge_state_status": merge_state_status,
            "checks": checks,
        },
    }


def provider_base_commit_oid(response: Any) -> tuple[str, str]:
    """Return the live unmerged-PR base tip or the base OID recorded on a merged PR."""
    root = mapping(response, "response")
    if root.get("errors"):
        raise ObserverError("GitHub GraphQL returned errors")
    repository = mapping(mapping(root.get("data"), "data").get("repository"), "repository")
    pull_request = mapping(repository.get("pullRequest"), "repository.pullRequest")
    state = normalized_pull_request_state(
        pull_request.get("state"), pull_request.get("merged")
    )
    if state == "merged":
        base_oid = bounded_string(
            pull_request.get("baseRefOid"), "pullRequest.baseRefOid", 40
        ).lower()
        source = "pr_associated_base_ref_oid"
    else:
        base_ref_name = bounded_string(
            pull_request.get("baseRefName"), "pullRequest.baseRefName"
        )
        base_ref = mapping(pull_request.get("baseRef"), "pullRequest.baseRef")
        if bounded_string(base_ref.get("name"), "pullRequest.baseRef.name") != base_ref_name:
            raise ObserverError("pull request base ref name does not match its baseRefName")
        target = mapping(base_ref.get("target"), "pullRequest.baseRef.target")
        if target.get("__typename") != "Commit":
            raise ObserverError("pull request base ref must point to a commit")
        base_oid = bounded_string(
            target.get("oid"), "pullRequest.baseRef.target.oid", 40
        ).lower()
        source = "live_base_ref_target"
    if SHA.fullmatch(base_oid) is None:
        raise ObserverError("pull request base commit is not a full 40-character SHA")
    return base_oid, source


def github_command(
    executable: str, repository: str, pull_request: int, after: str | None = None
) -> list[str]:
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
    ] + (["-f", f"after={after}"] if after is not None else [])


def fetch_github(repository: str, pull_request: int) -> Any:
    executable = shutil.which("gh")
    if executable is None:
        raise ObserverError("GitHub CLI is required")
    deadline = time.monotonic() + MAX_FETCH_SECONDS
    response_bytes = 0
    expected_metadata: dict[str, Any] | None = None
    expected_total: int | None = None

    def read_page(after: str | None) -> dict[str, Any]:
        nonlocal response_bytes
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ObserverError("GitHub observation exceeds the time limit")
        try:
            result = subprocess.run(
                github_command(executable, repository, pull_request, after),
                check=False,
                capture_output=True,
                timeout=remaining,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ObserverError("GitHub observation request failed or timed out") from error
        if time.monotonic() >= deadline:
            raise ObserverError("GitHub observation exceeds the time limit")
        if result.returncode != 0:
            raise ObserverError(f"GitHub CLI exited with status {result.returncode}")
        response_bytes += len(result.stdout)
        if response_bytes > MAX_API_BYTES:
            raise ObserverError("GitHub observation exceeds the cumulative byte limit")
        try:
            response = mapping(json.loads(result.stdout.decode("utf-8")), "response")
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise ObserverError("GitHub returned invalid bounded JSON") from error
        if response.get("errors"):
            raise ObserverError("GitHub GraphQL returned errors")
        return response

    def collect() -> tuple[dict[str, Any], list[dict[str, Any]], int]:
        nonlocal expected_metadata, expected_total
        after = None
        cursors: set[str] = set()
        thread_ids: set[str] = set()
        threads: list[dict[str, Any]] = []
        for page_index in range(MAX_REVIEW_PAGES):
            response = read_page(after)
            repo = mapping(mapping(response.get("data"), "data").get("repository"), "repository")
            pr = mapping(repo.get("pullRequest"), "repository.pullRequest")
            if (
                bounded_string(repo.get("nameWithOwner"), "repository.nameWithOwner", 256).lower() != repository.lower()
                or type(pr.get("number")) is not int or pr["number"] != pull_request
            ):
                raise ObserverError("GitHub observation identity changed or mismatched")
            metadata = {key: value for key, value in pr.items() if key != "reviewThreads"}
            if expected_metadata is not None and metadata != expected_metadata:
                raise ObserverError("GitHub pull request metadata changed during pagination")
            expected_metadata = metadata
            connection = mapping(pr.get("reviewThreads"), "pullRequest.reviewThreads")
            total = connection.get("totalCount")
            if type(total) is not int or not 0 <= total <= MAX_REVIEW_THREADS:
                raise ObserverError("reviewThreads.totalCount exceeds the bounded integer range")
            if expected_total is not None and total != expected_total:
                raise ObserverError("reviewThreads count changed during pagination")
            expected_total = total
            page_info = mapping(connection.get("pageInfo"), "reviewThreads.pageInfo")
            more = page_info.get("hasNextPage")
            if type(more) is not bool:
                raise ObserverError("reviewThreads.hasNextPage must be a boolean")
            raw_threads = connection.get("nodes")
            if not isinstance(raw_threads, list) or len(raw_threads) > 100:
                raise ObserverError("reviewThreads.nodes must be a bounded page")
            if more and not raw_threads:
                raise ObserverError("reviewThreads contains an empty intermediate page")
            for raw in raw_threads:
                thread = mapping(raw, "reviewThreads.node")
                thread_id = bounded_string(thread.get("id"), "reviewThreads.id", 256)
                if type(thread.get("isResolved")) is not bool:
                    raise ObserverError("reviewThreads.isResolved must be a boolean")
                if thread_id in thread_ids:
                    raise ObserverError("reviewThreads contains duplicate thread IDs")
                thread_ids.add(thread_id)
                threads.append({"id": thread_id, "isResolved": thread["isResolved"]})
            if len(threads) > total or (more and len(threads) >= total):
                raise ObserverError("reviewThreads count conflicts with pagination")
            if not more:
                if len(threads) != total:
                    raise ObserverError("reviewThreads count is incomplete")
                return response, threads, page_index + 1
            after = bounded_string(page_info.get("endCursor"), "reviewThreads.endCursor", 1024)
            if after in cursors:
                raise ObserverError("reviewThreads cursor repeated during pagination")
            cursors.add(after)
        raise ObserverError("reviewThreads exceeds the page limit")

    response, threads, page_count = collect()
    if page_count > 1:
        # Detect observable drift, not an atomic snapshot or changes after this read.
        response, repeated_threads, _ = collect()
        if threads != repeated_threads:
            raise ObserverError("reviewThreads changed between pagination passes")
    if time.monotonic() >= deadline:
        raise ObserverError("GitHub observation exceeds the time limit")
    response["data"]["repository"]["pullRequest"]["reviewThreads"] = {
        "totalCount": len(threads),
        "nodes": threads,
        "pageInfo": {"hasNextPage": False, "endCursor": None},
    }
    return response


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
                    "baseRefOid": "0" * 40,
                    "isDraft": False,
                    "state": "OPEN",
                    "merged": False,
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "CLEAN",
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


def pagination_self_test(common: dict[str, Any]) -> None:
    from copy import deepcopy
    from unittest.mock import patch
    from pr_watch import evaluate

    def page(start: int, stop: int, total: int = 101) -> dict[str, Any]:
        response = fixture()
        pr = response["data"]["repository"]["pullRequest"]
        pr["baseRef"] = {
            "name": "main", "target": {"__typename": "Commit", "oid": "0" * 40},
            "branchProtectionRule": None,
            "rules": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}},
        }
        pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["nodes"][1]["state"] = "SUCCESS"
        pr["reviewThreads"] = {
            "totalCount": total,
            "nodes": [{"id": f"thread-{index}", "isResolved": index != 100} for index in range(start, stop)],
            "pageInfo": {"hasNextPage": stop < total, "endCursor": f"cursor-{stop}"},
        }
        return response

    def fetch_pages(pages: list[Any], *, expected_cursors: list[str | None] | None = None) -> Any:
        commands: list[list[str]] = []

        def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
            assert kwargs["timeout"] > 0 and kwargs["timeout"] <= 30
            assert len(commands) < len(pages), "unexpected extra provider request"
            response = pages[len(commands)]
            commands.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps(response).encode(), b"")

        with patch.object(shutil, "which", return_value="gh"), patch.object(subprocess, "run", side_effect=run):
            response = fetch_github("example/project", 17)
        assert len(commands) == len(pages)
        if expected_cursors is not None:
            assert [next((arg[6:] for arg in command if arg.startswith("after=")), None) for command in commands] == expected_cursors
            assert all(command[:5] == ["gh", "api", "graphql", "--hostname", "github.com"] for command in commands)
        return response

    def refuse(pages: list[Any], message: str) -> None:
        try:
            fetch_pages(pages)
        except ObserverError as error:
            assert message in str(error), str(error)
        else:
            raise AssertionError(f"unsafe pagination accepted: {message}")

    first, last = page(0, 100), page(100, 101)
    response = fetch_pages([first, last, first, last], expected_cursors=[None, "cursor-100", None, "cursor-100"])
    document = observation_document(response, **common)
    assert document["observation"]["unresolved_threads"] == 1
    verdict = evaluate(document, evaluated_at=common["observed_at"])
    assert verdict["verdict"] != "ready"
    assert any(reason["code"] == "unresolved_review_threads" for reason in verdict["reasons"])
    resolved_last = deepcopy(last)
    resolved_last["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["isResolved"] = True
    ready = observation_document(fetch_pages([first, resolved_last, first, resolved_last]), **common)
    assert evaluate(ready, evaluated_at=common["observed_at"])["verdict"] == "ready"
    for count in (0, 1, 100):
        fetch_pages([page(0, count, count)], expected_cursors=[None])
    maximum = [page(index, index + 100, 1000) for index in range(0, 1000, 100)]
    assert len(fetch_pages(maximum + maximum)["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]) == 1000

    for cursor in (None, "", 3, "x" * 1025):
        bad = deepcopy(first)
        bad["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["endCursor"] = cursor
        refuse([bad], "endCursor")
    for field, value, message in (
        ("totalCount", True, "totalCount"),
        ("totalCount", 1001, "totalCount"),
        ("totalCount", 100, "count"),
        ("nodes", [], "empty"),
        ("nodes", [{"id": "one", "isResolved": "false"}], "isResolved"),
    ):
        bad = deepcopy(first)
        bad["data"]["repository"]["pullRequest"]["reviewThreads"][field] = value
        refuse([bad], message)
    bad = deepcopy(first)
    bad["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["hasNextPage"] = 1
    refuse([bad], "hasNextPage")
    for field, value, message in (("totalCount", 102, "count"), ("nodes", [], "count")):
        bad = deepcopy(last)
        bad["data"]["repository"]["pullRequest"]["reviewThreads"][field] = value
        refuse([first, bad], message)
    bad = deepcopy(last)
    bad["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0]["id"] = "thread-0"
    refuse([first, bad], "duplicate")
    for field, value in (("headRefOid", "b" * 40), ("baseRefName", "other"), ("baseRefOid", "c" * 40), ("reviewDecision", "CHANGES_REQUESTED")):
        bad = deepcopy(last)
        bad["data"]["repository"]["pullRequest"][field] = value
        refuse([first, bad], "changed")
    bad = deepcopy(last)
    bad["data"]["repository"]["pullRequest"]["baseRef"]["target"]["oid"] = "d" * 40
    refuse([first, bad], "changed")
    for field, value in (("nameWithOwner", "other/project"), ("pullRequest", {"number": 18})):
        bad = deepcopy(first)
        bad["data"]["repository"][field] = value
        refuse([bad], "identity")
    refuse([first, {"errors": [{"message": "partial failure"}], **last}], "GraphQL")
    for field, value in (("id", "replacement"), ("isResolved", True)):
        bad = deepcopy(last)
        bad["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"][0][field] = value
        refuse([first, last, first, bad], "changed")
    loop_pages = [page(0, 1, 3), page(1, 2, 3)]
    loop_pages[1]["data"]["repository"]["pullRequest"]["reviewThreads"]["pageInfo"]["endCursor"] = "cursor-1"
    refuse(loop_pages, "cursor")
    refuse([page(i, i + 1, 11) for i in range(10)], "page limit")
    # The byte limit applies to all responses, including the consistency pass.
    with patch.dict(globals(), MAX_API_BYTES=len(json.dumps(first).encode()) + len(json.dumps(last).encode()) + 1):
        refuse([first, last, first], "byte limit")
    # Each request consumes the same deadline, rather than receiving a fresh 30s.
    with patch.object(time, "monotonic", side_effect=[0, 0, 31]):
        refuse([first], "time limit")
    with patch.object(time, "monotonic", side_effect=[0, 0, 1, 31]):
        refuse([first], "time limit")
    with patch.object(shutil, "which", return_value="gh"):
        for raw in (b"not-json", b"\xff", b"null"):
            with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, b"")):
                try:
                    fetch_github("example/project", 17)
                except ObserverError:
                    pass
                else:
                    raise AssertionError("invalid provider response accepted")
        with patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("gh", 1)):
            try:
                fetch_github("example/project", 17)
            except ObserverError as error:
                assert "timed out" in str(error)
            else:
                raise AssertionError("provider timeout accepted")
    for connection in ("checks", "rules"):
        bad = deepcopy(response)
        pr = bad["data"]["repository"]["pullRequest"]
        if connection == "checks":
            pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"]["contexts"]["pageInfo"]["hasNextPage"] = True
        else:
            pr["reviewDecision"] = None
            pr["baseRef"] = {"name": "main", "branchProtectionRule": None, "rules": {"nodes": [], "pageInfo": {"hasNextPage": True}}}
        try:
            observation_document(bad, **common)
        except ObserverError:
            pass
        else:
            raise AssertionError(f"truncated {connection} accepted")

    # The CLI must timestamp before fetch, so slow observations can expire.
    import io
    from contextlib import redirect_stdout
    from datetime import timedelta

    start = datetime.fromisoformat(common["observed_at"].replace("Z", "+00:00"))
    current = [start]

    class Clock(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:
            return current[0]

    def slow_fetch(*_: Any) -> Any:
        current[0] += timedelta(seconds=10)
        return page(0, 100, 100)

    output = io.StringIO()
    argv = ["github_observe.py", "--repository", "example/project", "--pull-request", "17",
            "--expected-head", "a" * 40, "--expected-base", "main", "--required-check", "tests",
            "--max-attempts", "1", "--max-observation-age-seconds", "1", "--deadline", common["deadline"]]
    with patch.object(sys, "argv", argv), patch.dict(globals(), datetime=Clock, fetch_github=slow_fetch), redirect_stdout(output):
        assert main() == 0
    expired = evaluate(json.loads(output.getvalue()), evaluated_at=current[0])
    assert expired["verdict"] == "blocked"
    assert expired["reasons"][0]["code"] == "observation_expired"
    print("GitHub review pagination self-test passed.")


def self_test() -> None:
    common = {
        "repository": "example/project",
        "pull_request": 17,
        "expected_head": "a" * 40,
        "expected_base": "main",
        "required_checks": ["tests", "policy"],
        "allow_no_required_checks": False,
        "required_review": True,
        "max_attempts": 3,
        "attempt": 1,
        "max_observation_age_seconds": 900,
        "deadline": "2026-08-30T00:00:00Z",
        "observed_at": "2026-08-29T12:00:00Z",
    }
    document = observation_document(fixture(), **common)
    closed_fixture = fixture()
    closed_fixture["data"]["repository"]["pullRequest"].update(
        state="CLOSED", merged=False
    )
    closed_fixture["data"]["repository"]["pullRequest"]["baseRef"] = {
        "name": "main",
        "target": {"__typename": "Commit", "oid": "0" * 40},
    }
    closed_document = observation_document(closed_fixture, **common)
    assert closed_document["observation"]["state"] == "closed"
    assert provider_base_commit_oid(closed_fixture) == (
        "0" * 40,
        "live_base_ref_target",
    )
    for raw_state, merged in (("CLOSED", True), ("OPEN", True), ("MERGED", False)):
        inconsistent = fixture()
        pull_request = inconsistent["data"]["repository"]["pullRequest"]
        pull_request.update(state=raw_state, merged=merged)
        try:
            observation_document(inconsistent, **common)
        except ObserverError as error:
            assert "conflicts" in str(error)
        else:
            raise AssertionError(
                f"inconsistent pull request state was accepted: {raw_state}/{merged}"
            )
        try:
            provider_base_commit_oid(inconsistent)
        except ObserverError as error:
            assert "conflicts" in str(error)
        else:
            raise AssertionError(
                f"base observation accepted inconsistent pull request state: {raw_state}/{merged}"
            )
    def base_ref_fixture() -> dict[str, Any]:
        response = fixture()
        response["data"]["repository"]["pullRequest"]["baseRef"] = {
            "name": "main",
            "target": {"__typename": "Commit", "oid": "0" * 40},
        }
        return response

    assert provider_base_commit_oid(base_ref_fixture()) == (
        "0" * 40,
        "live_base_ref_target",
    )
    missing_base_ref = base_ref_fixture()
    missing_base_ref["data"]["repository"]["pullRequest"]["baseRef"] = None
    try:
        provider_base_commit_oid(missing_base_ref)
    except ObserverError as error:
        assert "pullRequest.baseRef" in str(error)
    else:
        raise AssertionError("missing live pull request base ref was accepted")
    malformed_base_oid = base_ref_fixture()
    malformed_base_oid["data"]["repository"]["pullRequest"]["baseRef"]["target"][
        "oid"
    ] = "b" * 39
    try:
        provider_base_commit_oid(malformed_base_oid)
    except ObserverError as error:
        assert "full 40-character SHA" in str(error)
    else:
        raise AssertionError("malformed live pull request base OID was accepted")
    merged_fixture = fixture()
    merged_pr = merged_fixture["data"]["repository"]["pullRequest"]
    merged_pr["state"] = "MERGED"
    merged_pr["merged"] = True
    merged_pr["baseRefOid"] = "c" * 40
    merged_pr["baseRef"] = None
    assert provider_base_commit_oid(merged_fixture) == (
        "c" * 40,
        "pr_associated_base_ref_oid",
    )
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

    blocked_merge_fixture = json.loads(json.dumps(ready_fixture))
    blocked_merge_fixture["data"]["repository"]["pullRequest"][
        "mergeStateStatus"
    ] = "BLOCKED"
    blocked_merge_document = observation_document(blocked_merge_fixture, **common)
    blocked_merge_result = evaluate(
        blocked_merge_document, evaluated_at=common["observed_at"]
    )
    assert blocked_merge_result["verdict"] == "blocked"
    assert blocked_merge_result["reasons"][0]["code"] == "provider_merge_state_blocked"
    assert blocked_merge_document["observation"]["merge_state_status"] == "BLOCKED"

    unsupported_merge_fixture = json.loads(json.dumps(ready_fixture))
    unsupported_merge_fixture["data"]["repository"]["pullRequest"][
        "mergeStateStatus"
    ] = "FUTURE_STATE"
    try:
        observation_document(unsupported_merge_fixture, **common)
    except ObserverError as error:
        assert "mergeStateStatus is unsupported" in str(error)
    else:
        raise AssertionError("unsupported provider merge state was accepted")

    absent_review_fixture = fixture()
    absent_review_pr = absent_review_fixture["data"]["repository"]["pullRequest"]
    absent_review_pr["reviewThreads"]["nodes"] = []
    absent_review_pr["reviewDecision"] = None
    absent_review_contexts = absent_review_pr["commits"]["nodes"][0]["commit"][
        "statusCheckRollup"
    ]["contexts"]["nodes"]
    absent_review_contexts[1]["state"] = "SUCCESS"
    absent_review_document = observation_document(
        absent_review_fixture,
        **{**common, "required_review": False},
    )
    if absent_review_document["observation"]["review_decision"] != "review_required":
        raise AssertionError(
            "missing provider review decision was weakened by caller policy: "
            f"{absent_review_document['observation']['review_decision']}"
        )
    absent_review_result = evaluate(
        absent_review_document,
        evaluated_at=common["observed_at"],
    )
    assert absent_review_result["verdict"] == "pending"
    assert absent_review_result["reasons"][0]["code"] == "review_pending"

    # A null decision alone is not proof; complete provider policy can be.
    policy_fixture = json.loads(json.dumps(absent_review_fixture))
    policy_pr = policy_fixture["data"]["repository"]["pullRequest"]
    policy_pr["mergeStateStatus"] = "CLEAN"
    policy_pr["baseRef"] = {
        "name": "main",
        "branchProtectionRule": None,
        "rules": {
            "nodes": [{"type": "PULL_REQUEST", "parameters": {
                "__typename": "PullRequestParameters",
                "requiredApprovingReviewCount": 0,
                "requireCodeOwnerReview": False,
                "requireLastPushApproval": False,
                "requiredReviewers": [],
            }}],
            "pageInfo": {"hasNextPage": False},
        },
    }
    policy_document = observation_document(policy_fixture, **{**common, "required_review": False})
    assert evaluate(policy_document, evaluated_at=common["observed_at"])["verdict"] == "ready", "complete zero-review provider policy remained blocked"
    assert policy_document["observation"]["review_policy"]["base_ref"] == policy_pr["baseRef"]
    assert evaluate(observation_document(policy_fixture, **common), evaluated_at=common["observed_at"])["verdict"] == "pending"
    for decision, expected in (("REVIEW_REQUIRED", "pending"), ("CHANGES_REQUESTED", "blocked"), ("APPROVED", "ready")):
        candidate = json.loads(json.dumps(policy_fixture))
        candidate["data"]["repository"]["pullRequest"]["reviewDecision"] = decision
        result = evaluate(observation_document(candidate, **{**common, "required_review": False}), evaluated_at=common["observed_at"])
        assert result["verdict"] == expected

    # None means a deleted field in these malformed/incomplete provider fixtures.
    policy_drift = [
        (("reviewDecision",), "UNKNOWN"),
        (("reviewDecision",), None),
        (("mergeStateStatus",), "BLOCKED"),
        (("mergeStateStatus",), "UNSTABLE"),
        (("mergeStateStatus",), None),
        (("baseRef", "name"), "other"),
        (("baseRef", "branchProtectionRule"), None),
        (("baseRef", "branchProtectionRule"), {}),
        (("baseRef", "rules"), None),
        (("baseRef", "rules", "pageInfo", "hasNextPage"), True),
        (("baseRef", "rules", "pageInfo", "hasNextPage"), None),
        (("baseRef", "rules", "nodes", 0, "type"), "FUTURE_REVIEW_RULE"),
        (("baseRef", "rules", "nodes", 0, "parameters"), {}),
    ]
    parameter_path = ("baseRef", "rules", "nodes", 0, "parameters")
    for field, bad in (
        ("requiredApprovingReviewCount", 1),
        ("requiredApprovingReviewCount", False),
        ("requiredApprovingReviewCount", "0"),
        ("requireCodeOwnerReview", True),
        ("requireLastPushApproval", True),
        ("requiredReviewers", [{"minimumApprovals": 1}]),
    ):
        policy_drift.extend(((parameter_path + (field,), bad), (parameter_path + (field,), None)))
    for path, value in policy_drift:
        candidate = json.loads(json.dumps(policy_fixture))
        target = candidate["data"]["repository"]["pullRequest"]
        for part in path[:-1]:
            target = target[part]
        if value is None:
            del target[path[-1]]
        else:
            target[path[-1]] = value
        try:
            result = evaluate(observation_document(candidate, **{**common, "required_review": False}), evaluated_at=common["observed_at"])
        except ObserverError:
            continue
        assert result["verdict"] != "ready", f"policy drift accepted: {path}={value!r}"

    classic_clear = {
        "requiresApprovingReviews": False, "requiredApprovingReviewCount": 0,
        "requiresCodeOwnerReviews": False, "requireLastPushApproval": False,
    }
    policy_pr["baseRef"]["branchProtectionRule"] = classic_clear
    assert provider_review_not_required(policy_pr, "main")
    for field in classic_clear:
        for bad in (True, None):
            policy_pr["baseRef"]["branchProtectionRule"] = {**classic_clear, field: bad}
            assert not provider_review_not_required(policy_pr, "main"), field
    policy_pr["baseRef"]["branchProtectionRule"] = None
    stricter = json.loads(json.dumps(policy_pr["baseRef"]["rules"]["nodes"][0]))
    stricter["parameters"]["requiredApprovingReviewCount"] = 1
    policy_pr["baseRef"]["rules"]["nodes"].append(stricter)
    assert not provider_review_not_required(policy_pr, "main")

    for binding in ({"repository": "other/project"}, {"base_ref": "other"}, {"head_sha": "b" * 40}):
        result = evaluate(
            {**policy_document, "binding": {**policy_document["binding"], **binding}},
            evaluated_at=common["observed_at"],
        )
        assert result["verdict"] != "ready"
    assert evaluate(policy_document, evaluated_at="2026-08-29T12:16:00Z")["verdict"] != "ready"

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
    no_check_common = {
        **common,
        "required_checks": [],
        "allow_no_required_checks": True,
    }
    no_check_fixture = fixture()
    no_check_pr = no_check_fixture["data"]["repository"]["pullRequest"]
    no_check_pr["reviewThreads"]["nodes"] = []
    no_check_pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"] = None
    no_check_document = observation_document(no_check_fixture, **no_check_common)
    assert no_check_document["policy"]["allow_no_required_checks"] is True
    no_check_result = evaluate(no_check_document, evaluated_at=common["observed_at"])
    if no_check_result["verdict"] != "blocked":
        raise AssertionError(
            "caller no-check exemption was accepted without provider policy proof: "
            f"{no_check_result['verdict']}"
        )
    assert no_check_result["reasons"][0]["code"] == "required_checks_unproven"
    pagination_self_test(common)
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
        observed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        response = fetch_github(args.repository, args.pull_request)
        document = observation_document(
            response,
            repository=args.repository,
            pull_request=args.pull_request,
            expected_head=args.expected_head,
            expected_base=args.expected_base,
            required_checks=args.required_check,
            allow_no_required_checks=args.allow_no_required_checks,
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
