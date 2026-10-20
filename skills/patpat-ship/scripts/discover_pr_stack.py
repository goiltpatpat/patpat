#!/usr/bin/env python3
"""Discover one native GitHub PR stack and emit a frozen schema-v2 manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any

import github_observe
import watch_pr_stack


MAX_API_BYTES = 1024 * 1024
MAX_REF_LENGTH = 256
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
GRAPHQL_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    nameWithOwner
    pullRequest(number: $number) {
      number
      stackEntry { position }
      stack {
        id
        number
        size
        baseRefName
        entries(first: 20) {
          totalCount
          pageInfo { hasNextPage }
          nodes {
            position
            pullRequest {
              number
              repository { nameWithOwner }
              headRepository { nameWithOwner }
              state
              merged
              headRefName
              headRefOid
              baseRefName
              baseRefOid
              baseRef {
                name
                target { __typename oid }
              }
            }
          }
        }
      }
    }
  }
}
""".strip()


class DiscoveryError(ValueError):
    """Raised when GitHub cannot provide one complete linear stack snapshot."""


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise DiscoveryError(f"{field} must be an object")
    return value


def _bounded_string(value: Any, field: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise DiscoveryError(f"{field} must be a bounded non-empty string")
    return value


def _positive_integer(value: Any, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise DiscoveryError(f"{field} must be an integer from 1 to {maximum}")
    return value


def _sha(value: Any, field: str) -> str:
    result = _bounded_string(value, field, 40).lower()
    if SHA_PATTERN.fullmatch(result) is None:
        raise DiscoveryError(f"{field} must be a full 40-character commit SHA")
    return result


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def validate_policy(
    required_checks: list[str], review_policy: str
) -> tuple[list[str], bool]:
    if not isinstance(required_checks, list) or not required_checks:
        raise DiscoveryError("at least one caller-supplied --required-check is required")
    if len(required_checks) > github_observe.MAX_CHECKS:
        raise DiscoveryError("required checks exceed the bounded 100-name limit")
    normalized = [
        _bounded_string(name, f"required-check[{index}]", github_observe.MAX_NAME_LENGTH)
        for index, name in enumerate(required_checks)
    ]
    if len(normalized) != len(set(normalized)):
        raise DiscoveryError("required checks must be unique")
    if review_policy not in {"required", "not-required"}:
        raise DiscoveryError("--review-policy must be required or not-required")
    return normalized, review_policy == "required"


def _base_commit(pull_request: dict[str, Any], *, label: str) -> str:
    base_name = _bounded_string(
        pull_request.get("baseRefName"), f"{label}.baseRefName", MAX_REF_LENGTH
    )
    merged = pull_request.get("merged")
    if not isinstance(merged, bool):
        raise DiscoveryError(f"{label}.merged must be a boolean")
    if merged:
        return _sha(pull_request.get("baseRefOid"), f"{label}.baseRefOid")

    base_ref = _mapping(pull_request.get("baseRef"), f"{label}.baseRef")
    if (
        _bounded_string(base_ref.get("name"), f"{label}.baseRef.name", MAX_REF_LENGTH)
        != base_name
    ):
        raise DiscoveryError(f"{label}.baseRef name does not match baseRefName")
    target = _mapping(base_ref.get("target"), f"{label}.baseRef.target")
    if target.get("__typename") != "Commit":
        raise DiscoveryError(f"{label}.baseRef target must be a commit")
    return _sha(target.get("oid"), f"{label}.baseRef.target.oid")


def discover_manifest(
    response: Any,
    *,
    repository: str,
    anchor_pull_request: int,
    required_checks: list[str],
    review_policy: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate native stack topology and bind it to the watcher's existing manifest."""
    checks, require_review = validate_policy(required_checks, review_policy)
    root = _mapping(response, "response")
    if root.get("errors"):
        raise DiscoveryError("GitHub GraphQL returned errors")
    data = _mapping(root.get("data"), "data")
    provider_repository = _mapping(data.get("repository"), "repository")
    if (
        _bounded_string(provider_repository.get("nameWithOwner"), "repository.nameWithOwner")
        != repository
    ):
        raise DiscoveryError("GitHub returned a different repository")
    anchor = _mapping(provider_repository.get("pullRequest"), "repository.pullRequest")
    if _positive_integer(anchor.get("number"), "pullRequest.number", 1_000_000) != anchor_pull_request:
        raise DiscoveryError("GitHub returned a different anchor pull request")
    anchor_entry = _mapping(anchor.get("stackEntry"), "pullRequest.stackEntry")
    anchor_position = _positive_integer(
        anchor_entry.get("position"), "pullRequest.stackEntry.position", watch_pr_stack.MAX_STACK_SIZE
    )
    stack = _mapping(anchor.get("stack"), "pullRequest.stack")
    stack_id = _bounded_string(stack.get("id"), "pullRequest.stack.id")
    stack_number = _positive_integer(stack.get("number"), "pullRequest.stack.number", 1_000_000)
    stack_size = _positive_integer(
        stack.get("size"), "pullRequest.stack.size", watch_pr_stack.MAX_STACK_SIZE
    )
    trunk_ref = _bounded_string(
        stack.get("baseRefName"), "pullRequest.stack.baseRefName", MAX_REF_LENGTH
    )

    entries_connection = _mapping(stack.get("entries"), "pullRequest.stack.entries")
    page_info = _mapping(entries_connection.get("pageInfo"), "stack.entries.pageInfo")
    if page_info.get("hasNextPage") is not False:
        raise DiscoveryError("stack entries are truncated or exceed the bounded page")
    total_count = entries_connection.get("totalCount")
    if type(total_count) is not int or total_count != stack_size:
        raise DiscoveryError("stack size does not match its entry count")
    raw_entries = entries_connection.get("nodes")
    if not isinstance(raw_entries, list) or len(raw_entries) != stack_size:
        raise DiscoveryError("stack entries are incomplete")

    rows: list[dict[str, Any]] = []
    seen_numbers: set[int] = set()
    seen_positions: set[int] = set()
    seen_head_refs: set[str] = set()
    for index, raw_entry in enumerate(raw_entries):
        label = f"stack.entries[{index}]"
        entry = _mapping(raw_entry, label)
        position = _positive_integer(entry.get("position"), f"{label}.position", stack_size)
        if position in seen_positions:
            raise DiscoveryError("stack positions must be unique")
        seen_positions.add(position)
        pull_request = _mapping(entry.get("pullRequest"), f"{label}.pullRequest")
        number = _positive_integer(
            pull_request.get("number"), f"{label}.pullRequest.number", 1_000_000
        )
        if number in seen_numbers:
            raise DiscoveryError("stack pull requests must be unique")
        seen_numbers.add(number)
        member_repository = _mapping(
            pull_request.get("repository"), f"{label}.pullRequest.repository"
        )
        if _bounded_string(
            member_repository.get("nameWithOwner"),
            f"{label}.pullRequest.repository.nameWithOwner",
        ) != repository:
            raise DiscoveryError("stack contains a pull request from a different repository")
        head_repository = _mapping(
            pull_request.get("headRepository"), f"{label}.pullRequest.headRepository"
        )
        if _bounded_string(
            head_repository.get("nameWithOwner"),
            f"{label}.pullRequest.headRepository.nameWithOwner",
        ) != repository:
            raise DiscoveryError("cross-repository stack heads are unsupported")

        state = _bounded_string(pull_request.get("state"), f"{label}.pullRequest.state").upper()
        merged = pull_request.get("merged")
        if not isinstance(merged, bool):
            raise DiscoveryError(f"{label}.pullRequest.merged must be a boolean")
        if (
            state not in {"OPEN", "CLOSED"}
            or (state == "OPEN" and merged)
            or (state == "CLOSED" and not merged)
        ):
            raise DiscoveryError(
                "stack entries must be open or merged; closed unmerged entries are unsupported"
            )

        head_ref = _bounded_string(
            pull_request.get("headRefName"), f"{label}.pullRequest.headRefName", MAX_REF_LENGTH
        )
        if head_ref in seen_head_refs:
            raise DiscoveryError("stack head branches must be unique")
        seen_head_refs.add(head_ref)
        head_sha = _sha(pull_request.get("headRefOid"), f"{label}.pullRequest.headRefOid")
        base_ref = _bounded_string(
            pull_request.get("baseRefName"), f"{label}.pullRequest.baseRefName", MAX_REF_LENGTH
        )
        base_sha = _base_commit(pull_request, label=f"{label}.pullRequest")
        rows.append(
            {
                "position": position,
                "pull_request": number,
                "head_ref": head_ref,
                "head_sha": head_sha,
                "base_ref": base_ref,
                "base_sha": base_sha,
                "state": "merged" if merged else "open",
            }
        )

    rows.sort(key=lambda row: row["position"])
    if [row["position"] for row in rows] != list(range(1, stack_size + 1)):
        raise DiscoveryError("stack positions must be contiguous from 1 to size")
    anchor_rows = [row for row in rows if row["pull_request"] == anchor_pull_request]
    if len(anchor_rows) != 1 or anchor_rows[0]["position"] != anchor_position:
        raise DiscoveryError("anchor stack position does not match the returned entries")

    open_rows = [row for row in rows if row["state"] == "open"]
    if not open_rows:
        raise DiscoveryError("all stack pull requests are merged; no watch manifest is needed")
    first_open_position = open_rows[0]["position"]
    seen_open = False
    for row in rows:
        if row["state"] == "open":
            seen_open = True
        elif seen_open:
            raise DiscoveryError("merged stack pull requests must form a prefix before open entries")

    targets: list[dict[str, Any]] = []
    for index, row in enumerate(open_rows):
        expected_base = trunk_ref if index == 0 else open_rows[index - 1]["head_ref"]
        expected_base_sha = row["base_sha"]
        if row["base_ref"] != expected_base:
            raise DiscoveryError(
                f"PR {row['pull_request']} does not target the preceding stack branch"
            )
        if index > 0 and expected_base_sha != open_rows[index - 1]["head_sha"]:
            raise DiscoveryError(
                f"PR {row['pull_request']} base SHA does not match the preceding stack head"
            )
        targets.append(
            {
                "pull_request": row["pull_request"],
                "expected_head": row["head_sha"],
                "expected_base": row["base_ref"],
                "expected_base_sha": expected_base_sha,
                "required_checks": checks,
                "require_review": require_review,
            }
        )

    manifest = {
        "schema_version": watch_pr_stack.SCHEMA_VERSION,
        "repository": repository,
        "pull_requests": targets,
    }
    watch_pr_stack.validate_manifest(manifest)
    topology = {
        "provider": "github.com",
        "repository": repository,
        "anchor_pull_request": anchor_pull_request,
        "stack": {
            "id": stack_id,
            "number": stack_number,
            "size": stack_size,
            "base_ref": trunk_ref,
        },
        "entries": rows,
        "watch_scope": {
            "active_from_position": first_open_position,
            "pull_requests": [row["pull_request"] for row in open_rows],
        },
    }
    receipt = {
        "kind": "patpat.pr_stack_discovery",
        "schema_version": 1,
        "observed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "topology_sha256": _canonical_sha256(topology),
        "manifest_sha256": watch_pr_stack._manifest_sha256(manifest),
        **topology,
    }
    return manifest, receipt


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
        raise DiscoveryError("GitHub CLI is required")
    try:
        result = subprocess.run(
            github_command(executable, repository, pull_request),
            check=False,
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DiscoveryError(f"GitHub stack discovery failed: {error}") from error
    if result.returncode != 0:
        raise DiscoveryError(f"GitHub CLI exited with status {result.returncode}")
    if len(result.stdout) > MAX_API_BYTES:
        raise DiscoveryError("GitHub stack response exceeds the byte limit")
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise DiscoveryError("GitHub returned invalid bounded JSON") from error


def _fixture_response() -> dict[str, Any]:
    first_head = "a" * 40
    second_head = "b" * 40
    return {
        "data": {
            "repository": {
                "nameWithOwner": "example/project",
                "pullRequest": {
                    "number": 18,
                    "stackEntry": {"position": 2},
                    "stack": {
                        "id": "STACK_node_id",
                        "number": 7,
                        "size": 2,
                        "baseRefName": "main",
                        "entries": {
                            "totalCount": 2,
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                {
                                    "position": 1,
                                    "pullRequest": {
                                        "number": 17,
                                        "repository": {"nameWithOwner": "example/project"},
                                        "headRepository": {"nameWithOwner": "example/project"},
                                        "state": "OPEN",
                                        "merged": False,
                                        "headRefName": "feature/17",
                                        "headRefOid": first_head,
                                        "baseRefName": "main",
                                        "baseRefOid": "0" * 40,
                                        "baseRef": {
                                            "name": "main",
                                            "target": {"__typename": "Commit", "oid": "0" * 40},
                                        },
                                    },
                                },
                                {
                                    "position": 2,
                                    "pullRequest": {
                                        "number": 18,
                                        "repository": {"nameWithOwner": "example/project"},
                                        "headRepository": {"nameWithOwner": "example/project"},
                                        "state": "OPEN",
                                        "merged": False,
                                        "headRefName": "feature/18",
                                        "headRefOid": second_head,
                                        "baseRefName": "feature/17",
                                        "baseRefOid": first_head,
                                        "baseRef": {
                                            "name": "feature/17",
                                            "target": {"__typename": "Commit", "oid": first_head},
                                        },
                                    },
                                },
                            ],
                        },
                    },
                },
            }
        }
    }


def self_test() -> None:
    checks = ["build", "lint"]
    manifest, receipt = discover_manifest(
        _fixture_response(),
        repository="example/project",
        anchor_pull_request=18,
        required_checks=checks,
        review_policy="required",
    )
    assert [entry["pull_request"] for entry in manifest["pull_requests"]] == [17, 18]
    assert manifest["pull_requests"][1]["expected_base_sha"] == "a" * 40
    assert all(entry["required_checks"] == checks for entry in manifest["pull_requests"])
    assert watch_pr_stack.validate_manifest(manifest)[0] == "example/project"
    assert receipt["manifest_sha256"] == watch_pr_stack._manifest_sha256(manifest)
    assert receipt["topology_sha256"] == _canonical_sha256(
        {
            key: value
            for key, value in receipt.items()
            if key
            not in {
                "kind",
                "schema_version",
                "observed_at",
                "topology_sha256",
                "manifest_sha256",
            }
        }
    )

    def entries(response: dict[str, Any]) -> list[dict[str, Any]]:
        return response["data"]["repository"]["pullRequest"]["stack"]["entries"]["nodes"]

    def member(response: dict[str, Any], index: int) -> dict[str, Any]:
        return entries(response)[index]["pullRequest"]

    reversed_response = _fixture_response()
    entries(reversed_response).reverse()
    reversed_manifest, _ = discover_manifest(
        reversed_response,
        repository="example/project",
        anchor_pull_request=18,
        required_checks=checks,
        review_policy="required",
    )
    assert reversed_manifest == manifest

    rebased_suffix_response = _fixture_response()
    second_entry = entries(rebased_suffix_response)[1]["pullRequest"]
    second_entry.update(
        headRefOid="d" * 40,
        baseRefName="main",
        baseRefOid="c" * 40,
        baseRef={
            "name": "main",
            "target": {"__typename": "Commit", "oid": "c" * 40},
        },
    )
    first_pr = entries(rebased_suffix_response)[0]["pullRequest"]
    first_pr.update(state="CLOSED", merged=True, baseRef=None)
    rebased_manifest, rebased_receipt = discover_manifest(
        rebased_suffix_response,
        repository="example/project",
        anchor_pull_request=18,
        required_checks=checks,
        review_policy="required",
    )
    assert [entry["pull_request"] for entry in rebased_manifest["pull_requests"]] == [18]
    assert rebased_manifest["pull_requests"][0]["expected_base"] == "main"
    assert rebased_manifest["pull_requests"][0]["expected_base_sha"] == "c" * 40
    assert [entry["state"] for entry in rebased_receipt["entries"]] == ["merged", "open"]
    assert rebased_receipt["watch_scope"]["active_from_position"] == 2
    all_merged_response = _fixture_response()
    all_merged_root = all_merged_response["data"]["repository"]["pullRequest"]
    all_merged_root.update(number=17, stackEntry={"position": 1})
    all_merged_stack = all_merged_root["stack"]
    all_merged_stack.update(size=1)
    all_merged_entries = all_merged_stack["entries"]
    all_merged_entries.update(totalCount=1, nodes=[all_merged_entries["nodes"][0]])
    all_merged_entries["nodes"][0]["pullRequest"].update(
        state="CLOSED", merged=True, baseRef=None
    )
    try:
        discover_manifest(
            all_merged_response,
            repository="example/project",
            anchor_pull_request=17,
            required_checks=checks,
            review_policy="required",
        )
    except DiscoveryError as error:
        assert "all stack pull requests are merged" in str(error)
    else:
        raise AssertionError("all-merged stack must not emit a watch manifest")

    def rejected(change: Any, expected: str) -> None:
        response = _fixture_response()
        change(response)
        try:
            discover_manifest(
                response,
                repository="example/project",
                anchor_pull_request=18,
                required_checks=checks,
                review_policy="required",
            )
        except DiscoveryError as error:
            if expected not in str(error):
                raise AssertionError(f"expected {expected!r}, got {str(error)!r}") from error
        else:
            raise AssertionError(f"expected discovery to reject {expected!r}")

    rejected(
        lambda value: value["data"]["repository"]["pullRequest"].update(stack=None),
        "must be an object",
    )
    rejected(lambda value: value.update(errors=[{"message": "partial"}]), "returned errors")
    rejected(
        lambda value: value["data"]["repository"]["pullRequest"]["stack"]["entries"]["pageInfo"].update(hasNextPage=True),
        "truncated",
    )
    rejected(
        lambda value: value["data"]["repository"]["pullRequest"]["stack"].update(size=21),
        "integer from 1 to 20",
    )
    rejected(lambda value: entries(value)[1].update(position=1), "positions must be unique")
    rejected(lambda value: entries(value)[1].update(position=3), "integer from 1 to 2")
    rejected(lambda value: member(value, 1).update(repository={"nameWithOwner": "other/repo"}), "different repository")
    rejected(
        lambda value: member(value, 1).update(headRepository={"nameWithOwner": "other/repo"}),
        "cross-repository",
    )
    rejected(
        lambda value: value["data"]["repository"].update(nameWithOwner="other/repo"),
        "different repository",
    )
    rejected(lambda value: entries(value)[1]["pullRequest"].update(number=17), "must be unique")
    rejected(
        lambda value: (
            member(value, 1).update(baseRefName="main"),
            member(value, 1)["baseRef"].update(name="main"),
        ),
        "preceding stack branch",
    )
    rejected(
        lambda value: member(value, 1)["baseRef"]["target"].update(oid="c" * 40),
        "preceding stack head",
    )
    rejected(lambda value: member(value, 0).update(headRefOid="short"), "full 40-character")
    rejected(lambda value: member(value, 0)["baseRef"]["target"].update(__typename="Tree"), "must be a commit")
    rejected(lambda value: member(value, 1).update(state="CLOSED"), "closed unmerged")
    rejected(
        lambda value: member(value, 1).update(state="CLOSED", merged=True, baseRef=None),
        "must form a prefix",
    )
    rejected(lambda value: member(value, 1).update(headRefName="feature/17"), "head branches must be unique")
    rejected(lambda value: value["data"]["repository"]["pullRequest"].update(number=19), "different anchor")
    rejected(
        lambda value: value["data"]["repository"]["pullRequest"]["stackEntry"].update(position=1),
        "anchor stack position",
    )

    try:
        discover_manifest(
            _fixture_response(),
            repository="example/project",
            anchor_pull_request=18,
            required_checks=[],
            review_policy="required",
        )
    except DiscoveryError as error:
        assert "caller-supplied --required-check" in str(error)
    else:
        raise AssertionError("missing required-check policy must fail closed")

    command = github_command("gh", "example/project", 18)
    assert command[1:5] == ["api", "graphql", "--hostname", "github.com"]
    assert command[-1] == f"query={GRAPHQL_QUERY}"
    assert re.match(r"^query\b", GRAPHQL_QUERY) is not None
    assert re.search(r"\bmutation\b", GRAPHQL_QUERY) is None


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("--repository", help="GitHub repository in OWNER/REPO form")
    command.add_argument("--pull-request", type=int, help="anchor PR within a native stack")
    command.add_argument(
        "--required-check",
        action="append",
        default=[],
        help="caller-supplied required check from verified repository policy; repeat for each name",
    )
    command.add_argument(
        "--review-policy",
        choices=("required", "not-required"),
        help="caller-supplied review policy applied to every stack PR; not verified here",
    )
    command.add_argument("--self-test", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    command = parser()
    args = command.parse_args(argv if argv is not None else sys.argv[1:])
    if args.self_test:
        self_test()
        print("GitHub PR stack discovery self-test passed.")
        return 0
    if github_observe.REPOSITORY.fullmatch(args.repository or "") is None:
        command.error("--repository must be OWNER/REPO")
    if (
        isinstance(args.pull_request, bool)
        or not isinstance(args.pull_request, int)
        or not 1 <= args.pull_request <= 1_000_000
    ):
        command.error("--pull-request must be an integer from 1 to 1000000")
    try:
        validate_policy(args.required_check, args.review_policy)
        response = fetch_github(args.repository, args.pull_request)
        manifest, receipt = discover_manifest(
            response,
            repository=args.repository,
            anchor_pull_request=args.pull_request,
            required_checks=args.required_check,
            review_policy=args.review_policy,
        )
        print(json.dumps(manifest, sort_keys=True, indent=2))
        print(json.dumps(receipt, sort_keys=True), file=sys.stderr)
        return 0
    except (DiscoveryError, watch_pr_stack.WatchError) as error:
        print(f"GitHub PR stack discovery stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
