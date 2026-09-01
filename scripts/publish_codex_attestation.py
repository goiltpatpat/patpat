#!/usr/bin/env python3
"""Fail-closed promote gate for Codex attestation.json. Not a live canary."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import probe_codex_behavior as probe  # noqa: E402


class PromoteError(RuntimeError):
    """Raised when attestation.json must not become external evidence."""


REQUIRED_ATTESTATION_KEYS = {
    "schema_version",
    "kind",
    "source",
    "execution",
    "evidence",
    "verdict",
    "reason_count",
    "cleanup",
    "claims",
}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise PromoteError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.rstrip("\r\n")


def is_private_path(path: Path) -> bool:
    name = path.name
    return name == "receipt.json" or name.endswith(".jsonl")


def listed_private_paths(root: Path) -> list[str]:
    tracked = git(root, "ls-files", "-c", "-o", "--exclude-standard")
    hits = []
    for line in tracked.splitlines():
        if not line:
            continue
        candidate = Path(line)
        if candidate.name == "receipt.json" or line.endswith(".jsonl"):
            hits.append(line)
    return hits


def current_head(root: Path) -> tuple[str, str]:
    status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise PromoteError("dirty worktree or HEAD^{tree} drifted vs attestation.source")
    revision = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    return revision, tree


def load_attestation(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PromoteError(f"malformed attestation: {error}") from error
    if not isinstance(payload, dict):
        raise PromoteError("malformed attestation: not an object")
    return payload


def allowlisted_source(source: Any) -> tuple[str, str] | None:
    if not isinstance(source, dict):
        return None
    revision = probe.safe_match(source.get("revision"), probe.GIT_OBJECT_RE)
    tree = probe.safe_match(source.get("tree"), probe.GIT_OBJECT_RE)
    inventory = probe.safe_match(source.get("installed_inventory_sha256"), probe.SHA256_RE)
    if revision is None or tree is None or inventory is None:
        return None
    if set(source) != {"revision", "tree", "installed_inventory_sha256"}:
        return None
    return revision, tree


def attestation_complete(attestation: dict[str, Any]) -> bool:
    if set(attestation) != REQUIRED_ATTESTATION_KEYS:
        return False
    if attestation.get("schema_version") != probe.ATTESTATION_SCHEMA_VERSION:
        return False
    if attestation.get("kind") != "patpat.codex.contract-canary.attestation":
        return False
    if allowlisted_source(attestation.get("source")) is None:
        return False
    execution = attestation.get("execution")
    if not isinstance(execution, dict) or set(execution) != {"started_at", "finished_at", "host", "model"}:
        return False
    if not probe.valid_utc_interval(execution.get("started_at"), execution.get("finished_at")):
        return False
    host = execution.get("host")
    model = execution.get("model")
    if not isinstance(host, dict) or set(host) != {"name", "version"}:
        return False
    if host.get("name") != "Codex CLI" or probe.safe_match(host.get("version"), probe.CODEX_VERSION_RE) is None:
        return False
    if not isinstance(model, dict) or set(model) != {"requested", "binding"}:
        return False
    if probe.safe_match(model.get("requested"), probe.MODEL_ID_RE) is None:
        return False
    if model.get("binding") != probe.MODEL_BINDING:
        return False
    evidence = attestation.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"rubric_sha256", "private_receipt", "trials"}:
        return False
    if probe.safe_match(evidence.get("rubric_sha256"), probe.SHA256_RE) is None:
        return False
    private_receipt = evidence.get("private_receipt")
    if not isinstance(private_receipt, dict) or set(private_receipt) != {"sha256", "bytes"}:
        return False
    if probe.safe_match(private_receipt.get("sha256"), probe.SHA256_RE) is None:
        return False
    if probe.safe_count(private_receipt.get("bytes")) is None:
        return False
    trials = evidence.get("trials")
    if not isinstance(trials, list) or len(trials) != 2:
        return False
    kinds = set()
    for trial in trials:
        if not isinstance(trial, dict):
            return False
        kind = trial.get("kind")
        if kind not in {"inspect", "change"}:
            return False
        kinds.add(kind)
        if trial.get("verdict") != "PASS":
            return False
        if probe.safe_match(trial.get("prompt_sha256"), probe.SHA256_RE) is None:
            return False
        if probe.safe_match(trial.get("initial_head"), probe.GIT_OBJECT_RE) is None:
            return False
        if trial.get("initial_head") != trial.get("final_head"):
            return False
        if trial.get("reason_count") != 0 or trial.get("returncode") != 0:
            return False
        if trial.get("scope_conforms") is not True:
            return False
        stream = trial.get("event_stream")
        stderr = trial.get("stderr")
        if not isinstance(stream, dict) or probe.safe_match(stream.get("sha256"), probe.SHA256_RE) is None:
            return False
        if probe.safe_count(stream.get("bytes")) is None:
            return False
        if not isinstance(stderr, dict) or probe.safe_match(stderr.get("sha256"), probe.SHA256_RE) is None:
            return False
        if probe.safe_count(stderr.get("bytes")) is None:
            return False
    if kinds != {"inspect", "change"}:
        return False
    cleanup = attestation.get("cleanup")
    if not isinstance(cleanup, dict) or set(cleanup) != {"workspace_removed", "auth_copy_removed"}:
        return False
    if cleanup.get("workspace_removed") is not True or cleanup.get("auth_copy_removed") is not True:
        return False
    if attestation.get("reason_count") != 0:
        return False
    claims = attestation.get("claims")
    if not isinstance(claims, dict):
        return False
    if claims.get("independent_review") != "not_attested":
        return False
    if "not a pre-tool gate" not in str(claims.get("enforcement", "")):
        return False
    if not isinstance(claims.get("limitations"), list) or not claims["limitations"]:
        return False
    return True


def refuse_private_request(attestation_path: Path, destination: Path) -> None:
    targets = [attestation_path, destination]
    if destination.suffix != ".json":
        targets.append(destination / "attestation.json")
    for path in targets:
        if is_private_path(path):
            raise PromoteError("refusing to copy or commit receipt.json or JSONL")


def destination_file(destination: Path) -> Path:
    if destination.suffix == ".json":
        if destination.name != "attestation.json":
            raise PromoteError("public destination must be attestation.json")
        return destination
    return destination / "attestation.json"


def promote(source: Path, attestation_path: Path, destination: Path) -> Path:
    source = source.resolve()
    attestation_path = attestation_path.resolve()
    destination = destination.resolve()
    refuse_private_request(attestation_path, destination)
    private = listed_private_paths(source)
    if private:
        raise PromoteError(
            "private receipt.json or JSONL already sit inside the Git worktree: "
            + ", ".join(private)
        )
    revision, tree = current_head(source)
    attestation = load_attestation(attestation_path)
    bound = allowlisted_source(attestation.get("source"))
    if bound is None:
        raise PromoteError("malformed or incomplete attestation.source")
    source_revision, source_tree = bound
    if source_revision != revision or source_tree != tree:
        raise PromoteError("dirty worktree or HEAD^{tree} drifted vs attestation.source")
    complete = attestation_complete(attestation)
    verdict = attestation.get("verdict")
    if verdict not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        raise PromoteError("malformed or contradictory attestation")
    if not complete:
        if verdict == "PASS":
            raise PromoteError("malformed or contradictory attestation")
        raise PromoteError("malformed or incomplete attestation")
    if verdict != "PASS":
        raise PromoteError("verdict is not PASS")
    target = destination_file(destination)
    refuse_private_request(attestation_path, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(attestation_path, target)
    return target


def passing_receipt(revision: str, tree: str) -> dict[str, Any]:
    def trial(kind: str, marker: str) -> dict[str, Any]:
        return {
            "kind": kind,
            "prompt_sha256": marker * 64,
            "verdict": "PASS",
            "reasons": [],
            "returncode": 0,
            "initial_head": marker * 40,
            "final_head": marker * 40,
            "changed_paths": [] if kind == "inspect" else ["README.md"],
            "events": {"sha256": marker * 64, "bytes": 123},
            "stderr_sha256": marker * 64,
            "stderr_bytes": 0,
        }

    return {
        "schema_version": probe.RECEIPT_SCHEMA_VERSION,
        "kind": "patpat.codex.contract-canary",
        "started_at": "2026-09-01T00:00:00Z",
        "finished_at": "2026-09-01T00:01:00Z",
        "patpat_revision": revision,
        "patpat_tree": tree,
        "installed_inventory_sha256": "c" * 64,
        "host": {"name": "Codex CLI", "version": "codex-cli 1.2.3"},
        "model": {"requested": "example", "binding": probe.MODEL_BINDING},
        "rubric": {"inspect": "read only"},
        "trials": [trial("inspect", "d"), trial("change", "1")],
        "verdict": "PASS",
        "reasons": [],
        "cleanup": {"workspace_removed": True, "auth_copy_removed": True},
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_bytes(probe.encoded_json(payload))


def init_repo(root: Path) -> tuple[str, str]:
    root.mkdir()
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.name", "Patpat Probe")
    git(root, "config", "user.email", "probe@example.invalid")
    git(root, "add", "README.md")
    git(root, "commit", "-q", "-m", "seed")
    return git(root, "rev-parse", "HEAD"), git(root, "rev-parse", "HEAD^{tree}")


def expect_fail(label: str, fn) -> None:
    try:
        fn()
    except PromoteError:
        print(f"FAIL closed: {label}")
        return
    raise AssertionError(f"expected fail closed: {label}")


def run_self_test() -> None:
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        source = base / "repo"
        revision, tree = init_repo(source)
        receipt = passing_receipt(revision, tree)
        attestation = probe.redacted_attestation(receipt, probe.encoded_json(receipt))
        assert attestation["verdict"] == "PASS"
        assert attestation_complete(attestation)
        candidate = base / "candidate" / "attestation.json"
        candidate.parent.mkdir()
        write_json(candidate, attestation)
        public = base / "public"
        copied = promote(source, candidate, public)
        assert copied == public / "attestation.json"
        assert copied.is_file()
        assert json.loads(copied.read_text(encoding="utf-8"))["verdict"] == "PASS"
        assert git(source, "status", "--porcelain=v1") == ""
        assert git(source, "diff", "--cached", "--name-only") == ""
        print("PASS: promote copies attestation.json without git add")

        dirty = base / "dirty"
        dirty_rev, dirty_tree = init_repo(dirty)
        dirty_att = probe.redacted_attestation(
            passing_receipt(dirty_rev, dirty_tree),
            probe.encoded_json(passing_receipt(dirty_rev, dirty_tree)),
        )
        dirty_file = base / "dirty-attestation.json"
        write_json(dirty_file, dirty_att)
        (dirty / "README.md").write_text("dirty\n", encoding="utf-8")
        expect_fail("dirty worktree", lambda: promote(dirty, dirty_file, base / "out-dirty"))

        drifted = json.loads(json.dumps(attestation))
        drifted["source"]["tree"] = "e" * 40
        drift_file = base / "drift.json"
        write_json(drift_file, drifted)
        expect_fail("HEAD tree drift", lambda: promote(source, drift_file, base / "out-drift"))

        expect_fail(
            "copy receipt.json",
            lambda: promote(source, base / "receipt.json", public),
        )
        jsonl = base / "events.jsonl"
        jsonl.write_text("{}\n", encoding="utf-8")
        expect_fail("copy JSONL", lambda: promote(source, jsonl, public))

        planted = source / "receipt.json"
        planted.write_text("{}\n", encoding="utf-8")
        expect_fail(
            "receipt.json already in worktree",
            lambda: promote(source, candidate, base / "out-private"),
        )
        planted.unlink()

        malformed = base / "malformed.json"
        malformed.write_text("{not-json", encoding="utf-8")
        expect_fail("malformed attestation", lambda: promote(source, malformed, base / "out-bad"))

        incomplete = json.loads(json.dumps(attestation))
        del incomplete["evidence"]["trials"][0]["event_stream"]
        incomplete_file = base / "incomplete.json"
        write_json(incomplete_file, incomplete)
        expect_fail("incomplete attestation", lambda: promote(source, incomplete_file, base / "out-inc"))

        contradictory = json.loads(json.dumps(attestation))
        contradictory["reason_count"] = 2
        contra_file = base / "contra.json"
        write_json(contra_file, contradictory)
        expect_fail(
            "contradictory PASS",
            lambda: promote(source, contra_file, base / "out-contra"),
        )

        failed = json.loads(json.dumps(attestation))
        failed["verdict"] = "FAIL"
        failed["reason_count"] = 1
        # Make it incomplete so verdict!=PASS is reached after completeness
        # A complete FAIL is still not PASS.
        fail_file = base / "fail.json"
        write_json(fail_file, failed)
        expect_fail("verdict not PASS", lambda: promote(source, fail_file, base / "out-fail"))

    print("Patpat Codex attestation promote self-test passed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--attestation")
    parser.add_argument("--destination")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        run_self_test()
        return 0
    if not args.attestation or not args.destination:
        parser.error("--attestation and --destination are required")
    copied = promote(Path(args.source), Path(args.attestation), Path(args.destination))
    print(copied)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PromoteError as error:
        print(f"Patpat Codex attestation promote failed: {error}", file=sys.stderr)
        raise SystemExit(1)
