#!/usr/bin/env python3
"""Verify the presence, shape, and passing verdict of a Patpat review receipt."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REVIEW_RECEIPT_RELATIVE = ".patpat/review-receipt.json"
MAX_RECEIPT_BYTES = 128 * 1024
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


class ReviewVerificationError(ValueError):
    """The review receipt cannot establish delivery-review-cleared."""


def verify_review_data(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ReviewVerificationError(f"review receipt at {path} must be a JSON object")
    if data.get("kind") not in {"patpat-review-receipt", "patpat.review.verdict"}:
        raise ReviewVerificationError(f"review receipt at {path} has unsupported kind: {data.get('kind')!r}")
    if "schema_version" not in data or type(data["schema_version"]) is not int:
        raise ReviewVerificationError(f"review receipt at {path} missing valid integer schema_version")
    verdict = data.get("verdict")
    if verdict != "pass":
        raise ReviewVerificationError(f"review receipt at {path} has non-cleared verdict: {verdict!r} (expected 'pass')")
    actor = data.get("actor")
    if not isinstance(actor, str) or not actor.strip():
        raise ReviewVerificationError(f"review receipt at {path} missing non-empty actor")
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise ReviewVerificationError(f"review receipt at {path} missing non-empty summary")
    head_sha = data.get("head_sha") or data.get("head")
    if not isinstance(head_sha, str) or SHA_PATTERN.fullmatch(head_sha.strip()) is None:
        raise ReviewVerificationError(f"review receipt at {path} missing valid hexadecimal head_sha")
    return data


def _verify_git_head_binding(root: Path, data: dict[str, Any]) -> None:
    head_sha = data.get("head_sha") or data.get("head")
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            actual_head = completed.stdout.strip()
            if actual_head and actual_head.lower() != str(head_sha).lower():
                raise ReviewVerificationError(
                    f"receipt head_sha {head_sha!r} does not match workspace git HEAD {actual_head!r}"
                )
    except OSError:
        pass


def verify_review(receipt_path: Path, root: Path | None = None) -> dict[str, Any]:
    if not receipt_path.is_file():
        raise ReviewVerificationError(f"missing review receipt: {receipt_path}")
    raw = receipt_path.read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise ReviewVerificationError(f"review receipt exceeds {MAX_RECEIPT_BYTES} byte limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewVerificationError(f"invalid JSON in review receipt: {error}") from error
    verified_data = verify_review_data(data, receipt_path)
    if root is not None:
        _verify_git_head_binding(root, verified_data)
    return verified_data


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1. Missing receipt must fail
        missing = root / "missing.json"
        try:
            verify_review(missing)
        except ReviewVerificationError:
            pass
        else:
            raise AssertionError("missing review receipt was accepted")

        # 2. Invalid JSON must fail
        bad_json = root / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        try:
            verify_review(bad_json)
        except ReviewVerificationError:
            pass
        else:
            raise AssertionError("invalid JSON review receipt was accepted")

        # 3. Non-pass verdict must fail
        non_pass = root / "changes.json"
        non_pass.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "changes-required",
                "actor": "reviewer",
                "summary": "needs fix",
                "head_sha": "a" * 40,
            }),
            encoding="utf-8",
        )
        try:
            verify_review(non_pass)
        except ReviewVerificationError:
            pass
        else:
            raise AssertionError("non-pass review verdict was accepted")

        # 4. Missing actor / summary must fail
        missing_fields = root / "no_actor.json"
        missing_fields.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "head_sha": "a" * 40,
            }),
            encoding="utf-8",
        )
        try:
            verify_review(missing_fields)
        except ReviewVerificationError:
            pass
        else:
            raise AssertionError("review receipt missing actor was accepted")

        # 5. Valid pass receipt must succeed
        valid = root / "valid.json"
        valid.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "actor": "independent-reviewer",
                "summary": "clean verification",
                "head_sha": "a" * 40,
            }),
            encoding="utf-8",
        )
        res = verify_review(valid)
        if res["verdict"] != "pass":
            raise AssertionError("valid review receipt failed verification")

    print("Review verifier self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="workspace root (default: current directory)")
    parser.add_argument("--receipt", type=Path, help="direct path to review receipt JSON")
    parser.add_argument("--self-test", action="store_true", help="run self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    receipt_path = args.receipt or (root / REVIEW_RECEIPT_RELATIVE)
    try:
        data = verify_review(receipt_path, root=root)
        print(f"Review cleared: {receipt_path} (actor={data['actor']}, verdict={data['verdict']})")
        return 0
    except (ReviewVerificationError, OSError) as error:
        print(f"review verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
