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
import threading
from dataclasses import dataclass
from pathlib import Path


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
MODEL_DIRECTORY = SCRIPT_DIRECTORY.parent / "models"
SPEC_FILE = "AssignmentGeneration.tla"
BASE_CONFIG = "AssignmentGeneration.cfg"
MUTANT_CONFIG = "AssignmentGeneration.mutant.cfg"
REJECTED_WRITE_MUTANT_CONFIG = "AssignmentGeneration.rejected-write-mutant.cfg"
SUCCESS_MARKER = "No error has been found."
MUTANT_INVARIANT = "NoStaleWrites"
REJECTED_WRITE_MUTANT_INVARIANT = "WritesMatchAcceptedAttempts"
TLC_VERSION_PATTERN = re.compile(r"^TLC2 Version [^\r\n]+", re.MULTILINE)
TLC_COMPLETION_PATTERN = re.compile(r"^Model checking completed\.", re.MULTILINE)
TLC_ERROR_PATTERN = re.compile(r"^Error: (.+)$", re.MULTILINE)
TLC_INVARIANT_PATTERN = re.compile(
    r"^Error: Invariant ([A-Za-z][A-Za-z0-9_]*) is violated"
    r"(?: by the initial state)?\.$",
    re.MULTILINE,
)
TLC_TRACE_PATTERN = re.compile(r"^State 1:", re.MULTILINE)
INITIAL_STATES_PATTERN = re.compile(
    r"^Finished computing initial states:\s*([0-9][0-9,]*)\s+distinct states? generated\b",
    re.MULTILINE,
)
STATE_COUNTS_PATTERN = re.compile(
    r"^[ \t]*([0-9][0-9,]*) states generated,\s*([0-9][0-9,]*) distinct states found,\s*"
    r"([0-9][0-9,]*) states left on queue\.$",
    re.MULTILINE,
)
TLC_TIMEOUT_SECONDS = 120
TLC_OUTPUT_LIMIT_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class TlcResult:
    returncode: int
    output: str


def normalize_tlc_output(output: str) -> str:
    return output.replace("\r\n", "\n").replace("\r", "\n")


def run_bounded(
    command: list[str], work_directory: Path, *, output_limit: int
) -> TlcResult:
    """Run a command while bounding captured output in memory."""
    process = subprocess.Popen(
        command,
        cwd=work_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if process.stdout is None:  # pragma: no cover - guaranteed by PIPE
        process.kill()
        raise RuntimeError("TLC output pipe was not created")

    output = bytearray()
    overflow = threading.Event()
    reader_errors: list[BaseException] = []

    def read_output() -> None:
        try:
            while chunk := process.stdout.read(64 * 1024):
                remaining = output_limit - len(output)
                if remaining > 0:
                    output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    overflow.set()
                    process.kill()
        except (OSError, ValueError) as error:
            reader_errors.append(error)

    reader = threading.Thread(target=read_output, name="patpat-tlc-output", daemon=True)
    reader.start()
    try:
        returncode = process.wait(timeout=TLC_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.wait()
        reader.join()
        decoded = output.decode("utf-8", errors="replace")
        raise subprocess.TimeoutExpired(command, error.timeout, output=decoded) from error
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    reader.join()
    process.stdout.close()
    if reader_errors:
        raise RuntimeError(f"failed to capture TLC output: {reader_errors[0]}")
    if overflow.is_set():
        raise RuntimeError(f"TLC output exceeded the {output_limit}-byte limit")
    return TlcResult(
        returncode,
        normalize_tlc_output(output.decode("utf-8", errors="replace")),
    )


def run_tlc(
    java: str, jar: Path, config_name: str, work_directory: Path
) -> TlcResult:
    command = [java, "-jar", str(jar), "-continue", "-config", config_name, SPEC_FILE]
    return run_bounded(
        command,
        work_directory,
        output_limit=TLC_OUTPUT_LIMIT_BYTES,
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


def require_complete_output(output: str) -> None:
    if TLC_COMPLETION_PATTERN.search(output) is None:
        raise RuntimeError("TLC output is missing the model-checking completion marker")


def require_clean_baseline(
    result: TlcResult,
) -> tuple[str, tuple[int, int, int], re.Match[str]]:
    output = normalize_tlc_output(result.output)
    require_complete_output(output)
    if result.returncode != 0:
        raise RuntimeError(f"TLC base model exited with status {result.returncode}")
    errors = TLC_ERROR_PATTERN.findall(output)
    if errors:
        raise RuntimeError(f"TLC base model reported an error: {errors[0]}")
    if SUCCESS_MARKER not in output:
        raise RuntimeError("TLC base model is missing the success marker")
    state_counts = require_nonempty_state_space(output)
    version = TLC_VERSION_PATTERN.search(output)
    if version is None:
        raise RuntimeError("TLC version could not be identified")
    return output, state_counts, version


def require_counterexample(result: TlcResult, invariant: str, label: str) -> str:
    output = normalize_tlc_output(result.output)
    require_complete_output(output)
    if result.returncode != 0:
        raise RuntimeError(
            f"TLC {label} mutant exited abnormally with status {result.returncode}"
        )
    violations = TLC_INVARIANT_PATTERN.findall(output)
    if not violations or set(violations) != {invariant}:
        raise AssertionError(
            f"TLC did not report only the expected {label} invariant: {invariant}"
        )
    allowed_errors = {
        f"Invariant {invariant} is violated.",
        "The behavior up to this point is:",
    }
    unexpected_errors = [
        error for error in TLC_ERROR_PATTERN.findall(output) if error not in allowed_errors
    ]
    if unexpected_errors:
        raise RuntimeError(f"TLC reported an unrelated error: {unexpected_errors[0]}")
    if TLC_TRACE_PATTERN.search(output) is None:
        raise RuntimeError("TLC counterexample is missing a nonempty state trace")
    require_nonempty_state_space(output)
    return output


def counterexample_count(output: str, invariant: str) -> int:
    return sum(
        found == invariant
        for found in TLC_INVARIANT_PATTERN.findall(normalize_tlc_output(output))
    )


def require_nonempty_state_space(output: str) -> tuple[int, int, int]:
    """Require nonzero initial, generated, and distinct states in TLC output."""
    output = normalize_tlc_output(output)
    initial_match = INITIAL_STATES_PATTERN.search(output)
    state_matches = STATE_COUNTS_PATTERN.findall(output)
    if initial_match is None or not state_matches:
        raise RuntimeError("TLC output is missing initial or final state counts")
    initial = int(initial_match.group(1).replace(",", ""))
    generated, distinct, _queued = (
        int(count.replace(",", "")) for count in state_matches[-1]
    )
    if initial < 1 or generated < 1 or distinct < 1:
        raise RuntimeError("TLC completed without a nonempty initial and explored state space")
    return initial, generated, distinct


def self_test_contract() -> int:
    valid_baseline_output = (
        "TLC2 Version test\n"
        "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n"
        "12 states generated, 8 distinct states found, 0 states left on queue.\n"
        "Model checking completed. No error has been found.\n"
    )
    require_clean_baseline(TlcResult(0, valid_baseline_output))
    invalid_baselines = (
        valid_baseline_output.replace(
            "Model checking completed.",
            "Error: Invariant NoStaleWrites is violated.\nModel checking completed.",
        ),
        valid_baseline_output.replace(
            "Model checking completed.",
            "Error: Parsing or semantic analysis failed.\nModel checking completed.",
        ),
    )
    for output in invalid_baselines:
        try:
            require_clean_baseline(TlcResult(0, output))
        except RuntimeError:
            continue
        raise AssertionError("TLC baseline output containing an error was accepted")

    valid_output = (
        "Error: Invariant NoStaleWrites is violated.\n"
        "Error: The behavior up to this point is:\n"
        "State 1: <Initial predicate>\n"
        "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n"
        "  12,345 states generated, 6,789 distinct states found, 0 states left on queue.\n"
        "Model checking completed. No error has been found.\n"
    )
    if require_nonempty_state_space(valid_output) != (1, 12345, 6789):
        raise AssertionError("TLC state-count parser returned incorrect counts")
    require_counterexample(TlcResult(0, valid_output), MUTANT_INVARIANT, "valid")
    repeated_output = valid_output.replace(
        "Model checking completed.",
        "Error: Invariant NoStaleWrites is violated.\n"
        "Error: The behavior up to this point is:\n"
        "State 1: <Initial predicate>\n"
        "Model checking completed.",
    )
    require_counterexample(TlcResult(0, repeated_output), MUTANT_INVARIANT, "repeated")
    require_counterexample(
        TlcResult(0, valid_output.replace("\n", "\r\n")),
        MUTANT_INVARIANT,
        "CRLF",
    )

    invalid_outputs = (
        "Finished computing initial states: 0 distinct states generated at 2026-10-22 00:00:00.\n"
        "0 states generated, 0 distinct states found, 0 states left on queue.\n",
        "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n"
        "1 states generated, 0 distinct states found, 0 states left on queue.\n",
        "1 states generated, 1 distinct states found, 0 states left on queue.\n",
        "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n",
    )
    for output in invalid_outputs:
        try:
            require_nonempty_state_space(output)
        except RuntimeError:
            continue
        raise AssertionError("TLC output without a complete nonempty state space was accepted")

    invalid_counterexamples = (
        TlcResult(
            0,
            valid_output.replace(
                "Model checking completed.",
                "Error: Parsing or semantic analysis failed.\nModel checking completed.",
            ),
        ),
        TlcResult(0, valid_output.replace(MUTANT_INVARIANT, "WrongInvariant")),
        TlcResult(0, valid_output.replace("State 1: <Initial predicate>\n", "")),
        TlcResult(
            0,
            valid_output.replace("Model checking completed. No error has been found.\n", ""),
        ),
        TlcResult(137, valid_output),
    )
    for result in invalid_counterexamples:
        try:
            require_counterexample(result, MUTANT_INVARIANT, "invalid")
        except (AssertionError, RuntimeError):
            continue
        raise AssertionError("invalid TLC counterexample output was accepted")

    try:
        run_bounded(
            [sys.executable, "-c", "import sys; sys.stdout.write('x' * 4096)"],
            SCRIPT_DIRECTORY,
            output_limit=64,
        )
    except RuntimeError as error:
        if "output exceeded" not in str(error):
            raise
    else:
        raise AssertionError("oversized TLC output was accepted")

    print("TLC bounded output and counterexample contract: PASS")
    return 0


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
        try:
            baseline_output, state_counts, version = require_clean_baseline(baseline)
            initial_states, generated_states, distinct_states = state_counts
        except RuntimeError:
            sys.stderr.write(baseline.output)
            raise

        generation_mutant = run_tlc(java, jar, MUTANT_CONFIG, mutant_directory)
        generation_mutant_output = require_counterexample(
            generation_mutant, MUTANT_INVARIANT, "stale-generation"
        )
        rejected_write_directory = temporary_root / "rejected-write-mutant"
        rejected_write_mutant = run_tlc(
            java, jar, REJECTED_WRITE_MUTANT_CONFIG, rejected_write_directory
        )
        rejected_write_mutant_output = require_counterexample(
            rejected_write_mutant, REJECTED_WRITE_MUTANT_INVARIANT, "rejected-write"
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
        print(
            f"States: {initial_states} initial, {generated_states} generated, "
            f"{distinct_states} distinct"
        )
        print(
            "Generation-guard mutant: "
            f"{counterexample_count(generation_mutant_output, MUTANT_INVARIANT)} "
            "counterexamples found as expected"
        )
        print(
            "Rejected-write mutant: "
            f"{counterexample_count(rejected_write_mutant_output, REJECTED_WRITE_MUTANT_INVARIANT)} "
            "counterexamples found as expected"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    check = parser.add_mutually_exclusive_group(required=True)
    check.add_argument("--tlc-jar", type=Path, help="path to tla2tools.jar")
    check.add_argument("--self-test", action="store_true", help="check TLC output contract without running TLC")
    parser.add_argument("--java", default="java", help="Java executable (default: java)")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test_contract()
    try:
        return self_test(args.tlc_jar.resolve(), args.java)
    except subprocess.TimeoutExpired as error:
        print(f"TLC timed out after {TLC_TIMEOUT_SECONDS} seconds", file=sys.stderr)
        if error.stdout:
            print(error.stdout, file=sys.stderr)
        return 2
    except (AssertionError, FileNotFoundError, OSError, RuntimeError) as error:
        print(f"assignment model check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
