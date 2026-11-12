#!/usr/bin/env python3
"""Deterministic executable proof contract evaluator in pure Python 3.

Evaluates proof contracts defined in YAML, JSON, or Markdown formats against
authoritative surfaces. Enforces expectations, executes cleanup even on failure,
evaluates optional falsification vectors, and generates structured JSON receipts.
"""

from __future__ import annotations

import argparse
import dataclasses
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import time
from typing import Any

CANONICAL_FIELDS = ("claim", "surface", "action", "expect", "cleanup")
OPTIONAL_FIELDS = ("falsification_vector", "timeout", "description")


class ContractError(ValueError):
    """Raised when a proof contract is malformed or invalid."""


@dataclasses.dataclass
class Expectation:
    exit_code: int = 0
    stdout_contains: list[str] = dataclasses.field(default_factory=list)
    stdout_not_contains: list[str] = dataclasses.field(default_factory=list)
    stderr_empty: bool | None = None
    stderr_contains: list[str] = dataclasses.field(default_factory=list)
    stderr_not_contains: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"exit_code": self.exit_code}
        if self.stdout_contains:
            data["stdout_contains"] = self.stdout_contains
        if self.stdout_not_contains:
            data["stdout_not_contains"] = self.stdout_not_contains
        if self.stderr_empty is not None:
            data["stderr_empty"] = self.stderr_empty
        if self.stderr_contains:
            data["stderr_contains"] = self.stderr_contains
        if self.stderr_not_contains:
            data["stderr_not_contains"] = self.stderr_not_contains
        return data


@dataclasses.dataclass
class FalsificationVector:
    action: str
    expect: Expectation | None = None
    cleanup: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"action": self.action}
        if self.expect is not None:
            data["expect"] = self.expect.to_dict()
        if self.cleanup is not None:
            data["cleanup"] = self.cleanup
        return data


@dataclasses.dataclass
class ProofContract:
    claim: str
    surface: str
    action: str
    expect: Expectation
    cleanup: str
    falsification_vector: FalsificationVector | None = None
    timeout: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "claim": self.claim,
            "surface": self.surface,
            "action": self.action,
            "expect": self.expect.to_dict(),
            "cleanup": self.cleanup,
        }
        if self.falsification_vector is not None:
            data["falsification_vector"] = self.falsification_vector.to_dict()
        if self.timeout is not None:
            data["timeout"] = self.timeout
        return data


@dataclasses.dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    timed_out: bool = False
    error: str | None = None


# ---------------------------------------------------------------------------
# Pure Python YAML / Scalar Parser (Zero External Dependencies)
# ---------------------------------------------------------------------------

def strip_yaml_comment(line: str) -> str:
    """Strip comment starting with '#' outside quotes."""
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            if not (i > 0 and line[i - 1] == "\\"):
                in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            return line[:i]
    return line


def parse_yaml_scalar(val: str) -> Any:
    """Parse a YAML scalar value into Python type."""
    val = val.strip()
    if not val:
        return ""
    if val in ("null", "~", "None"):
        return None
    if val.lower() in ("true", "yes", "on"):
        return True
    if val.lower() in ("false", "no", "off"):
        return False
    # Quoted string
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        if len(val) >= 2:
            inner = val[1:-1]
            if val.startswith('"'):
                try:
                    inner = json.loads(val)
                except (json.JSONDecodeError, ValueError):
                    pass
            return inner
    # Integer
    try:
        return int(val)
    except ValueError:
        pass
    # Float
    try:
        return float(val)
    except ValueError:
        pass
    # JSON flow list or dict
    if (val.startswith("[") and val.endswith("]")) or (val.startswith("{") and val.endswith("}")):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, ValueError):
            pass
    return val


def parse_yaml_text(text: str) -> Any:
    """Parse pure YAML text without third-party libraries."""
    raw_lines = text.splitlines()
    processed_lines: list[tuple[int, int, str, str]] = []
    for idx, raw_line in enumerate(raw_lines):
        line = raw_line.replace("\t", "  ")
        stripped = strip_yaml_comment(line)
        if not stripped.strip():
            continue
        indent = len(stripped) - len(stripped.lstrip(" "))
        processed_lines.append((idx + 1, indent, stripped.strip(), raw_line))

    if not processed_lines:
        return {}

    pos = 0

    def parse_block(min_indent: int) -> Any:
        nonlocal pos
        if pos >= len(processed_lines):
            return {}

        _, first_indent, first_content, _ = processed_lines[pos]
        if first_indent < min_indent:
            return {}

        if first_content.startswith("- ") or first_content == "-":
            # List
            result_list: list[Any] = []
            while pos < len(processed_lines):
                line_no, indent, content, orig_line = processed_lines[pos]
                if indent < first_indent:
                    break
                if indent > first_indent:
                    break
                if not (content.startswith("- ") or content == "-"):
                    break
                pos += 1
                item_content = content[2:].strip() if content.startswith("- ") else ""
                if not item_content:
                    if pos < len(processed_lines) and processed_lines[pos][1] > indent:
                        child = parse_block(processed_lines[pos][1])
                        result_list.append(child)
                    else:
                        result_list.append(None)
                else:
                    if ":" in item_content and not (item_content.startswith("{") or item_content.startswith("[")):
                        sub_k, _, sub_v = item_content.partition(":")
                        sub_k = sub_k.strip().strip("'\"")
                        sub_v = sub_v.strip()
                        sub_dict: dict[str, Any] = {}
                        if sub_v:
                            sub_dict[sub_k] = parse_yaml_scalar(sub_v)
                        else:
                            if pos < len(processed_lines) and processed_lines[pos][1] > indent:
                                sub_dict[sub_k] = parse_block(processed_lines[pos][1])
                            else:
                                sub_dict[sub_k] = None
                        if pos < len(processed_lines) and processed_lines[pos][1] > indent:
                            rest = parse_block(processed_lines[pos][1])
                            if isinstance(rest, dict):
                                sub_dict.update(rest)
                        result_list.append(sub_dict)
                    else:
                        result_list.append(parse_yaml_scalar(item_content))
            return result_list
        else:
            # Mapping
            result_dict: dict[str, Any] = {}
            while pos < len(processed_lines):
                line_no, indent, content, orig_line = processed_lines[pos]
                if indent < first_indent:
                    break
                if indent > first_indent:
                    break
                if ":" not in content:
                    pos += 1
                    continue
                pos += 1
                key, _, val = content.partition(":")
                key = key.strip().strip("'\"")
                val = val.strip()
                if val in ("|", ">"):
                    # Multiline block
                    block_lines: list[str] = []
                    child_indent: int | None = None
                    while pos < len(processed_lines):
                        next_line_no, next_indent, next_content, next_orig = processed_lines[pos]
                        if next_indent <= indent:
                            break
                        if child_indent is None:
                            child_indent = next_indent
                        raw_indent = len(next_orig) - len(next_orig.lstrip(" "))
                        rel_indent = max(0, raw_indent - child_indent)
                        block_lines.append(" " * rel_indent + next_orig.strip())
                        pos += 1
                    result_dict[key] = "\n".join(block_lines) if val == "|" else " ".join(block_lines)
                elif not val:
                    if pos < len(processed_lines) and processed_lines[pos][1] > indent:
                        child = parse_block(processed_lines[pos][1])
                        result_dict[key] = child
                    else:
                        result_dict[key] = None
                else:
                    result_dict[key] = parse_yaml_scalar(val)
            return result_dict

    return parse_block(0)


# ---------------------------------------------------------------------------
# Expectation Normalizer
# ---------------------------------------------------------------------------

def parse_expectation_string(text: str) -> dict[str, Any]:
    """Parse string representation of expectation (e.g. key=val, key: val)."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass

    result: dict[str, Any] = {}
    m_exit = re.search(r"\bexit_code\s*[:=]\s*(-?\d+)", text, re.IGNORECASE)
    if m_exit:
        result["exit_code"] = int(m_exit.group(1))

    m_stderr_empty = re.search(r"\bstderr_empty\s*[:=]\s*(true|false|yes|no)\b", text, re.IGNORECASE)
    if m_stderr_empty:
        result["stderr_empty"] = m_stderr_empty.group(1).lower() in ("true", "yes")
    elif re.search(r"\bstderr\s+empty\b", text, re.IGNORECASE):
        result["stderr_empty"] = True

    m_stdout = re.search(r"\bstdout_contains\s*[:=]\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s,;]+))", text, re.IGNORECASE)
    if m_stdout:
        val = next(g for g in m_stdout.groups() if g is not None)
        result["stdout_contains"] = [val]

    return result


def normalize_expectation(raw: Any) -> Expectation:
    """Normalize raw expect data into Expectation instance."""
    if raw is None:
        return Expectation(exit_code=0)

    if isinstance(raw, str):
        raw_dict = parse_expectation_string(raw)
        if not raw_dict and ":" in raw:
            parsed_yaml = parse_yaml_text(raw)
            if isinstance(parsed_yaml, dict):
                raw_dict = parsed_yaml
        raw = raw_dict

    if isinstance(raw, list):
        flat: dict[str, Any] = {}
        for item in raw:
            if isinstance(item, dict):
                flat.update(item)
            elif isinstance(item, str):
                parsed_item = parse_expectation_string(item)
                flat.update(parsed_item)
        raw = flat

    if not isinstance(raw, dict):
        raise ContractError(f"expect field must be a mapping or structured string, got {type(raw).__name__}")

    norm_dict: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(k, str):
            norm_dict[k.strip().lower().replace("-", "_").replace(" ", "_")] = v

    exit_code = 0
    if "exit_code" in norm_dict:
        try:
            exit_code = int(norm_dict["exit_code"])
        except (ValueError, TypeError) as err:
            raise ContractError(f"expect.exit_code must be an integer: {norm_dict['exit_code']}") from err

    def to_string_list(val: Any) -> list[str]:
        if val is None:
            return []
        if isinstance(val, (list, tuple)):
            return [str(x) for x in val if x is not None]
        return [str(val)]

    stdout_contains = to_string_list(norm_dict.get("stdout_contains"))
    stdout_not_contains = to_string_list(norm_dict.get("stdout_not_contains"))
    stderr_contains = to_string_list(norm_dict.get("stderr_contains"))
    stderr_not_contains = to_string_list(norm_dict.get("stderr_not_contains"))

    stderr_empty: bool | None = None
    if "stderr_empty" in norm_dict:
        val = norm_dict["stderr_empty"]
        if isinstance(val, bool):
            stderr_empty = val
        elif isinstance(val, str):
            stderr_empty = val.lower() in ("true", "yes", "1")
        elif isinstance(val, int):
            stderr_empty = bool(val)

    return Expectation(
        exit_code=exit_code,
        stdout_contains=stdout_contains,
        stdout_not_contains=stdout_not_contains,
        stderr_empty=stderr_empty,
        stderr_contains=stderr_contains,
        stderr_not_contains=stderr_not_contains,
    )


# ---------------------------------------------------------------------------
# Contract Parser (JSON / YAML / Markdown)
# ---------------------------------------------------------------------------

def normalize_field_name(name: str) -> str:
    key = name.strip().lower().replace("-", "_").replace(" ", "_")
    if key in ("expected", "expected_observation", "expectations"):
        return "expect"
    if key in ("falsification", "falsify", "falsification_vector"):
        return "falsification_vector"
    if key in ("clean_up", "teardown"):
        return "cleanup"
    if key in ("command", "run"):
        return "action"
    if key in ("target", "authoritative_surface"):
        return "surface"
    return key


def parse_markdown_contract(text: str) -> dict[str, Any]:
    """Parse proof contract embedded in markdown."""
    # 1. Fenced code block (yaml, json, proof-contract)
    fence_pattern = re.compile(
        r"```(?:ya?ml|json|proof[-_]?contract)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE
    )
    for match in fence_pattern.finditer(text):
        block_text = match.group(1).strip()
        # Try JSON
        try:
            data = json.loads(block_text)
            if isinstance(data, dict):
                norm = {normalize_field_name(k): v for k, v in data.items() if isinstance(k, str)}
                if "action" in norm or "claim" in norm:
                    return norm
        except (json.JSONDecodeError, ValueError):
            pass
        # Try YAML
        try:
            data = parse_yaml_text(block_text)
            if isinstance(data, dict):
                norm = {normalize_field_name(k): v for k, v in data.items() if isinstance(k, str)}
                if "action" in norm or "claim" in norm:
                    return norm
        except (ValueError, KeyError, TypeError, IndexError):
            pass

    # 2. Markdown table
    table_rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) == 2 and not cells[0].startswith("---") and cells[0].lower() != "field":
                table_rows.append((cells[0], cells[1]))
    if table_rows:
        table_dict: dict[str, Any] = {}
        for k, v in table_rows:
            table_dict[normalize_field_name(k)] = v
        if "action" in table_dict or "claim" in table_dict:
            return table_dict

    # 3. Markdown headings (## Claim, ## Surface, etc.)
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$")
    heading_sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in text.splitlines():
        m = heading_re.match(line.strip())
        if m:
            if current_key:
                heading_sections[current_key] = "\n".join(current_lines).strip()
            norm = normalize_field_name(m.group(2))
            if norm in CANONICAL_FIELDS or norm in OPTIONAL_FIELDS:
                current_key = norm
                current_lines = []
            else:
                current_key = None
        elif current_key is not None:
            current_lines.append(line)
    if current_key:
        heading_sections[current_key] = "\n".join(current_lines).strip()
    if len(heading_sections) >= 3 and ("action" in heading_sections or "claim" in heading_sections):
        return heading_sections

    # 4. Markdown bullet points / bold labels
    bullet_lines: list[str] = []
    for line in text.splitlines():
        m_bold = re.match(r"^\s*-\s*\*\*([A-Za-z0-9_\- ]+)\*\*\s*:\s*(.*)$", line)
        if m_bold:
            indent = len(line) - len(line.lstrip(" "))
            bullet_lines.append(" " * indent + m_bold.group(1) + ": " + m_bold.group(2))
            continue
        m_bullet = re.match(r"^\s*-\s*([A-Za-z0-9_\- ]+)\s*:\s*(.*)$", line)
        if m_bullet and normalize_field_name(m_bullet.group(1)) in (CANONICAL_FIELDS + OPTIONAL_FIELDS):
            indent = len(line) - len(line.lstrip(" "))
            bullet_lines.append(" " * indent + m_bullet.group(1) + ": " + m_bullet.group(2))
            continue
        bullet_lines.append(line)

    normalized_md = "\n".join(bullet_lines)
    parsed = parse_yaml_text(normalized_md)
    if isinstance(parsed, dict):
        norm = {normalize_field_name(k): v for k, v in parsed.items() if isinstance(k, str)}
        if "claim" in norm or "action" in norm:
            return norm

    return {}


def parse_contract_data(text: str) -> dict[str, Any]:
    """Parse raw text from JSON, YAML, or Markdown into raw dict."""
    stripped = text.strip()
    # 1. Direct JSON
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            loaded = json.loads(stripped)
            if isinstance(loaded, dict):
                return loaded
        except json.JSONDecodeError:
            pass

    # 2. Markdown check
    if any(marker in text for marker in ("```", "## ", "- **", "- ", "|")):
        md_dict = parse_markdown_contract(text)
        if md_dict:
            return md_dict

    # 3. Direct YAML / key-value lines
    yaml_dict = parse_yaml_text(text)
    if isinstance(yaml_dict, dict) and yaml_dict:
        return yaml_dict

    # Fallback to Markdown parser
    md_fallback = parse_markdown_contract(text)
    if md_fallback:
        return md_fallback

    raise ContractError("Unable to parse proof contract: unsupported format or invalid syntax")


def parse_contract(text: str, source_path: Path | None = None) -> ProofContract:
    """Parse and validate a ProofContract from text."""
    raw = parse_contract_data(text)
    if not isinstance(raw, dict):
        raise ContractError(f"Contract must be a mapping, got {type(raw).__name__}")

    normalized: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(k, str):
            normalized[normalize_field_name(k)] = v

    # Validate canonical required fields
    missing = [f for f in CANONICAL_FIELDS if f not in normalized or normalized[f] is None]
    if missing:
        raise ContractError(f"Proof contract missing required field(s): {', '.join(missing)}")

    claim = str(normalized["claim"]).strip()
    surface = str(normalized["surface"]).strip()
    action = normalized["action"]
    if isinstance(action, list):
        action = " && ".join(str(a).strip() for a in action)
    else:
        action = str(action).strip()

    if not claim:
        raise ContractError("claim field cannot be empty")
    if not surface:
        raise ContractError("surface field cannot be empty")
    if not action:
        raise ContractError("action field cannot be empty")

    cleanup_raw = normalized.get("cleanup")
    cleanup = str(cleanup_raw).strip() if cleanup_raw is not None else ""

    # Parse expectation
    expect = normalize_expectation(normalized["expect"])

    # Optional falsification vector
    falsification: FalsificationVector | None = None
    if "falsification_vector" in normalized and normalized["falsification_vector"]:
        raw_fals = normalized["falsification_vector"]
        if isinstance(raw_fals, str):
            falsification = FalsificationVector(action=raw_fals.strip())
        elif isinstance(raw_fals, dict):
            f_norm = {normalize_field_name(k): v for k, v in raw_fals.items() if isinstance(k, str)}
            f_action = str(f_norm.get("action", "")).strip()
            if not f_action:
                raise ContractError("falsification_vector mapping must specify 'action'")
            f_expect = normalize_expectation(f_norm["expect"]) if "expect" in f_norm else None
            f_cleanup = str(f_norm["cleanup"]).strip() if "cleanup" in f_norm else None
            falsification = FalsificationVector(action=f_action, expect=f_expect, cleanup=f_cleanup)

    timeout = None
    if "timeout" in normalized and normalized["timeout"] is not None:
        try:
            timeout = float(normalized["timeout"])
        except (ValueError, TypeError):
            pass

    return ProofContract(
        claim=claim,
        surface=surface,
        action=action,
        expect=expect,
        cleanup=cleanup,
        falsification_vector=falsification,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Command Execution Subprocess Handler
# ---------------------------------------------------------------------------

def execute_subprocess(command: str, timeout: float | None = None, cwd: Path | None = None) -> CommandResult:
    """Execute command in subprocess with timeout, capturing stdout and stderr."""
    start_time = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return CommandResult(
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=duration_ms,
            timed_out=False,
            error=None,
        )
    except subprocess.TimeoutExpired as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        stdout = exc.stdout if isinstance(exc.stdout, str) else (
            exc.stdout.decode("utf-8", errors="replace") if exc.stdout else ""
        )
        stderr = exc.stderr if isinstance(exc.stderr, str) else (
            exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
        )
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout=stdout,
            stderr=stderr,
            duration_ms=duration_ms,
            timed_out=True,
            error=f"Command timed out after {timeout} seconds",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        return CommandResult(
            command=command,
            exit_code=-1,
            stdout="",
            stderr=str(exc),
            duration_ms=duration_ms,
            timed_out=False,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Evaluator Logic
# ---------------------------------------------------------------------------

def assert_expectations(res: CommandResult, expect: Expectation) -> tuple[list[dict[str, Any]], list[str]]:
    """Assert expectation against command result."""
    assertions: list[dict[str, Any]] = []
    errors: list[str] = []

    # 1. Exit code
    exit_ok = (res.exit_code == expect.exit_code)
    assertions.append({
        "check": "exit_code",
        "expected": expect.exit_code,
        "actual": res.exit_code,
        "passed": exit_ok,
    })
    if not exit_ok:
        errors.append(f"exit_code mismatch: expected {expect.exit_code}, got {res.exit_code}")

    # 2. stdout_contains
    for target in expect.stdout_contains:
        has_str = target in res.stdout
        assertions.append({
            "check": "stdout_contains",
            "expected": target,
            "passed": has_str,
        })
        if not has_str:
            errors.append(f"stdout missing expected substring: {target!r}")

    # 3. stdout_not_contains
    for target in expect.stdout_not_contains:
        has_str = target in res.stdout
        assertions.append({
            "check": "stdout_not_contains",
            "forbidden": target,
            "passed": not has_str,
        })
        if has_str:
            errors.append(f"stdout unexpectedly contains forbidden substring: {target!r}")

    # 4. stderr_empty
    if expect.stderr_empty is not None:
        is_empty = (res.stderr.strip() == "")
        passed = (is_empty == expect.stderr_empty)
        assertions.append({
            "check": "stderr_empty",
            "expected": expect.stderr_empty,
            "actual": is_empty,
            "passed": passed,
        })
        if not passed:
            if expect.stderr_empty:
                errors.append(f"stderr was not empty: {res.stderr.strip()!r}")
            else:
                errors.append("stderr was empty but expected non-empty output")

    # 5. stderr_contains
    for target in expect.stderr_contains:
        has_str = target in res.stderr
        assertions.append({
            "check": "stderr_contains",
            "expected": target,
            "passed": has_str,
        })
        if not has_str:
            errors.append(f"stderr missing expected substring: {target!r}")

    # 6. stderr_not_contains
    for target in expect.stderr_not_contains:
        has_str = target in res.stderr
        assertions.append({
            "check": "stderr_not_contains",
            "forbidden": target,
            "passed": not has_str,
        })
        if has_str:
            errors.append(f"stderr unexpectedly contains forbidden substring: {target!r}")

    return assertions, errors


def evaluate_contract(
    contract: ProofContract,
    timeout: float | None = None,
    cwd: Path | None = None,
) -> dict[str, Any]:
    """Execute contract, perform assertions, run cleanup, and return structured receipt."""
    eff_timeout = timeout if timeout is not None else (contract.timeout or 30.0)
    errors: list[str] = []
    action_res: CommandResult | None = None
    assertions: list[dict[str, Any]] = []
    falsification_rec: dict[str, Any] | None = None
    cleanup_rec: dict[str, Any] | None = None

    try:
        # Step 1: Execute primary action
        action_res = execute_subprocess(contract.action, timeout=eff_timeout, cwd=cwd)
        if action_res.timed_out:
            errors.append(f"Action timed out after {eff_timeout} seconds")
        elif action_res.error:
            errors.append(f"Action execution error: {action_res.error}")

        # Step 2: Assert primary expectations
        assertions, assert_errors = assert_expectations(action_res, contract.expect)
        errors.extend(assert_errors)

        # Step 3: Falsification Vector (if present)
        if contract.falsification_vector is not None:
            f_vec = contract.falsification_vector
            f_res = execute_subprocess(f_vec.action, timeout=eff_timeout, cwd=cwd)

            # Cleanup falsification if defined
            f_cleanup_res = None
            if f_vec.cleanup and f_vec.cleanup.strip() and f_vec.cleanup.strip().lower() not in {"none", "-", "n/a"}:
                f_cleanup_res = execute_subprocess(f_vec.cleanup, timeout=eff_timeout, cwd=cwd)

            if f_vec.expect is not None:
                # Assert custom falsification expectation
                f_assertions, f_errors = assert_expectations(f_res, f_vec.expect)
                f_passed = (len(f_errors) == 0 and not f_res.timed_out)
                if not f_passed:
                    errors.append(f"Falsification vector failed expectation: {', '.join(f_errors)}")
            else:
                # Default: falsification action MUST FAIL the primary expectation
                _, f_errors = assert_expectations(f_res, contract.expect)
                # If f_errors is empty, the falsified action passed primary expectations -> tautology!
                if not f_errors and not f_res.timed_out:
                    errors.append("Falsification vector unexpectedly satisfied primary expectation (oracle tautology detected)")
                    f_passed = False
                else:
                    f_passed = True

            falsification_rec = {
                "action": f_vec.action,
                "exit_code": f_res.exit_code,
                "passed": f_passed,
                "duration_ms": round(f_res.duration_ms, 2),
                "timed_out": f_res.timed_out,
            }
            if f_cleanup_res is not None:
                falsification_rec["cleanup_exit_code"] = f_cleanup_res.exit_code

    finally:
        # Step 4: GUARANTEED CLEANUP EXECUTION (runs even if action fails or times out)
        cleanup_cmd = contract.cleanup.strip() if contract.cleanup else ""
        if cleanup_cmd and cleanup_cmd.lower() not in {"none", "-", "—", "n/a", "null", "false", "true", ":"}:
            c_res = execute_subprocess(cleanup_cmd, timeout=eff_timeout, cwd=cwd)
            cleanup_ok = (c_res.exit_code == 0)
            cleanup_rec = {
                "executed": True,
                "command": cleanup_cmd,
                "exit_code": c_res.exit_code,
                "stdout": c_res.stdout,
                "stderr": c_res.stderr,
                "duration_ms": round(c_res.duration_ms, 2),
                "timed_out": c_res.timed_out,
                "passed": cleanup_ok,
            }
            if not cleanup_ok:
                errors.append(f"Cleanup command failed with exit code {c_res.exit_code}: {c_res.stderr.strip()}")
        else:
            cleanup_rec = {
                "executed": False,
                "command": cleanup_cmd or "none",
                "passed": True,
            }

    passed = (len(errors) == 0)
    verdict = "pass" if passed else "fail"

    receipt: dict[str, Any] = {
        "schema": "patpat-proof-receipt/v1",
        "verdict": verdict,
        "passed": passed,
        "claim": contract.claim,
        "surface": contract.surface,
        "action": {
            "command": contract.action,
            "exit_code": action_res.exit_code if action_res else -1,
            "stdout": action_res.stdout if action_res else "",
            "stderr": action_res.stderr if action_res else "",
            "duration_ms": round(action_res.duration_ms, 2) if action_res else 0.0,
            "timed_out": action_res.timed_out if action_res else False,
        },
        "expect": contract.expect.to_dict(),
        "assertions": assertions,
        "cleanup": cleanup_rec,
        "falsification": falsification_rec,
        "contract": contract.to_dict(),
        "errors": errors,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }
    return receipt


# ---------------------------------------------------------------------------
# Self-Test Suite
# ---------------------------------------------------------------------------

def self_test() -> int:
    """Run comprehensive self-test suite covering passing, failing, and edge cases."""
    print("Running eval_proof_contract self-test suite...")
    cases_run = 0

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. JSON passing contract
        json_pass = {
            "claim": "echo produces hello",
            "surface": "echo",
            "action": "echo hello",
            "expect": {
                "exit_code": 0,
                "stdout_contains": ["hello"],
                "stderr_empty": True,
            },
            "cleanup": "true",
        }
        c1 = parse_contract(json.dumps(json_pass))
        r1 = evaluate_contract(c1, cwd=tmp_path)
        assert r1["passed"] is True, f"Case 1 failed: {r1['errors']}"
        assert r1["verdict"] == "pass"
        assert r1["action"]["exit_code"] == 0
        cases_run += 1

        # 2. YAML passing contract with multiline block and list expect
        yaml_pass = """
claim: arithmetic proof
surface: python3
action: |
  python3 -c "print(21 * 2)"
expect:
  exit_code: 0
  stdout_contains:
    - "42"
  stderr_empty: true
cleanup: true
"""
        c2 = parse_contract(yaml_pass)
        r2 = evaluate_contract(c2, cwd=tmp_path)
        assert r2["passed"] is True, f"Case 2 failed: {r2['errors']}"
        assert r2["verdict"] == "pass"
        cases_run += 1

        # 3. Markdown code fence (YAML)
        md_yaml = """# Contract Document
Some explanation before.

```yaml
claim: markdown yaml fence
surface: echo
action: echo "fence_test_output"
expect:
  exit_code: 0
  stdout_contains: fence_test_output
  stderr_empty: true
cleanup: true
```
"""
        c3 = parse_contract(md_yaml)
        r3 = evaluate_contract(c3, cwd=tmp_path)
        assert r3["passed"] is True, f"Case 3 failed: {r3['errors']}"
        assert r3["verdict"] == "pass"
        cases_run += 1

        # 4. Markdown code fence (JSON)
        md_json = """# Contract Document
```json
{
  "claim": "markdown json fence",
  "surface": "sh",
  "action": "printf 'json_token'",
  "expect": {
    "exit_code": 0,
    "stdout_contains": ["json_token"],
    "stderr_empty": true
  },
  "cleanup": "true"
}
```
"""
        c4 = parse_contract(md_json)
        r4 = evaluate_contract(c4, cwd=tmp_path)
        assert r4["passed"] is True, f"Case 4 failed: {r4['errors']}"
        cases_run += 1

        # 5. Markdown bullet list format
        md_bullet = """
- **Claim**: bullet proof contract
- **Surface**: CLI
- **Action**: echo "bullet_token"
- **Expect**:
  - exit_code: 0
  - stdout_contains: bullet_token
  - stderr_empty: true
- **Cleanup**: true
"""
        c5 = parse_contract(md_bullet)
        r5 = evaluate_contract(c5, cwd=tmp_path)
        assert r5["passed"] is True, f"Case 5 failed: {r5['errors']}"
        cases_run += 1

        # 6. Markdown table format
        md_table = """
| Field | Value |
| --- | --- |
| Claim | Table contract evaluation |
| Surface | CLI |
| Action | echo "table_token" |
| Expect | exit_code: 0, stdout_contains: "table_token", stderr_empty: true |
| Cleanup | true |
"""
        c6 = parse_contract(md_table)
        r6 = evaluate_contract(c6, cwd=tmp_path)
        assert r6["passed"] is True, f"Case 6 failed: {r6['errors']}"
        cases_run += 1

        # 7. Failing assertion: exit_code mismatch
        fail_exit = {
            "claim": "assert failure on exit code",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.exit(7)'",
            "expect": {"exit_code": 0},
            "cleanup": "true",
        }
        c7 = parse_contract(json.dumps(fail_exit))
        r7 = evaluate_contract(c7, cwd=tmp_path)
        assert r7["passed"] is False, "Case 7 should have failed"
        assert r7["verdict"] == "fail"
        assert any("exit_code mismatch" in err for err in r7["errors"])
        cases_run += 1

        # 8. Failing assertion: stdout_contains missing
        fail_stdout = {
            "claim": "assert failure on missing stdout",
            "surface": "echo",
            "action": "echo goodbye",
            "expect": {"exit_code": 0, "stdout_contains": ["expected_token_missing"]},
            "cleanup": "true",
        }
        c8 = parse_contract(json.dumps(fail_stdout))
        r8 = evaluate_contract(c8, cwd=tmp_path)
        assert r8["passed"] is False, "Case 8 should have failed"
        assert any("stdout missing expected substring" in err for err in r8["errors"])
        cases_run += 1

        # 9. Failing assertion: stderr_empty violation
        fail_stderr = {
            "claim": "assert failure on dirty stderr",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.stderr.write(\"unexpected warning\\n\")'",
            "expect": {"exit_code": 0, "stderr_empty": True},
            "cleanup": "true",
        }
        c9 = parse_contract(json.dumps(fail_stderr))
        r9 = evaluate_contract(c9, cwd=tmp_path)
        assert r9["passed"] is False, "Case 9 should have failed"
        assert any("stderr was not empty" in err for err in r9["errors"])
        cases_run += 1

        # 10. Action timeout handling
        timeout_contract = {
            "claim": "timeout enforcement",
            "surface": "python3",
            "action": "python3 -c 'import time; time.sleep(2)'",
            "expect": {"exit_code": 0},
            "cleanup": "true",
        }
        c10 = parse_contract(json.dumps(timeout_contract))
        r10 = evaluate_contract(c10, timeout=0.1, cwd=tmp_path)
        assert r10["passed"] is False, "Case 10 should have failed due to timeout"
        assert r10["action"]["timed_out"] is True
        assert any("timed out" in err for err in r10["errors"])
        cases_run += 1

        # 11. Guaranteed cleanup execution even on failure
        test_file = tmp_path / "scratch_flag.txt"
        cleanup_on_fail = {
            "claim": "cleanup runs on failure",
            "surface": "sh",
            "action": f"touch '{test_file}' && python3 -c 'import sys; sys.exit(3)'",
            "expect": {"exit_code": 0},
            "cleanup": f"rm -f '{test_file}'",
        }
        c11 = parse_contract(json.dumps(cleanup_on_fail))
        r11 = evaluate_contract(c11, cwd=tmp_path)
        assert r11["passed"] is False, "Action was expected to fail"
        assert r11["cleanup"]["executed"] is True
        assert r11["cleanup"]["passed"] is True
        assert not test_file.exists(), "Cleanup failed to remove the file on failure"
        cases_run += 1

        # 12. Cleanup failure handling (cleanup non-zero exit)
        cleanup_fail = {
            "claim": "cleanup error detection",
            "surface": "echo",
            "action": "echo ok",
            "expect": {"exit_code": 0},
            "cleanup": "python3 -c 'import sys; sys.exit(4)'",
        }
        c12 = parse_contract(json.dumps(cleanup_fail))
        r12 = evaluate_contract(c12, cwd=tmp_path)
        assert r12["passed"] is False, "Case 12 should have failed due to cleanup exit code"
        assert any("Cleanup command failed" in err for err in r12["errors"])
        cases_run += 1

        # 13. Falsification vector passing (adversarial test successfully rejected)
        fals_pass = """
claim: parity check
surface: python3
action: python3 -c "import sys; sys.exit(0 if 10 % 2 == 0 else 1)"
expect:
  exit_code: 0
cleanup: true
falsification_vector:
  action: python3 -c "import sys; sys.exit(0 if 11 % 2 == 0 else 1)"
"""
        c13 = parse_contract(fals_pass)
        r13 = evaluate_contract(c13, cwd=tmp_path)
        assert r13["passed"] is True, f"Case 13 failed: {r13['errors']}"
        assert r13["falsification"]["passed"] is True
        cases_run += 1

        # 14. Falsification vector failing (tautological check detected)
        fals_tautology = """
claim: tautology check
surface: python3
action: python3 -c "import sys; sys.exit(0)"
expect:
  exit_code: 0
cleanup: true
falsification_vector:
  action: python3 -c "import sys; sys.exit(0)"
"""
        c14 = parse_contract(fals_tautology)
        r14 = evaluate_contract(c14, cwd=tmp_path)
        assert r14["passed"] is False, "Case 14 should fail because falsification satisfied expect"
        assert any("tautology detected" in err for err in r14["errors"])
        cases_run += 1

        # 15. Missing required fields in contract
        incomplete_json = '{"claim": "incomplete", "action": "echo 1"}'
        try:
            parse_contract(incomplete_json)
            raise AssertionError("Incomplete contract should have raised ContractError")
        except ContractError as err:
            assert "missing required field" in str(err)
        cases_run += 1

        # 16. Non-zero expected exit code
        nonzero_expected = {
            "claim": "non-zero expected exit code",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.exit(42)'",
            "expect": {"exit_code": 42},
            "cleanup": "true",
        }
        c16 = parse_contract(json.dumps(nonzero_expected))
        r16 = evaluate_contract(c16, cwd=tmp_path)
        assert r16["passed"] is True, f"Case 16 failed: {r16['errors']}"
        assert r16["action"]["exit_code"] == 42
        cases_run += 1

        # 17. stdout_not_contains assertion passing & failing
        not_contains_pass = {
            "claim": "stdout_not_contains pass",
            "surface": "echo",
            "action": "echo 'good morning'",
            "expect": {"exit_code": 0, "stdout_not_contains": ["night"]},
            "cleanup": "true",
        }
        c17a = parse_contract(json.dumps(not_contains_pass))
        r17a = evaluate_contract(c17a, cwd=tmp_path)
        assert r17a["passed"] is True, f"Case 17a failed: {r17a['errors']}"

        not_contains_fail = {
            "claim": "stdout_not_contains fail",
            "surface": "echo",
            "action": "echo 'good night'",
            "expect": {"exit_code": 0, "stdout_not_contains": ["night"]},
            "cleanup": "true",
        }
        c17b = parse_contract(json.dumps(not_contains_fail))
        r17b = evaluate_contract(c17b, cwd=tmp_path)
        assert r17b["passed"] is False, "Case 17b should have failed"
        assert any("forbidden substring" in err for err in r17b["errors"])
        cases_run += 1

        # 18. stderr_contains assertion passing & failing
        stderr_pass = {
            "claim": "stderr_contains pass",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.stderr.write(\"specific_warning_xyz\\n\")'",
            "expect": {"exit_code": 0, "stderr_contains": ["specific_warning_xyz"]},
            "cleanup": "true",
        }
        c18a = parse_contract(json.dumps(stderr_pass))
        r18a = evaluate_contract(c18a, cwd=tmp_path)
        assert r18a["passed"] is True, f"Case 18a failed: {r18a['errors']}"

        stderr_fail = {
            "claim": "stderr_contains fail",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.stderr.write(\"other_warning\\n\")'",
            "expect": {"exit_code": 0, "stderr_contains": ["missing_warning_abc"]},
            "cleanup": "true",
        }
        c18b = parse_contract(json.dumps(stderr_fail))
        r18b = evaluate_contract(c18b, cwd=tmp_path)
        assert r18b["passed"] is False, "Case 18b should have failed"
        cases_run += 1

        # 19. stderr_empty: false assertion passing when stderr has output
        stderr_not_empty = {
            "claim": "stderr_empty false pass",
            "surface": "python3",
            "action": "python3 -c 'import sys; sys.stderr.write(\"expected diagnostic\\n\")'",
            "expect": {"exit_code": 0, "stderr_empty": False},
            "cleanup": "true",
        }
        c19 = parse_contract(json.dumps(stderr_not_empty))
        r19 = evaluate_contract(c19, cwd=tmp_path)
        assert r19["passed"] is True, f"Case 19 failed: {r19['errors']}"
        cases_run += 1

        # 20. CLI invocation with --receipt file writing
        cli_contract_file = tmp_path / "contract_cli.json"
        cli_receipt_file = tmp_path / "receipt_out.json"
        cli_contract_file.write_text(json.dumps(json_pass), encoding="utf-8")
        exit_code = main(["--receipt", str(cli_receipt_file), "--quiet", str(cli_contract_file)])
        assert exit_code == 0, "CLI run should have returned 0"
        assert cli_receipt_file.is_file(), "Receipt file should have been written"
        receipt_data = json.loads(cli_receipt_file.read_text(encoding="utf-8"))
        assert receipt_data["verdict"] == "pass"
        cases_run += 1

        # 21. CLI invocation with failing contract
        cli_fail_file = tmp_path / "contract_fail.json"
        cli_fail_file.write_text(json.dumps(fail_exit), encoding="utf-8")
        exit_code_fail = main(["--quiet", str(cli_fail_file)])
        assert exit_code_fail == 1, "CLI run on failing contract must return 1"
        cases_run += 1

        # 22. Contract-level timeout honored in CLI invocation without --timeout
        contract_with_timeout = {
            "claim": "contract-level timeout honored",
            "surface": "python3",
            "action": "python3 -c 'import time; time.sleep(2)'",
            "timeout": 0.2,
            "expect": {"exit_code": 0},
            "cleanup": "true",
        }
        cli_timeout_file = tmp_path / "contract_timeout.json"
        cli_timeout_receipt = tmp_path / "receipt_timeout.json"
        cli_timeout_file.write_text(json.dumps(contract_with_timeout), encoding="utf-8")
        exit_code_timeout = main(["--receipt", str(cli_timeout_receipt), "--quiet", str(cli_timeout_file)])
        assert exit_code_timeout == 1, "Contract with timeout=0.2s sleeping 2s must fail via CLI"
        r22 = json.loads(cli_timeout_receipt.read_text(encoding="utf-8"))
        assert r22["action"]["timed_out"] is True, "Action must be marked timed out"
        assert any("timed out" in err for err in r22["errors"])
        cases_run += 1

    print(f"eval_proof_contract self-test passed: {cases_run} cases ok")
    return 0


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic executable proof contract evaluator in pure Python 3."
    )
    parser.add_argument(
        "contract",
        nargs="?",
        help="Path to proof contract file (YAML, JSON, or Markdown), or '-' for stdin",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Timeout in seconds for action execution (default: contract timeout or 30.0)",
    )
    parser.add_argument(
        "--receipt",
        type=Path,
        help="Write structured JSON receipt to specified file path",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        help="Working directory for subprocess execution (default: current directory)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output structured JSON receipt to stdout (default behavior)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress JSON receipt output to stdout",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test suite and exit",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.contract:
        parser.print_help(sys.stderr)
        return 1

    # Read contract text
    try:
        if args.contract == "-":
            text = sys.stdin.read()
            contract_path = None
        else:
            contract_path = Path(args.contract)
            text = contract_path.read_text(encoding="utf-8")
    except OSError as err:
        err_receipt = {
            "schema": "patpat-proof-receipt/v1",
            "verdict": "fail",
            "passed": False,
            "errors": [f"Cannot read contract file: {err}"],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not args.quiet:
            print(json.dumps(err_receipt, indent=2))
        return 1

    # Parse contract
    try:
        contract = parse_contract(text, source_path=contract_path)
    except ContractError as err:
        err_receipt = {
            "schema": "patpat-proof-receipt/v1",
            "verdict": "fail",
            "passed": False,
            "errors": [f"Contract parsing error: {err}"],
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not args.quiet:
            print(json.dumps(err_receipt, indent=2))
        if args.receipt:
            args.receipt.write_text(json.dumps(err_receipt, indent=2), encoding="utf-8")
        return 1

    # Evaluate contract
    receipt = evaluate_contract(contract, timeout=args.timeout, cwd=args.cwd)

    # Output receipt
    receipt_json = json.dumps(receipt, indent=2)
    if not args.quiet:
        print(receipt_json)
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(receipt_json, encoding="utf-8")

    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
