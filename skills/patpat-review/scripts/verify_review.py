#!/usr/bin/env python3
"""Verify the presence, shape, and passing verdict of a Patpat review receipt."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REVIEW_RECEIPT_RELATIVE = ".patpat/review-receipt.json"
GIT_DIR_REVIEW_RECEIPT_RELATIVE = Path("patpat") / "review-receipt.json"
MAX_RECEIPT_BYTES = 128 * 1024
SHA_PATTERN = re.compile(r"^[0-9a-f]{40,64}$")
FLOOR_GUARD_CATEGORIES = frozenset({
    "test-skipping-annotation",
    "test-skipping-call",
    "linter-suppression",
    "broad-exception-swallowing",
    "stray-scratch-artifact",
})


class ReviewVerificationError(ValueError):
    """The review receipt cannot establish delivery-review-cleared."""


def resolve_git_dir(root: Path) -> Path | None:
    """Resolve the git metadata directory for root, or None if not a git repo."""
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if completed.returncode != 0:
        return None
    raw = completed.stdout.strip()
    if not raw:
        return None
    git_dir = Path(raw)
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    return git_dir


def default_review_receipt_path(root: Path) -> Path:
    """Resolve default review receipt path under git metadata (non-dirtying) with legacy fallback."""
    resolved_root = root.resolve()
    legacy = resolved_root / REVIEW_RECEIPT_RELATIVE
    git_dir = resolve_git_dir(resolved_root)
    if git_dir is not None:
        primary = git_dir / GIT_DIR_REVIEW_RECEIPT_RELATIVE
        if primary.is_file():
            return primary
        if legacy.is_file():
            return legacy
        return primary
    if legacy.is_file():
        return legacy
    root_hash = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / "patpat" / root_hash / "review-receipt.json"


def _load_unslop_module() -> Any | None:
    script = Path(__file__).resolve().parents[2] / "patpat-unslop" / "scripts" / "unslop_ast_check.py"
    if not script.is_file():
        return None
    mod_name = "_patpat_unslop_ast_check"
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(mod_name, script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except (ImportError, SyntaxError, OSError) as error:
        sys.modules.pop(mod_name, None)
        raise ReviewVerificationError(
            f"Floor Guard unavailable: failed to import {script}: {error}"
        ) from error
    return module


def _collect_review_diff(root: Path, base_ref: str | None = None) -> tuple[str, list[str]]:
    """Collect unified diff text and untracked relative file paths for Floor Guard checking."""
    diff_chunks: list[str] = []

    def _run_git(*args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except (subprocess.SubprocessError, OSError):
            return None

    if base_ref:
        res = _run_git("diff", f"{base_ref}...HEAD")
        if res is not None and res.returncode == 0 and res.stdout:
            diff_chunks.append(res.stdout)
    else:
        head_res = _run_git("rev-parse", "HEAD")
        head_sha = head_res.stdout.strip() if head_res is not None and head_res.returncode == 0 else ""
        merge_base_sha: str | None = None
        for candidate in ("main", "master", "origin/main", "origin/master"):
            mb = _run_git("merge-base", "HEAD", candidate)
            if mb is not None and mb.returncode == 0:
                candidate_sha = mb.stdout.strip()
                if candidate_sha and candidate_sha != head_sha:
                    merge_base_sha = candidate_sha
                    break
        if merge_base_sha is not None:
            res = _run_git("diff", f"{merge_base_sha}..HEAD")
        else:
            has_parent = _run_git("rev-parse", "--verify", "HEAD~1")
            if has_parent is not None and has_parent.returncode == 0:
                res = _run_git("diff", "HEAD~1..HEAD")
            else:
                res = _run_git("show", "--format=", "HEAD")
        if res is not None and res.returncode == 0 and res.stdout:
            diff_chunks.append(res.stdout)

    wt = _run_git("diff", "HEAD")
    if wt is not None and wt.returncode == 0 and wt.stdout:
        diff_chunks.append(wt.stdout)

    untracked_paths: list[str] = []
    ut = _run_git("ls-files", "--others", "--exclude-standard")
    if ut is not None and ut.returncode == 0 and ut.stdout:
        untracked_paths = [line.strip() for line in ut.stdout.splitlines() if line.strip()]

    return "\n".join(diff_chunks), untracked_paths


def check_floor_guard(root: Path, base_ref: str | None = None) -> list[str]:
    """Run unslop Floor Guard checks on candidate diff and untracked files."""
    unslop = _load_unslop_module()
    if unslop is None:
        raise ReviewVerificationError(
            "Floor Guard unavailable: failed to load unslop_ast_check.py"
        )
    diff_text, untracked_paths = _collect_review_diff(root, base_ref=base_ref)
    violations: list[Any] = []
    if diff_text.strip():
        violations.extend(unslop.check_diff_content(diff_text, root=root))
    if untracked_paths:
        violations.extend(unslop.check_stray_scratch_paths(untracked_paths))
    floor_hits = [v for v in violations if v.category in FLOOR_GUARD_CATEGORIES]
    seen: set[str] = set()
    diagnostics: list[str] = []
    for v in floor_hits:
        diag = v.format_diagnostic()
        if diag not in seen:
            seen.add(diag)
            diagnostics.append(diag)
    return diagnostics


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
    except (subprocess.SubprocessError, OSError) as error:
        raise ReviewVerificationError(f"failed to establish git HEAD in {root}: {error}") from error

    if completed.returncode != 0:
        err = completed.stderr.strip() or f"exit code {completed.returncode}"
        raise ReviewVerificationError(f"failed to establish git HEAD in {root}: {err}")

    actual_head = completed.stdout.strip()
    if not actual_head:
        raise ReviewVerificationError(f"failed to establish git HEAD in {root}: empty git rev-parse output")

    if actual_head.lower() != str(head_sha).lower():
        raise ReviewVerificationError(
            f"receipt head_sha {head_sha!r} does not match workspace git HEAD {actual_head!r}"
        )


def verify_review(
    receipt_path: Path,
    root: Path | None = None,
    *,
    check_diff: bool = True,
    base_ref: str | None = None,
) -> dict[str, Any]:
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
        if check_diff:
            floor_violations = check_floor_guard(root, base_ref=base_ref)
            if floor_violations:
                details = "\n".join(f"  - {item}" for item in floor_violations)
                raise ReviewVerificationError(f"Floor Guard violations detected in review diff:\n{details}")
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

        # 6. Non-git directory with root specified must fail closed
        try:
            verify_review(valid, root=root)
        except ReviewVerificationError:
            pass
        else:
            raise AssertionError("review verification did not fail closed on non-git root")

        # 7. Non-git default receipt path falls back to temp dir when no legacy receipt exists
        non_git_default = default_review_receipt_path(root)
        if non_git_default.parent.parent != Path(tempfile.gettempdir()) / "patpat":
            raise AssertionError(f"expected temp-dir fallback for non-git root, got {non_git_default}")

    # 8. Git repo: default receipt lives under <git-dir>/patpat/review-receipt.json without dirtying worktree
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)

        def git(*args: str) -> str:
            res = subprocess.run(
                ["git", *args],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )
            return res.stdout.strip()

        git("init", "-q")
        git("config", "user.name", "Test")
        git("config", "user.email", "test@example.invalid")
        (repo / "clean.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
        git("add", "clean.py")
        git("commit", "-qm", "initial clean commit")
        head_sha = git("rev-parse", "HEAD")

        expected_path = default_review_receipt_path(repo)
        git_dir = resolve_git_dir(repo)
        if git_dir is None or expected_path != git_dir / GIT_DIR_REVIEW_RECEIPT_RELATIVE:
            raise AssertionError(f"expected git-dir receipt path, got {expected_path}")

        expected_path.parent.mkdir(parents=True, exist_ok=True)
        expected_path.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "actor": "independent-reviewer",
                "summary": "clean commit",
                "head_sha": head_sha,
            }),
            encoding="utf-8",
        )
        if git("status", "--porcelain") != "":
            raise AssertionError("writing receipt under <git-dir>/patpat/ dirtied the worktree")
        verified = verify_review(default_review_receipt_path(repo), root=repo)
        if verified["verdict"] != "pass":
            raise AssertionError("clean git-dir receipt failed verification")

        # 9. Floor Guard violation (linter suppression + test skip + broad swallow) must fail review
        (repo / "bad.py").write_text(
            "@pytest.mark.skip(reason='flaky')\n"
            "def test_x():\n"
            "    try:\n"
            "        x = 1  # noqa\n"
            "    except Exception:\n"
            "        pass\n",
            encoding="utf-8",
        )
        git("add", "bad.py")
        git("commit", "-qm", "add floor guard violations")
        bad_sha = git("rev-parse", "HEAD")
        expected_path.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "actor": "independent-reviewer",
                "summary": "should fail floor guard",
                "head_sha": bad_sha,
            }),
            encoding="utf-8",
        )
        try:
            verify_review(expected_path, root=repo)
        except ReviewVerificationError as err:
            msg = str(err)
            if "Floor Guard violations" not in msg or "linter-suppression" not in msg:
                raise AssertionError(f"unexpected Floor Guard error message: {msg}")
        else:
            raise AssertionError("review verification accepted Floor Guard violations")

        # 10. Clean fix commit + stray scratch untracked file must fail review
        (repo / "bad.py").write_text("def clean_fn() -> int:\n    return 1\n", encoding="utf-8")
        git("add", "bad.py")
        git("commit", "-qm", "fix floor guard violations")
        fixed_sha = git("rev-parse", "HEAD")
        expected_path.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "actor": "independent-reviewer",
                "summary": "fixed",
                "head_sha": fixed_sha,
            }),
            encoding="utf-8",
        )
        verify_review(expected_path, root=repo)

        stray_dir = repo / "_work"
        stray_dir.mkdir()
        (stray_dir / "scratch.txt").write_text("leftover\n", encoding="utf-8")
        try:
            verify_review(expected_path, root=repo)
        except ReviewVerificationError as err:
            if "stray-scratch-artifact" not in str(err):
                raise AssertionError(f"expected stray-scratch-artifact error, got: {err}")
        else:
            raise AssertionError("review verification accepted stray _work/ scratch file")

        # Clean up stray scratch dir before multi-commit and CLI self-tests
        (stray_dir / "scratch.txt").unlink()
        stray_dir.rmdir()

        # 11. Multi-commit branch off main/master: clean commit 2 must not hide commit 1 Floor Guard violation
        git("checkout", "-qb", "feature/multi-commit")
        (repo / "feature_bad.py").write_text("x = 1  # noqa\n", encoding="utf-8")
        git("add", "feature_bad.py")
        git("commit", "-qm", "commit 1 with floor guard violation")
        (repo / "feature_clean.py").write_text("def ok() -> int:\n    return 2\n", encoding="utf-8")
        git("add", "feature_clean.py")
        git("commit", "-qm", "commit 2 clean")
        multi_sha = git("rev-parse", "HEAD")
        expected_path.write_text(
            json.dumps({
                "kind": "patpat-review-receipt",
                "schema_version": 1,
                "verdict": "pass",
                "actor": "independent-reviewer",
                "summary": "multi-commit branch",
                "head_sha": multi_sha,
            }),
            encoding="utf-8",
        )
        try:
            verify_review(expected_path, root=repo)
        except ReviewVerificationError as err:
            msg = str(err)
            if "Floor Guard violations" not in msg or "linter-suppression" not in msg:
                raise AssertionError(f"expected merge-base Floor Guard failure, got: {msg}")
        else:
            raise AssertionError("clean commit 2 hid Floor Guard violation from commit 1")

        # 12. Missing/unloadable unslop module must fail closed
        original_loader = globals()["_load_unslop_module"]
        globals()["_load_unslop_module"] = lambda: None
        try:
            try:
                verify_review(expected_path, root=repo)
            except ReviewVerificationError as err:
                if "Floor Guard unavailable" not in str(err):
                    raise AssertionError(f"expected fail-closed unslop error, got: {err}")
            else:
                raise AssertionError("verify_review failed open when unslop module was unavailable")
        finally:
            globals()["_load_unslop_module"] = original_loader

        # 13. --skip-diff-check must explicitly tag output so it cannot masquerade as clean Floor Guard pass
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            rc = main(["--root", str(repo), "--receipt", str(expected_path), "--skip-diff-check"])
        skipped_out = stdout_buf.getvalue()
        if rc != 0:
            raise AssertionError(f"--skip-diff-check returned non-zero {rc}")
        if "FLOOR GUARD SKIPPED" not in skipped_out or "Review cleared:" in skipped_out:
            raise AssertionError(f"--skip-diff-check output lacked explicit skip tag: {skipped_out!r}")

    print("Review verifier self-test passed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."), help="workspace root (default: current directory)")
    parser.add_argument("--receipt", type=Path, help="direct path to review receipt JSON")
    parser.add_argument(
        "--base-ref",
        help="optional git base ref for Floor Guard diff check (default: merge-base with main/master, fallback HEAD~1..HEAD)",
    )
    parser.add_argument(
        "--skip-diff-check",
        action="store_true",
        help="skip unslop Floor Guard diff check (receipt schema and HEAD binding still verified)",
    )
    parser.add_argument("--self-test", action="store_true", help="run self-test")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    root = args.root.resolve()
    receipt_path = args.receipt or default_review_receipt_path(root)
    try:
        data = verify_review(
            receipt_path,
            root=root,
            check_diff=not args.skip_diff_check,
            base_ref=args.base_ref,
        )
        if args.skip_diff_check:
            print(
                f"Review receipt verified [FLOOR GUARD SKIPPED: --skip-diff-check]: "
                f"{receipt_path} (actor={data['actor']}, verdict={data['verdict']})"
            )
        else:
            print(f"Review cleared: {receipt_path} (actor={data['actor']}, verdict={data['verdict']})")
        return 0
    except (ReviewVerificationError, OSError) as error:
        print(f"review verification failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
