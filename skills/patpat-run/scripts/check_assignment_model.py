#!/usr/bin/env python3
"""Check the bounded assignment-generation TLA+ model and targeted mutants."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import os
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
TLC_INVARIANT_LINE_PATTERN = re.compile(
    r"^Error: Invariant (?P<name>[A-Za-z][A-Za-z0-9_]*) is violated"
    r"(?: by the initial state)?\.$",
    re.MULTILINE,
)
TLC_INVARIANT_PATTERN = re.compile(
    r"^Error: Invariant ([A-Za-z][A-Za-z0-9_]*) is violated"
    r"(?: by the initial state)?\.$",
    re.MULTILINE,
)
TLC_TRACE_PATTERN = re.compile(r"^State 1:", re.MULTILINE)
TLC_STATE_HEADER_PATTERN = re.compile(r"^State ([0-9]+):(?:[ \t]*(.*))?$", re.MULTILINE)
TLC_VARIABLE_PATTERN = re.compile(
    r"^[ \t]*/\\\s+([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.*)$", re.MULTILINE
)
CONFIG_ASSIGNMENT_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.+)$")
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
RECEIPT_OUTPUT_LIMIT_BYTES = 32 * 1024 * 1024
REPOSITORY_ROOT = MODEL_DIRECTORY.parents[2]
RECEIPT_FILES = {
    "baseline": "baseline.pass.json",
    "stale-generation": "mutant.stale-generation.counterexample.json",
    "rejected-write": "mutant.rejected-write.counterexample.json",
}


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


def parse_tlc_trace(trace_output: str) -> list[dict[str, object]]:
    """Parse one TLC trace while preserving each variable's rendered value."""
    headers = list(TLC_STATE_HEADER_PATTERN.finditer(trace_output))
    if not headers:
        raise RuntimeError("TLC counterexample is missing its state trace")

    trace: list[dict[str, object]] = []
    previous_state: dict[str, str] | None = None
    for index, header in enumerate(headers):
        end = headers[index + 1].start() if index + 1 < len(headers) else len(trace_output)
        body = trace_output[header.end() : end]
        state: dict[str, str] = {}
        current_name: str | None = None
        current_value: list[str] = []

        def finish_value() -> None:
            nonlocal current_name, current_value
            if current_name is not None:
                if current_name in state:
                    raise RuntimeError(f"TLC state repeats variable {current_name}")
                state[current_name] = "\n".join(current_value).strip()
                current_name = None
                current_value = []

        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                finish_value()
                continue
            if (
                STATE_COUNTS_PATTERN.match(line)
                or INITIAL_STATES_PATTERN.match(line)
                or TLC_COMPLETION_PATTERN.match(line)
                or stripped.startswith(
                    (
                        "The depth of the complete state graph",
                        "The average outdegree of the complete state graph",
                        "Finished in ",
                        "Progress(",
                        "Error:",
                    )
                )
            ):
                finish_value()
                break
            variable = TLC_VARIABLE_PATTERN.match(line)
            if variable:
                finish_value()
                current_name = variable.group(1)
                current_value = [variable.group(2).strip()]
            elif current_name is not None:
                current_value.append(stripped)
        finish_value()
        if not state:
            raise RuntimeError(f"TLC state {header.group(1)} contains no variables")

        action = (header.group(2) or "").strip()
        if action.startswith("<") and action.endswith(">"):
            action = action[1:-1]
        changed_keys = (
            []
            if previous_state is None
            else sorted(
                key
                for key in previous_state.keys() | state.keys()
                if previous_state.get(key) != state.get(key)
            )
        )
        trace.append(
            {
                "index": int(header.group(1)),
                "action": action,
                "changed_keys": changed_keys,
                "state": state,
            }
        )
        previous_state = state
    return trace


def parse_counterexample_traces(output: str, invariant: str) -> list[list[dict[str, object]]]:
    """Parse every complete TLC trace for one invariant in a bounded run."""
    output = normalize_tlc_output(output)
    violations = list(TLC_INVARIANT_LINE_PATTERN.finditer(output))
    traces: list[list[dict[str, object]]] = []
    for index, violation in enumerate(violations):
        if violation.group("name") != invariant:
            continue
        end = (
            violations[index + 1].start()
            if index + 1 < len(violations)
            else len(output)
        )
        completion = TLC_COMPLETION_PATTERN.search(output, violation.end(), end)
        if completion is not None:
            end = completion.start()
        traces.append(parse_tlc_trace(output[violation.end() : end]))
    if not traces:
        raise RuntimeError(f"TLC produced no trace for violated invariant {invariant}")
    return traces


def shortest_counterexample_trace(
    traces: list[list[dict[str, object]]],
) -> list[dict[str, object]]:
    """Select a shortest complete path and use canonical JSON to break ties."""
    return min(
        traces,
        key=lambda trace: (
            len(trace),
            json.dumps(trace, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


def parse_config_metadata(config_text: str) -> tuple[dict[str, object], list[str]]:
    constants: dict[str, object] = {}
    invariants: list[str] = []
    section: str | None = None
    for raw_line in config_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line in {"CONSTANTS", "INVARIANTS"}:
            section = line
            continue
        if section == "CONSTANTS":
            assignment = CONFIG_ASSIGNMENT_PATTERN.fullmatch(line)
            if assignment is None:
                raise RuntimeError(f"unsupported TLC constant entry: {line}")
            key, value = assignment.groups()
            if value in {"TRUE", "FALSE"}:
                parsed: object = value == "TRUE"
            elif value.isdecimal():
                parsed = int(value)
            elif value.startswith("{") and value.endswith("}"):
                parsed = [item.strip() for item in value[1:-1].split(",") if item.strip()]
            else:
                parsed = value
            constants[key] = parsed
        elif section == "INVARIANTS":
            if line.startswith("CHECK_"):
                continue
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", line):
                raise RuntimeError(f"unsupported TLC invariant entry: {line}")
            invariants.append(line)
    if not constants or not invariants:
        raise RuntimeError("TLC configuration is missing constants or invariants")
    return constants, invariants


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "0" * 40
    return result.stdout.strip()


def repository_path(path: Path) -> str:
    return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()


def build_receipt(
    *,
    case_id: str,
    mutant: dict[str, object] | None,
    config_name: str,
    result: TlcResult,
    jar_digest: str,
    expected_invariant: str | None,
) -> dict[str, object]:
    output = normalize_tlc_output(result.output)
    require_complete_output(output)
    states = require_nonempty_state_space(output)
    version = TLC_VERSION_PATTERN.search(output)
    if version is None:
        raise RuntimeError("TLC version could not be identified for the receipt")

    config_path = MODEL_DIRECTORY / config_name
    constants, invariants = parse_config_metadata(config_path.read_text(encoding="utf-8"))
    trace: list[dict[str, object]] = []
    violations = set(TLC_INVARIANT_PATTERN.findall(output))
    if expected_invariant is None:
        if result.returncode != 0 or violations or SUCCESS_MARKER not in output:
            raise RuntimeError("baseline receipt requires a passing TLC run")
        outcome = "pass"
        violated_count = 0
    else:
        if result.returncode != 0 or violations != {expected_invariant}:
            raise RuntimeError("mutant receipt does not contain only its expected counterexample")
        outcome = "counterexample"
        violated_count = counterexample_count(output, expected_invariant)
        traces = parse_counterexample_traces(output, expected_invariant)
        if len(traces) != violated_count:
            raise RuntimeError(
                f"TLC trace count mismatch for {expected_invariant}: "
                f"parsed {len(traces)}, reported {violated_count}"
            )
        trace = shortest_counterexample_trace(traces)

    properties = []
    for invariant in invariants:
        failed = invariant == expected_invariant
        properties.append(
            {
                "name": invariant,
                "outcome": "counterexample" if failed else "pass",
                "counterexample_count": violated_count if failed else 0,
                "trace_selection": "shortest; canonical JSON breaks ties" if failed else None,
                "trace": trace if failed else [],
            }
        )

    return {
        "schema_version": 1,
        "kind": "patpat-model-check-receipt",
        "case": case_id,
        "mutant": mutant,
        "repository": {"head": git_head()},
        "model": {
            "path": repository_path(MODEL_DIRECTORY / SPEC_FILE),
            "sha256": sha256_file(MODEL_DIRECTORY / SPEC_FILE),
        },
        "checker": {
            "name": "TLC",
            "version": version.group(0),
            "tla2tools_jar_sha256": jar_digest,
            "runner_path": repository_path(Path(__file__)),
            "runner_sha256": sha256_file(Path(__file__)),
        },
        "configuration": {
            "path": repository_path(config_path),
            "sha256": sha256_file(config_path),
            "constants": constants,
        },
        "bounds": {
            key: value for key, value in constants.items() if key.startswith("Max")
        },
        "result": {
            "outcome": outcome,
            "tlc_exit_code": result.returncode,
            "states": {
                "initial": states[0],
                "generated": states[1],
                "distinct": states[2],
            },
        },
        "properties": properties,
    }


def require_new_receipt_directory(path: Path) -> Path:
    destination = path.expanduser().absolute()
    if os.path.lexists(destination):
        raise FileExistsError(f"receipt destination already exists: {destination}")
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"receipt parent directory does not exist: {destination.parent}"
        )
    return destination


def serialize_receipt(receipt: dict[str, object]) -> str:
    return json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_receipts(destination: Path, receipts: dict[str, dict[str, object]]) -> Path:
    destination = require_new_receipt_directory(destination)
    serialized = {
        RECEIPT_FILES[case_id]: serialize_receipt(receipt)
        for case_id, receipt in receipts.items()
    }
    total_bytes = sum(len(value.encode("utf-8")) for value in serialized.values())
    if total_bytes > RECEIPT_OUTPUT_LIMIT_BYTES:
        raise RuntimeError(
            f"receipt output exceeded the {RECEIPT_OUTPUT_LIMIT_BYTES}-byte limit"
        )

    destination.mkdir()
    created: list[Path] = []
    try:
        for filename, content in serialized.items():
            path = destination / filename
            with path.open("x", encoding="utf-8", newline="\n") as handle:
                created.append(path)
                handle.write(content)
    except BaseException:
        for path in created:
            try:
                path.unlink()
            except OSError:
                pass
        try:
            destination.rmdir()
        except OSError:
            pass
        raise
    return destination


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




@dataclass(frozen=True)
class AssignmentState:
    generation: int
    assigned: bool
    owner: str
    issued: tuple[tuple[int, str], ...]
    writes: tuple[tuple[int, int], ...]
    attempts: tuple[bool, ...]
    steps: int


def explore_assignment_state_space_python(
    max_generation: int = 3,
    max_steps: int = 6,
    workers: tuple[str, ...] = ("workerA", "workerB"),
    enforce_generation: bool = True,
    inject_rejected_write: bool = False,
) -> dict[str, Any]:
    """Pure-Python breadth-first state-space explorer for AssignmentGeneration model."""
    init_state = AssignmentState(
        generation=0,
        assigned=False,
        owner="noWorker",
        issued=(),
        writes=(),
        attempts=(),
        steps=0,
    )
    queue: deque[tuple[AssignmentState, list[dict[str, Any]]]] = deque()
    queue.append((init_state, [{"index": 1, "action": "Initial predicate", "changed_keys": [], "state": init_state}]))
    visited: set[AssignmentState] = {init_state}
    distinct_states = 1
    total_generated = 1
    counterexample_trace: list[dict[str, Any]] | None = None

    while queue:
        curr, path = queue.popleft()

        # Check invariant: all writes must have token == current_generation
        for token, current in curr.writes:
            if token != current:
                if counterexample_trace is None:
                    counterexample_trace = path
                break
        if counterexample_trace is not None and not enforce_generation:
            break

        if curr.steps >= max_steps:
            continue

        next_transitions: list[tuple[str, list[str], AssignmentState]] = []

        # 1. Assign(worker)
        if curr.generation < max_generation:
            for w in workers:
                nxt = AssignmentState(
                    generation=curr.generation + 1,
                    assigned=True,
                    owner=w,
                    issued=curr.issued + ((curr.generation + 1, w),),
                    writes=curr.writes,
                    attempts=curr.attempts,
                    steps=curr.steps + 1,
                )
                next_transitions.append((f"Assign({w})", ["generation", "assigned", "owner", "issued"], nxt))

        # 2. Revoke
        if curr.assigned and curr.generation < max_generation:
            nxt = AssignmentState(
                generation=curr.generation + 1,
                assigned=False,
                owner="noWorker",
                issued=curr.issued,
                writes=curr.writes,
                attempts=curr.attempts,
                steps=curr.steps + 1,
            )
            next_transitions.append(("Revoke", ["generation", "assigned", "owner"], nxt))

        # 3. AttemptWrite(token, worker)
        for tok in range(0, max_generation + 1):
            for w in workers:
                is_allowed = (
                    any(t == tok and wrk == w for t, wrk in curr.issued)
                    and curr.assigned
                    and (tok == curr.generation or not enforce_generation)
                )
                if is_allowed:
                    nxt = AssignmentState(
                        generation=curr.generation,
                        assigned=curr.assigned,
                        owner=curr.owner,
                        issued=curr.issued,
                        writes=curr.writes + ((tok, curr.generation),),
                        attempts=curr.attempts + (True,),
                        steps=curr.steps + 1,
                    )
                    next_transitions.append((f"AcceptedWrite(tok={tok}, worker={w})", ["writes", "attempts"], nxt))
                else:
                    new_writes = curr.writes
                    if inject_rejected_write and curr.assigned:
                        new_writes = curr.writes + ((curr.generation, curr.generation),)
                    nxt = AssignmentState(
                        generation=curr.generation,
                        assigned=curr.assigned,
                        owner=curr.owner,
                        issued=curr.issued,
                        writes=new_writes,
                        attempts=curr.attempts + (False,),
                        steps=curr.steps + 1,
                    )
                    next_transitions.append((f"RejectedWrite(tok={tok}, worker={w})", ["writes", "attempts"], nxt))

        for action_name, changed_keys, nxt_state in next_transitions:
            total_generated += 1
            if nxt_state not in visited:
                visited.add(nxt_state)
                distinct_states += 1
                new_path = path + [{"index": len(path) + 1, "action": action_name, "changed_keys": changed_keys, "state": nxt_state}]
                queue.append((nxt_state, new_path))

    return {
        "distinct_states": distinct_states,
        "total_generated": total_generated,
        "counterexample": counterexample_trace,
        "passed": counterexample_trace is None,
    }


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

    trace_output = (
        "Error: Invariant NoStaleWrites is violated.\n"
        "Error: The behavior up to this point is:\n"
        "State 1: <Initial predicate>\n"
        "/\\ generation = 0\n"
        "/\\ assigned = FALSE\n"
        "/\\ owner = noWorker\n"
        "\n"
        "State 2: <Assign(workerA)>\n"
        "/\\ generation = 1\n"
        "/\\ assigned = TRUE\n"
        "/\\ owner = workerA\n"
        "\n"
        "Error: Invariant NoStaleWrites is violated.\n"
        "Error: The behavior up to this point is:\n"
        "State 1: <Initial predicate>\n"
        "/\\ generation = 0\n"
        "/\\ assigned = FALSE\n"
        "/\\ owner = noWorker\n"
        "\n"
        "State 2: <Assign(workerA)>\n"
        "/\\ generation = 1\n"
        "/\\ assigned = TRUE\n"
        "/\\ owner = workerA\n"
        "\n"
        "State 3: <Revoke>\n"
        "/\\ generation = 2\n"
        "/\\ assigned = FALSE\n"
        "/\\ owner = noWorker\n"
        "Model checking completed.\n"
    )
    traces = parse_counterexample_traces(trace_output, MUTANT_INVARIANT)
    if len(traces) != 2:
        raise AssertionError("receipt parser did not preserve every mutant trace")
    shortest = shortest_counterexample_trace(traces)
    if len(shortest) != 2 or shortest[0]["changed_keys"] != []:
        raise AssertionError("receipt parser selected an incorrect shortest trace")
    if shortest[1]["changed_keys"] != ["assigned", "generation", "owner"]:
        raise AssertionError("receipt parser returned incorrect changed state keys")

    footer_trace = parse_tlc_trace(
        "State 1: <Initial predicate>\n"
        "/\\ generation = 0\n"
        "/\\ owner = noWorker\n"
        "\n"
        "12 states generated, 8 distinct states found, 0 states left on queue.\n"
        "The depth of the complete state graph search is 2.\n"
        "Finished in 00s at (2026-10-30 12:00:00)\n"
    )
    if footer_trace[0]["state"].get("owner") != "noWorker":
        raise AssertionError("receipt parser leaked TLC summary lines into state variable values")

    constants, invariants = parse_config_metadata(
        (MODEL_DIRECTORY / MUTANT_CONFIG).read_text(encoding="utf-8")
    )
    if constants.get("MaxSteps") != 6 or constants.get("EnforceGeneration") is not False:
        raise AssertionError("receipt parser returned incorrect TLC constants")
    if MUTANT_INVARIANT not in invariants:
        raise AssertionError("receipt parser omitted the targeted invariant")

    synthetic_baseline = (
        "TLC2 Version test\n"
        "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n"
        "12 states generated, 8 distinct states found, 0 states left on queue.\n"
        "Model checking completed. No error has been found.\n"
    )
    baseline_receipt = build_receipt(
        case_id="baseline",
        mutant=None,
        config_name=BASE_CONFIG,
        result=TlcResult(0, synthetic_baseline),
        jar_digest="test-jar-digest",
        expected_invariant=None,
    )
    mutant_receipt = build_receipt(
        case_id="stale-generation",
        mutant={"id": "stale-generation", "target_property": MUTANT_INVARIANT},
        config_name=MUTANT_CONFIG,
        result=TlcResult(
            0,
            "TLC2 Version test\n"
            + trace_output
            + "Finished computing initial states: 1 distinct state generated at 2026-10-22 00:00:00.\n"
            + "12 states generated, 8 distinct states found, 0 states left on queue.\n",
        ),
        jar_digest="test-jar-digest",
        expected_invariant=MUTANT_INVARIANT,
    )
    if baseline_receipt["mutant"] is not None or baseline_receipt["result"]["outcome"] != "pass":
        raise AssertionError("baseline receipt did not record a passing non-mutant run")
    if baseline_receipt["bounds"] != {"MaxGeneration": 3, "MaxSteps": 6}:
        raise AssertionError("receipt omitted the numeric model bounds")
    if mutant_receipt["mutant"]["id"] != "stale-generation":
        raise AssertionError("mutant receipt omitted its mutant identity")
    mutant_property = next(
        item for item in mutant_receipt["properties"] if item["name"] == MUTANT_INVARIANT
    )
    if mutant_property["outcome"] != "counterexample" or len(mutant_property["trace"]) != 2:
        raise AssertionError("mutant receipt omitted its complete selected counterexample")

    with tempfile.TemporaryDirectory(prefix="patpat-receipt-contract-") as raw:
        parent = Path(raw)
        destination = parent / "new-receipts"
        written = write_receipts(
            destination,
            {"baseline": baseline_receipt, "stale-generation": mutant_receipt},
        )
        baseline_file = written / RECEIPT_FILES["baseline"]
        mutant_file = written / RECEIPT_FILES["stale-generation"]
        baseline_bytes = baseline_file.read_bytes()
        mutant_bytes = mutant_file.read_bytes()
        if json.loads(baseline_bytes)["mutant"] is not None:
            raise AssertionError("serialized baseline receipt changed its mutant identity")
        if json.loads(mutant_bytes)["properties"] == []:
            raise AssertionError("serialized mutant receipt lost its property trace")
        try:
            write_receipts(destination, {"baseline": baseline_receipt})
        except FileExistsError:
            pass
        else:
            raise AssertionError("receipt writer overwrote an existing destination")
        if baseline_file.read_bytes() != baseline_bytes or mutant_file.read_bytes() != mutant_bytes:
            raise AssertionError("receipt writer changed existing receipt bytes")
        try:
            require_new_receipt_directory(baseline_file)
        except FileExistsError:
            pass
        else:
            raise AssertionError("receipt destination preflight accepted an existing file")

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


def self_test(jar: Path, java: str, receipt_out: Path | None = None) -> int:
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

        if receipt_out is not None:
            receipts = {
                "baseline": build_receipt(
                    case_id="baseline",
                    mutant=None,
                    config_name=BASE_CONFIG,
                    result=baseline,
                    jar_digest=jar_digest,
                    expected_invariant=None,
                ),
                "stale-generation": build_receipt(
                    case_id="stale-generation",
                    mutant={
                        "id": "stale-generation",
                        "target_property": MUTANT_INVARIANT,
                        "changed_constants": {"EnforceGeneration": False},
                    },
                    config_name=MUTANT_CONFIG,
                    result=generation_mutant,
                    jar_digest=jar_digest,
                    expected_invariant=MUTANT_INVARIANT,
                ),
                "rejected-write": build_receipt(
                    case_id="rejected-write",
                    mutant={
                        "id": "rejected-write",
                        "target_property": REJECTED_WRITE_MUTANT_INVARIANT,
                        "changed_constants": {"InjectRejectedWrite": True},
                    },
                    config_name=REJECTED_WRITE_MUTANT_CONFIG,
                    result=rejected_write_mutant,
                    jar_digest=jar_digest,
                    expected_invariant=REJECTED_WRITE_MUTANT_INVARIANT,
                ),
            }
            receipts_directory = write_receipts(receipt_out, receipts)
            print(f"Receipts written: {receipts_directory}")

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
    # Pure-Python state space explorer verification
    py_baseline = explore_assignment_state_space_python(enforce_generation=True)
    assert py_baseline["passed"], "Pure-Python model explorer failed on baseline"
    py_mutant = explore_assignment_state_space_python(enforce_generation=False)
    assert not py_mutant["passed"], "Pure-Python model explorer failed to catch stale generation mutant"
    assert py_mutant["counterexample"] is not None, "Pure-Python model explorer did not produce counterexample"
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    check = parser.add_mutually_exclusive_group(required=True)
    check.add_argument("--tlc-jar", type=Path, help="path to tla2tools.jar")
    check.add_argument("--self-test", action="store_true", help="check TLC output contract without running TLC")
    check.add_argument("--pure-python", action="store_true", help="run pure-Python state space exploration without Java/TLC")
    parser.add_argument("--java", default="java", help="Java executable (default: java)")
    parser.add_argument(
        "--receipt-out",
        type=Path,
        help="write baseline and mutant JSON receipts to a new directory (must not exist)",
    )
    args = parser.parse_args(argv)
    if args.self_test:
        if args.receipt_out is not None:
            parser.error("--receipt-out requires --tlc-jar and a real TLC run")
        return self_test_contract()
    if args.pure_python:
        res = explore_assignment_state_space_python(enforce_generation=True)
        print(f"Pure-Python model check: baseline pass ({res['distinct_states']} distinct / {res['total_generated']} generated states)")
        return 0
    try:
        receipt_out = (
            require_new_receipt_directory(args.receipt_out)
            if args.receipt_out is not None
            else None
        )
        return self_test(args.tlc_jar.resolve(), args.java, receipt_out)
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
