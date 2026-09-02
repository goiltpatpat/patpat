#!/usr/bin/env python3
"""Append-only human decision trail beside run state, not inside it."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path


HEADER = ("ts", "phase", "decision", "why", "evidence", "result")
HEADER_LINE = "\t".join(HEADER)
VERDICTS = frozenset({"VERIFIED", "NOT VERIFIED", "INCONCLUSIVE"})
PASS_VERDICTS = frozenset({"VERIFIED"})


class DecisionTrailError(ValueError):
    """Raised when a decision trail file or row violates the contract."""


def verdict_is_pass(result: str) -> bool:
    """INCONCLUSIVE is not a pass. Do not map it to keep."""
    return result in PASS_VERDICTS


def split_rows(text: str) -> list[str]:
    if text.startswith("\ufeff"):
        text = text[1:]
    if not text:
        return []
    return text.splitlines()


def validate_text(text: str) -> list[str]:
    errors: list[str] = []
    lines = split_rows(text)
    if not lines:
        errors.append("decision trail is missing the header row")
        return errors
    if lines[0] != HEADER_LINE:
        errors.append("decision trail header must be ts/phase/decision/why/evidence/result")
        return errors
    for index, line in enumerate(lines[1:], start=2):
        if not line:
            errors.append(f"line {index}: empty data row")
            continue
        columns = line.split("\t")
        if len(columns) != len(HEADER):
            errors.append(f"line {index}: expected {len(HEADER)} tab-separated columns")
            continue
        result = columns[-1]
        if result not in VERDICTS:
            errors.append(
                f"line {index}: result must be VERIFIED, NOT VERIFIED, or INCONCLUSIVE"
            )
            continue
        if result == "INCONCLUSIVE" and verdict_is_pass(result):
            errors.append(f"line {index}: INCONCLUSIVE is not a pass")
    return errors


def validate_path(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return [f"{path}: {error}"]
    return [f"{path}: {error}" for error in validate_text(text)]


def append_row(
    path: Path,
    *,
    ts: str,
    phase: str,
    decision: str,
    why: str,
    evidence: str,
    result: str,
) -> None:
    values = (ts, phase, decision, why, evidence, result)
    if any("\t" in value or "\n" in value or "\r" in value for value in values):
        raise DecisionTrailError("decision trail fields must not contain tabs or newlines")
    if any(not value for value in values):
        raise DecisionTrailError("decision trail fields must be non-empty")
    if result not in VERDICTS:
        raise DecisionTrailError("result must be VERIFIED, NOT VERIFIED, or INCONCLUSIVE")
    if result == "INCONCLUSIVE" and verdict_is_pass(result):
        raise DecisionTrailError("INCONCLUSIVE is not a pass")

    existing = ""
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        errors = validate_text(existing)
        if errors:
            raise DecisionTrailError("; ".join(errors))
        body = existing if existing.endswith("\n") else existing + "\n"
    else:
        body = HEADER_LINE + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(body + "\t".join(values) + "\n", encoding="utf-8")


def run_self_test() -> list[str]:
    failures: list[str] = []
    if verdict_is_pass("INCONCLUSIVE"):
        failures.append("self-test: INCONCLUSIVE must not count as a pass")
    if verdict_is_pass("NOT VERIFIED"):
        failures.append("self-test: NOT VERIFIED must not count as a pass")
    if not verdict_is_pass("VERIFIED"):
        failures.append("self-test: VERIFIED must count as a pass")

    with tempfile.TemporaryDirectory(prefix="patpat-decisions-") as temp_directory:
        path = Path(temp_directory) / "run-id" / "decisions.tsv"
        append_row(
            path,
            ts="2026-09-02T00:00:00+00:00",
            phase="VERIFY",
            decision="keep the contract pin",
            why="missing sentences must fail closed",
            evidence="scripts/validate.py:1",
            result="VERIFIED",
        )
        first = path.read_text(encoding="utf-8")
        append_row(
            path,
            ts="2026-09-02T00:01:00+00:00",
            phase="REVIEW",
            decision="leave INCONCLUSIVE unmapped",
            why="INCONCLUSIVE is not a pass",
            evidence="PR#0",
            result="INCONCLUSIVE",
        )
        second = path.read_text(encoding="utf-8")
        if not second.startswith(first if first.endswith("\n") else first + "\n"):
            if first not in second or second.index(first.strip()) != 0:
                failures.append("self-test: append mutated prior rows")
        if first not in second:
            failures.append("self-test: append dropped the first row")
        errors = validate_text(second)
        if errors:
            failures.append(f"self-test: valid trail rejected: {errors}")

        broken = Path(temp_directory) / "broken.tsv"
        broken.write_text("nope\n", encoding="utf-8")
        if not validate_path(broken):
            failures.append("self-test: accepted a missing header")

        mapped = Path(temp_directory) / "mapped.tsv"
        mapped.write_text(
            HEADER_LINE + "\n"
            + "t\tVERIFY\tcall\twhy\tevidence\tkeep\n",
            encoding="utf-8",
        )
        mapped_errors = validate_text(mapped.read_text(encoding="utf-8"))
        if not any("INCONCLUSIVE" in error or "result must be" in error for error in mapped_errors):
            failures.append("self-test: accepted a keep mapping instead of a verdict")

        try:
            append_row(
                path,
                ts="2026-09-02T00:02:00+00:00",
                phase="LEARN",
                decision="rewrite history",
                why="should fail",
                evidence="file:1",
                result="keep",
            )
        except DecisionTrailError:
            pass
        else:
            failures.append("self-test: append accepted keep as a verdict")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--append", type=Path)
    parser.add_argument("--ts")
    parser.add_argument("--phase")
    parser.add_argument("--decision")
    parser.add_argument("--why")
    parser.add_argument("--evidence")
    parser.add_argument("--result")
    args = parser.parse_args()

    if args.self_test:
        failures = run_self_test()
        if failures:
            print("Decision trail self-test failed:")
            for failure in failures:
                print(f"- {failure}")
            return 1
        print("Patpat decision-trail self-test passed.")
        return 0

    if args.validate is not None:
        errors = validate_path(args.validate)
        if errors:
            for error in errors:
                print(error)
            return 1
        print(f"Decision trail ok: {args.validate}")
        return 0

    if args.append is not None:
        required = {
            "ts": args.ts,
            "phase": args.phase,
            "decision": args.decision,
            "why": args.why,
            "evidence": args.evidence,
            "result": args.result,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error("append requires --ts --phase --decision --why --evidence --result")
        try:
            append_row(args.append, **required)
        except DecisionTrailError as error:
            print(error)
            return 1
        print(f"Appended decision: {args.append}")
        return 0

    parser.error("a command or --self-test is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
