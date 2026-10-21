#!/usr/bin/env python3
"""Check the bounded assignment-generation TLA+ model and targeted mutants."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
MODEL_DIRECTORY = SCRIPT_DIRECTORY.parent / "models"
SPEC_FILE = "AssignmentGeneration.tla"
BASE_CONFIG = "AssignmentGeneration.cfg"
MUTANT_CONFIG = "AssignmentGeneration.mutant.cfg"
REJECTED_WRITE_MUTANT_CONFIG = "AssignmentGeneration.rejected-write-mutant.cfg"
SUCCESS_MARKER = "No error has been found."
MUTANT_MARKER = "Invariant NoStaleWrites is violated."
REJECTED_WRITE_MUTANT_MARKER = "Invariant WritesMatchAcceptedAttempts is violated."
TLC_VERSION_PATTERN = re.compile(r"^TLC2 Version [^\r\n]+", re.MULTILINE)
TLC_TIMEOUT_SECONDS = 120


def run_tlc(
    java: str, jar: Path, config_name: str, work_directory: Path
) -> subprocess.CompletedProcess[str]:
    command = [java, "-jar", str(jar), "-config", config_name, SPEC_FILE]
    return subprocess.run(
        command,
        cwd=work_directory,
        check=False,
        capture_output=True,
        text=True,
        timeout=TLC_TIMEOUT_SECONDS,
    )


def resolve_java(java: str) -> str:
    candidate = Path(java).expanduser()
    if candidate.is_absolute() or len(candidate.parts) > 1:
        resolved = candidate.resolve()
        if resolved.is_file():
            return str(resolved)
        raise FileNotFoundError(f"Java executable does not exist: {resolved}")

    located = shutil.which(java)
    if located is not None:
        return str(Path(located).resolve())
    if candidate.is_file():
        return str(candidate.resolve())
    raise FileNotFoundError(f"Java executable does not exist: {java}")


def require_counterexample(
    result: subprocess.CompletedProcess[str], marker: str, label: str
) -> str:
    output = result.stdout + result.stderr
    if result.returncode == 0 or marker not in output:
        sys.stderr.write(output)
        raise AssertionError(f"TLC did not find the expected {label} counterexample")
    return output


def self_test(jar: Path, java: str) -> int:
    if not jar.is_file():
        raise FileNotFoundError(f"TLA+ tools jar does not exist: {jar}")
    java = resolve_java(java)
    jar_digest = hashlib.sha256(jar.read_bytes()).hexdigest()

    with tempfile.TemporaryDirectory(prefix="patpat-assignment-model-") as raw:
        temporary_root = Path(raw)
        baseline_directory = temporary_root / "baseline"
        mutant_directory = temporary_root / "mutant"
        for work_directory, config_name in (
            (baseline_directory, BASE_CONFIG),
            (mutant_directory, MUTANT_CONFIG),
            (temporary_root / "rejected-write-mutant", REJECTED_WRITE_MUTANT_CONFIG),
        ):
            work_directory.mkdir()
            shutil.copy2(MODEL_DIRECTORY / SPEC_FILE, work_directory / SPEC_FILE)
            shutil.copy2(MODEL_DIRECTORY / config_name, work_directory / config_name)

        baseline = run_tlc(java, jar, BASE_CONFIG, baseline_directory)
        baseline_output = baseline.stdout + baseline.stderr
        if baseline.returncode != 0 or SUCCESS_MARKER not in baseline_output:
            sys.stderr.write(baseline_output)
            raise RuntimeError("TLC did not prove the bounded base model")
        version = TLC_VERSION_PATTERN.search(baseline_output)
        if version is None:
            sys.stderr.write(baseline_output)
            raise RuntimeError("TLC version could not be identified")

        generation_mutant = run_tlc(java, jar, MUTANT_CONFIG, mutant_directory)
        generation_mutant_output = require_counterexample(
            generation_mutant, MUTANT_MARKER, "stale-generation"
        )
        rejected_write_directory = temporary_root / "rejected-write-mutant"
        rejected_write_mutant = run_tlc(
            java, jar, REJECTED_WRITE_MUTANT_CONFIG, rejected_write_directory
        )
        rejected_write_mutant_output = require_counterexample(
            rejected_write_mutant, REJECTED_WRITE_MUTANT_MARKER, "rejected-write"
        )

        print("Bounded assignment-generation TLA+ model: PASS")
        print(f"Checker: {version.group(0)}")
        print(f"tla2tools.jar SHA-256: {jar_digest}")
        print(
            next(
                line.strip()
                for line in baseline_output.splitlines()
                if SUCCESS_MARKER in line
            )
        )
        for line in baseline_output.splitlines():
            if "states generated" in line:
                print(line.strip())
                break
        print("Generation-guard mutant: counterexample found as expected")
        print(generation_mutant_output)
        print("Rejected-write mutant: counterexample found as expected")
        print(rejected_write_mutant_output)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tlc-jar", required=True, type=Path, help="path to tla2tools.jar")
    parser.add_argument("--java", default="java", help="Java executable (default: java)")
    args = parser.parse_args(argv)
    try:
        return self_test(args.tlc_jar.resolve(), args.java)
    except subprocess.TimeoutExpired as error:
        print(f"TLC timed out after {TLC_TIMEOUT_SECONDS} seconds", file=sys.stderr)
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        if error.stderr:
            print(error.stderr, file=sys.stderr)
        return 2
    except (AssertionError, FileNotFoundError, OSError, RuntimeError) as error:
        print(f"assignment model check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
