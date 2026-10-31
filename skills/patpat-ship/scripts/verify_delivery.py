#!/usr/bin/env python3
"""Verify the presence, shape, and readiness of a Patpat delivery receipt."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

DELIVERY_RECEIPT_RELATIVE = ".patpat/delivery-receipt.json"
MAX_RECEIPT_BYTES = 128 * 1024
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")


class DeliveryVerificationError(ValueError):
    """The delivery receipt cannot establish delivery-pr-ready."""


def verify_delivery_data(data: Any, path: Path) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DeliveryVerificationError(f"delivery receipt at {path} must be a JSON object")
    if data.get("kind") not in {"patpat-delivery-receipt", "patpat.delivery.verdict"}:
        raise DeliveryVerificationError(f"delivery receipt at {path} has unsupported kind: {data.get('kind')!r}")
    if "schema_version" not in data or type(data["schema_version"]) is not int:
        raise DeliveryVerificationError(f"delivery receipt at {path} missing valid integer schema_version")
    status = data.get("status")
    if status not in {"ready", "merged"}:
        raise DeliveryVerificationError(f"delivery receipt at {path} has invalid status: {status!r} (expected 'ready' or 'merged')")
    pr_number = data.get("pr_number") or data.get("pull_request")
    if type(pr_number) is not int or pr_number <= 0:
        raise DeliveryVerificationError(f"delivery receipt at {path} missing positive integer pr_number")
    pr_url = data.get("pr_url") or data.get("url")
    if not isinstance(pr_url, str) or not pr_url.strip():
        raise DeliveryVerificationError(f"delivery receipt at {path} missing non-empty pr_url")
    head_sha = data.get("head_sha") or data.get("head")
    if not isinstance(head_sha, str) or SHA_PATTERN.fullmatch(head_sha.strip()) is None:
        raise DeliveryVerificationError(f"delivery receipt at {path} missing valid hexadecimal head_sha")
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
                raise DeliveryVerificationError(
                    f"delivery receipt head_sha {head_sha!r} does not match workspace git HEAD {actual_head!r}"
                )
    except OSError:
        pass


def verify_delivery(receipt_path: Path, root: Path | None = None) -> dict[str, Any]:
    if not receipt_path.is_file():
        raise DeliveryVerificationError(f"missing delivery receipt: {receipt_path}")
    raw = receipt_path.read_bytes()
    if len(raw) > MAX_RECEIPT_BYTES:
        raise DeliveryVerificationError(f"delivery receipt exceeds {MAX_RECEIPT_BYTES} byte limit")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeliveryVerificationError(f"invalid JSON in delivery receipt: {error}") from error
    verified_data = verify_delivery_data(data, receipt_path)
    if root is not None:
        _verify_git_head_binding(root, verified_data)
    return verified_data


def self_test() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # 1. Missing receipt must fail
        missing = root / "missing.json"
        try:
            verify_delivery(missing)
        except DeliveryVerificationError:
            pass
        else:
            raise AssertionError("missing delivery receipt was accepted")

        # 2. Invalid JSON must fail
        bad_json = root / "bad.json"
        bad_json.write_text("{broken", encoding="utf-8")
        try:
            verify_delivery(bad_json)
        except DeliveryVerificationError:
            pass
        else:
            raise AssertionError("invalid JSON delivery receipt was accepted")

        # 3. Invalid status must fail
        bad_status = root / "bad_status.json"
        bad_status.write_text(
            json.dumps({
                "kind": "patpat-delivery-receipt",
                "schema_version": 1,
                "status": "pending",
                "pr_number": 114,
                "pr_url": "https://github.com/example/repo/pull/114",
                "head_sha": "b" * 40,
            }),
            encoding="utf-8",
        )
        try:
            verify_delivery(bad_status)
        except DeliveryVerificationError:
            pass
        else:
            raise AssertionError("pending delivery status was accepted as ready")

        # 4. Missing pr_number must fail
        missing_pr = root / "no_pr.json"
        missing_pr.write_text(
            json.dumps({
                "kind": "patpat-delivery-receipt",
                "schema_version": 1,
                "status": "ready",
                "pr_url": "https://github.com/example/repo/pull/114",
                "head_sha": "b" * 40,
            }),
            encoding="utf-8",
        )
        try:
            verify_delivery(missing_pr)
        except DeliveryVerificationError:
            pass
        else:
            raise AssertionError("delivery receipt missing pr_number was accepted")

        # 5. Valid ready receipt must succeed
        valid = root / "valid.json"
        valid.write_text(
            json.dumps({
                "kind": "patpat-delivery-receipt",
                "schema_version": 1,
                "status": "ready",
                "pr_number": 114,
                "pr_url": "https://github.com/example/repo/pull/114",
                "head_sha": "b" * 40,
            }),
            encoding="utf-8",
        )
        res = verify_delivery(valid)
        if res["status"] != "ready":
            raise AssertionError("valid delivery receipt failed verification")

    print("Delivery verifier self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="workspace root (default: current directory)")
    parser.add_argument("--receipt", type=Path, help="direct path to delivery receipt JSON")
    parser.add_argument("--self-test", action="store_true", help="run self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    receipt_path = args.receipt or (root / DELIVERY_RECEIPT_RELATIVE)
    try:
        data = verify_delivery(receipt_path, root=root)
        print(f"Delivery PR ready: PR #{data.get('pr_number') or data.get('pull_request')} ({data['status']}) at {data.get('pr_url') or data.get('url')}")
        return 0
    except (DeliveryVerificationError, OSError) as error:
        print(f"delivery verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
