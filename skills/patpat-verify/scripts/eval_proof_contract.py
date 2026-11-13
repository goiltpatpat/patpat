#!/usr/bin/env python3
"""Deterministic executable proof contract evaluator in pure Python 3.

Evaluates proof contracts defined in YAML, JSON, or Markdown formats against
authoritative surfaces. Enforces expectations, executes cleanup even on failure,
evaluates optional falsification vectors, and generates structured JSON receipts.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
from datetime import datetime, timezone
import io
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
DIAGNOSTIC_KEYS = (
    "contract_syntax_valid",
    "surface_accessible",
    "execution_completed",
    "exit_code_matched",
    "stdout_invariants_satisfied",
    "stderr_invariants_satisfied",
    "cleanup_succeeded",
)
DIAGNOSTIC_REMEDIATIONS: dict[str, str] = {
    "contract_syntax_valid": (
        "Provide all 5 canonical fields (claim, surface, action, expect, cleanup) "
        "in valid JSON, YAML, or Markdown contract syntax."
    ),
    "surface_accessible": "Verify the target surface command exists on PATH and is executable in cwd.",
    "execution_completed": "Increase contract timeout or resolve subprocess execution failure.",
    "exit_code_matched": "Align implementation exit status or expect.exit_code with the authoritative surface.",
    "stdout_invariants_satisfied": "Inspect stdout_contains and stdout_not_contains expectations against observed stdout.",
    "stderr_invariants_satisfied": (
        "Inspect stderr_empty, stderr_contains, and stderr_not_contains expectations against observed stderr."
    ),
    "cleanup_succeeded": "Fix cleanup command teardown so incidental artifacts exit with code 0.",
}
NOOP_CLEANUP_VALUES = frozenset({"none", "-", "—", "n/a", "null", "false", "true", ":"})


def is_noop_cleanup(cmd: str | None) -> bool:
    """Return True if a cleanup command string is absent or an explicit no-op sentinel."""
    if cmd is None:
        return True
    stripped = cmd.strip().lower()
    return not stripped or stripped in NOOP_CLEANUP_VALUES


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

def _extract_inline_expect_values(text: str, key: str) -> list[str] | None:
    """Extract inline single or bracket-list expectation values for a key on one line."""
    m = re.search(rf"\b{re.escape(key)}[ \t]*[:=][ \t]*", text, re.IGNORECASE)
    if not m:
        return None
    tail = text[m.end():]
    if not tail or tail[0] in "\r\n,;":
        return None

    if tail.startswith("["):
        depth = 0
        in_quote: str | None = None
        escaped = False
        end_idx = -1
        for idx, ch in enumerate(tail):
            if in_quote == '"':
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_quote = None
            elif in_quote == "'":
                if ch == "'":
                    in_quote = None
            else:
                if ch in ('"', "'"):
                    in_quote = ch
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        end_idx = idx
                        break
        if end_idx != -1:
            bracket_str = tail[: end_idx + 1]
            try:
                parsed = json.loads(bracket_str)
                if isinstance(parsed, list):
                    return [str(item) for item in parsed if item is not None]
            except (json.JSONDecodeError, ValueError):
                pass
            inner = tail[1:end_idx]
            items: list[str] = []
            for tok_m in re.finditer(
                r'\s*(?:"((?:[^"\\]|\\.)*)"|\'([^\']*)\'|([^,\s][^,]*?))\s*(?:,|$)',
                inner,
            ):
                if tok_m.group(1) is not None:
                    val = tok_m.group(1).replace('\\"', '"').replace("\\\\", "\\")
                    items.append(val)
                elif tok_m.group(2) is not None:
                    items.append(tok_m.group(2))
                elif tok_m.group(3) is not None:
                    token = tok_m.group(3).strip()
                    if token and token != "-":
                        items.append(token)
            return items

    if tail[0] in ('"', "'"):
        quote = tail[0]
        escaped = False
        for idx in range(1, len(tail)):
            ch = tail[idx]
            if quote == '"':
                if escaped:
                    escaped = False
                    continue
                if ch == "\\":
                    escaped = True
                    continue
            if ch == quote:
                raw_quoted = tail[: idx + 1]
                if quote == '"':
                    try:
                        val = json.loads(raw_quoted)
                        if isinstance(val, str):
                            return [val]
                    except (json.JSONDecodeError, ValueError):
                        pass
                return [tail[1:idx]]

    m_bare = re.match(r"([^\s,;]+)", tail)
    if m_bare:
        token = m_bare.group(1)
        if token != "-":
            return [token]
    return None


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

    for expect_key in (
        "stdout_contains",
        "stdout_not_contains",
        "stderr_contains",
        "stderr_not_contains",
    ):
        extracted = _extract_inline_expect_values(text, expect_key)
        if extracted is not None:
            result[expect_key] = extracted

    return result


def normalize_expectation(raw: Any) -> Expectation:
    """Normalize raw expect data into Expectation instance."""
    if raw is None:
        return Expectation(exit_code=0)

    if isinstance(raw, str):
        raw_stripped = raw.strip()
        raw_dict: Any = None
        if "\n" in raw_stripped and ":" in raw_stripped and not raw_stripped.startswith("{"):
            parsed_yaml = parse_yaml_text(raw_stripped)
            if isinstance(parsed_yaml, (dict, list)) and parsed_yaml:
                raw_dict = parsed_yaml
        if not raw_dict:
            raw_dict = parse_expectation_string(raw_stripped)
            if not raw_dict and ":" in raw_stripped and not raw_stripped.startswith("{"):
                parsed_yaml = parse_yaml_text(raw_stripped)
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


def parse_contract(text: str) -> ProofContract:
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
    if not cleanup:
        raise ContractError("cleanup field cannot be empty")

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
            encoding="utf-8",
            errors="replace",
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
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
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


def is_command_not_found(res: CommandResult) -> bool:
    """Detect command-not-found outcomes across POSIX shells (127) and Windows cmd.exe."""
    if res.exit_code == 127:
        return True
    if (
        os.name == "nt"
        and res.exit_code in (1, 9009)
        and "not recognized as an internal or external command" in res.stderr.lower()
    ):
        return True
    return False


def build_diagnostics(
    action_res: CommandResult | None,
    assertions: list[dict[str, Any]],
    contract: ProofContract,
    cleanup_rec: dict[str, Any] | None,
) -> dict[str, bool]:
    """Compute the 7 typed boolean execution diagnostics for an evaluated contract."""
    stdout_checks = [
        a for a in assertions if a.get("check") in ("stdout_contains", "stdout_not_contains")
    ]
    stderr_checks = [
        a
        for a in assertions
        if a.get("check") in ("stderr_empty", "stderr_contains", "stderr_not_contains")
    ]
    return {
        "contract_syntax_valid": True,
        "surface_accessible": (
            action_res is not None
            and (action_res.error is None or action_res.timed_out)
            and (
                contract.expect.exit_code == 127
                or not is_command_not_found(action_res)
            )
        ),
        "execution_completed": (
            action_res is not None and not action_res.timed_out and action_res.error is None
        ),
        "exit_code_matched": (
            action_res is not None and action_res.exit_code == contract.expect.exit_code
        ),
        "stdout_invariants_satisfied": (
            action_res is not None and all(bool(a.get("passed")) for a in stdout_checks)
        ),
        "stderr_invariants_satisfied": (
            action_res is not None and all(bool(a.get("passed")) for a in stderr_checks)
        ),
        "cleanup_succeeded": bool(cleanup_rec and cleanup_rec.get("passed")),
    }


def build_remediation_hint(failing_diagnostics: list[str], errors: list[str]) -> str:
    """Derive a deterministic remediation hint from failing diagnostics and errors."""
    if not failing_diagnostics and not errors:
        return ""
    hints = [
        DIAGNOSTIC_REMEDIATIONS[key]
        for key in failing_diagnostics
        if key in DIAGNOSTIC_REMEDIATIONS
    ]
    base = " ".join(hints)
    if errors:
        err_summary = "; ".join(errors[:3])
        if base:
            return f"{base} Details: {err_summary}"
        return f"Resolve verification failure: {err_summary}"
    return base


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
            f_cleanup_res: CommandResult | None = None
            f_cleanup_ok = True
            f_cleanup_cmd = f_vec.cleanup.strip() if f_vec.cleanup else ""
            if not is_noop_cleanup(f_cleanup_cmd):
                f_cleanup_res = execute_subprocess(f_cleanup_cmd, timeout=eff_timeout, cwd=cwd)
                f_cleanup_ok = (
                    f_cleanup_res.exit_code == 0
                    and not f_cleanup_res.timed_out
                    and f_cleanup_res.error is None
                )

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

            if f_cleanup_res is not None and not f_cleanup_ok:
                f_passed = False
                if f_cleanup_res.timed_out:
                    errors.append(f"Falsification cleanup timed out after {eff_timeout} seconds")
                elif f_cleanup_res.error:
                    errors.append(f"Falsification cleanup execution error: {f_cleanup_res.error}")
                else:
                    errors.append(
                        f"Falsification cleanup command failed with exit code {f_cleanup_res.exit_code}: "
                        f"{f_cleanup_res.stderr.strip()}"
                    )

            falsification_rec = {
                "action": f_vec.action,
                "exit_code": f_res.exit_code,
                "passed": f_passed,
                "duration_ms": round(f_res.duration_ms, 2),
                "timed_out": f_res.timed_out,
            }
            if f_cleanup_res is not None:
                falsification_rec["cleanup_exit_code"] = f_cleanup_res.exit_code
                falsification_rec["cleanup_passed"] = f_cleanup_ok

    finally:
        # Step 4: GUARANTEED CLEANUP EXECUTION (runs even if action fails or times out)
        cleanup_cmd = contract.cleanup.strip() if contract.cleanup else ""
        if not is_noop_cleanup(cleanup_cmd):
            c_res = execute_subprocess(cleanup_cmd, timeout=eff_timeout, cwd=cwd)
            cleanup_ok = (c_res.exit_code == 0 and not c_res.timed_out and c_res.error is None)
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
                if c_res.timed_out:
                    errors.append(f"Cleanup command timed out after {eff_timeout} seconds")
                elif c_res.error:
                    errors.append(f"Cleanup execution error: {c_res.error}")
                else:
                    errors.append(f"Cleanup command failed with exit code {c_res.exit_code}: {c_res.stderr.strip()}")
        else:
            cleanup_rec = {
                "executed": False,
                "command": cleanup_cmd or "none",
                "passed": True,
            }

    diagnostics = build_diagnostics(action_res, assertions, contract, cleanup_rec)
    failing_diagnostics = [key for key, ok in diagnostics.items() if not ok]
    remediation_hint = build_remediation_hint(failing_diagnostics, errors)

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
        "diagnostics": diagnostics,
        "failing_diagnostics": failing_diagnostics,
        "remediation_hint": remediation_hint,
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

    def py_cmd(code: str) -> str:
        exe = sys.executable
        if os.name == "nt":
            prefix = f'call "{exe}"' if " " in exe else exe
            return f'{prefix} -c "{code}"'
        return f"{shlex.quote(exe)} -c {shlex.quote(code)}"

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
        yaml_pass = (
            "claim: arithmetic proof\n"
            "surface: python\n"
            "action: |\n"
            f"  {py_cmd('print(21 * 2)')}\n"
            "expect:\n"
            "  exit_code: 0\n"
            "  stdout_contains:\n"
            '    - "42"\n'
            "  stderr_empty: true\n"
            "cleanup: true\n"
        )
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
action: echo fence_test_output
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
        md_json_obj = {
            "claim": "markdown json fence",
            "surface": "python",
            "action": py_cmd("import sys; sys.stdout.write('json_token')"),
            "expect": {
                "exit_code": 0,
                "stdout_contains": ["json_token"],
                "stderr_empty": True,
            },
            "cleanup": "true",
        }
        md_json = f"# Contract Document\n```json\n{json.dumps(md_json_obj, indent=2)}\n```\n"
        c4 = parse_contract(md_json)
        r4 = evaluate_contract(c4, cwd=tmp_path)
        assert r4["passed"] is True, f"Case 4 failed: {r4['errors']}"
        cases_run += 1

        # 5. Markdown bullet list format
        md_bullet = """
- **Claim**: bullet proof contract
- **Surface**: CLI
- **Action**: echo bullet_token
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
| Action | echo table_token |
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
            "surface": "python",
            "action": py_cmd("import sys; sys.exit(7)"),
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
            "surface": "python",
            "action": py_cmd("import sys; sys.stderr.write('unexpected warning\\n')"),
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
            "surface": "python",
            "action": py_cmd("import time; time.sleep(2)"),
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
            "surface": "python",
            "action": py_cmd(
                f"from pathlib import Path; import sys; Path({test_file.name!r}).write_text('x', encoding='utf-8'); sys.exit(3)"
            ),
            "expect": {"exit_code": 0},
            "cleanup": py_cmd(
                f"from pathlib import Path; Path({test_file.name!r}).unlink(missing_ok=True)"
            ),
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
            "cleanup": py_cmd("import sys; sys.exit(4)"),
        }
        c12 = parse_contract(json.dumps(cleanup_fail))
        r12 = evaluate_contract(c12, cwd=tmp_path)
        assert r12["passed"] is False, "Case 12 should have failed due to cleanup exit code"
        assert any("Cleanup command failed" in err for err in r12["errors"])
        cases_run += 1

        # 13. Falsification vector passing (adversarial test successfully rejected)
        fals_pass = (
            "claim: parity check\n"
            "surface: python\n"
            f"action: {json.dumps(py_cmd('import sys; sys.exit(0 if 10 % 2 == 0 else 1)'))}\n"
            "expect:\n"
            "  exit_code: 0\n"
            "cleanup: true\n"
            "falsification_vector:\n"
            f"  action: {json.dumps(py_cmd('import sys; sys.exit(0 if 11 % 2 == 0 else 1)'))}\n"
        )
        c13 = parse_contract(fals_pass)
        r13 = evaluate_contract(c13, cwd=tmp_path)
        assert r13["passed"] is True, f"Case 13 failed: {r13['errors']}"
        assert r13["falsification"]["passed"] is True
        cases_run += 1

        # 14. Falsification vector failing (tautological check detected)
        fals_tautology = (
            "claim: tautology check\n"
            "surface: python\n"
            f"action: {json.dumps(py_cmd('import sys; sys.exit(0)'))}\n"
            "expect:\n"
            "  exit_code: 0\n"
            "cleanup: true\n"
            "falsification_vector:\n"
            f"  action: {json.dumps(py_cmd('import sys; sys.exit(0)'))}\n"
        )
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
            "surface": "python",
            "action": py_cmd("import sys; sys.exit(42)"),
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
            "action": "echo good morning",
            "expect": {"exit_code": 0, "stdout_not_contains": ["night"]},
            "cleanup": "true",
        }
        c17a = parse_contract(json.dumps(not_contains_pass))
        r17a = evaluate_contract(c17a, cwd=tmp_path)
        assert r17a["passed"] is True, f"Case 17a failed: {r17a['errors']}"

        not_contains_fail = {
            "claim": "stdout_not_contains fail",
            "surface": "echo",
            "action": "echo good night",
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
            "surface": "python",
            "action": py_cmd("import sys; sys.stderr.write('specific_warning_xyz\\n')"),
            "expect": {"exit_code": 0, "stderr_contains": ["specific_warning_xyz"]},
            "cleanup": "true",
        }
        c18a = parse_contract(json.dumps(stderr_pass))
        r18a = evaluate_contract(c18a, cwd=tmp_path)
        assert r18a["passed"] is True, f"Case 18a failed: {r18a['errors']}"

        stderr_fail = {
            "claim": "stderr_contains fail",
            "surface": "python",
            "action": py_cmd("import sys; sys.stderr.write('other_warning\\n')"),
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
            "surface": "python",
            "action": py_cmd("import sys; sys.stderr.write('expected diagnostic\\n')"),
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
            "surface": "python",
            "action": py_cmd("import time; time.sleep(2)"),
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

        # 23. Diagnostics: passing contract sets all 7 booleans True, empty failing_diagnostics & remediation_hint
        assert set(r1["diagnostics"].keys()) == set(DIAGNOSTIC_KEYS)
        assert all(r1["diagnostics"][k] is True for k in DIAGNOSTIC_KEYS), f"Expected all True: {r1['diagnostics']}"
        assert r1["failing_diagnostics"] == []
        assert r1["remediation_hint"] == ""
        cases_run += 1

        # 24. Diagnostics: exit_code mismatch isolates exit_code_matched == False
        assert r7["diagnostics"]["contract_syntax_valid"] is True
        assert r7["diagnostics"]["surface_accessible"] is True
        assert r7["diagnostics"]["execution_completed"] is True
        assert r7["diagnostics"]["exit_code_matched"] is False
        assert r7["diagnostics"]["stdout_invariants_satisfied"] is True
        assert r7["diagnostics"]["stderr_invariants_satisfied"] is True
        assert r7["diagnostics"]["cleanup_succeeded"] is True
        assert r7["failing_diagnostics"] == ["exit_code_matched"]
        assert "exit_code mismatch" in r7["remediation_hint"]
        cases_run += 1

        # 25. Diagnostics: stdout failure isolates stdout_invariants_satisfied == False (contains & not_contains)
        assert r8["diagnostics"]["exit_code_matched"] is True
        assert r8["diagnostics"]["stdout_invariants_satisfied"] is False
        assert r8["diagnostics"]["stderr_invariants_satisfied"] is True
        assert r8["failing_diagnostics"] == ["stdout_invariants_satisfied"]
        assert "stdout" in r8["remediation_hint"].lower()
        assert r17b["diagnostics"]["stdout_invariants_satisfied"] is False
        assert r17b["failing_diagnostics"] == ["stdout_invariants_satisfied"]
        cases_run += 1

        # 26. Diagnostics: stderr failure isolates stderr_invariants_satisfied == False (stderr_empty & stderr_contains)
        assert r9["diagnostics"]["exit_code_matched"] is True
        assert r9["diagnostics"]["stdout_invariants_satisfied"] is True
        assert r9["diagnostics"]["stderr_invariants_satisfied"] is False
        assert r9["failing_diagnostics"] == ["stderr_invariants_satisfied"]
        assert "stderr" in r9["remediation_hint"].lower()
        assert r18b["diagnostics"]["stderr_invariants_satisfied"] is False
        assert r18b["failing_diagnostics"] == ["stderr_invariants_satisfied"]
        cases_run += 1

        # 27. Diagnostics: timeout sets surface_accessible True, execution_completed False, exit_code_matched False
        assert r10["diagnostics"]["contract_syntax_valid"] is True
        assert r10["diagnostics"]["surface_accessible"] is True
        assert r10["diagnostics"]["execution_completed"] is False
        assert r10["diagnostics"]["exit_code_matched"] is False
        assert r10["diagnostics"]["cleanup_succeeded"] is True
        assert "execution_completed" in r10["failing_diagnostics"]
        assert "exit_code_matched" in r10["failing_diagnostics"]
        assert "timeout" in r10["remediation_hint"].lower()
        cases_run += 1

        # 28. Diagnostics: cleanup failure isolates cleanup_succeeded == False
        assert r12["diagnostics"]["contract_syntax_valid"] is True
        assert r12["diagnostics"]["surface_accessible"] is True
        assert r12["diagnostics"]["execution_completed"] is True
        assert r12["diagnostics"]["exit_code_matched"] is True
        assert r12["diagnostics"]["stdout_invariants_satisfied"] is True
        assert r12["diagnostics"]["stderr_invariants_satisfied"] is True
        assert r12["diagnostics"]["cleanup_succeeded"] is False
        assert r12["failing_diagnostics"] == ["cleanup_succeeded"]
        assert "cleanup" in r12["remediation_hint"].lower()
        cases_run += 1

        # 29. Diagnostics: inaccessible surface (command not found) sets surface_accessible == False
        missing_surface = {
            "claim": "detect inaccessible surface command",
            "surface": "nonexistent_cmd",
            "action": "patpat_nonexistent_binary_99999",
            "expect": {"exit_code": 0},
            "cleanup": "true",
        }
        c29 = parse_contract(json.dumps(missing_surface))
        r29 = evaluate_contract(c29, cwd=tmp_path)
        assert r29["passed"] is False
        assert r29["diagnostics"]["contract_syntax_valid"] is True
        assert r29["diagnostics"]["surface_accessible"] is False
        assert r29["diagnostics"]["exit_code_matched"] is False
        assert "surface_accessible" in r29["failing_diagnostics"]
        assert r29["remediation_hint"]
        cases_run += 1

        # 30. Diagnostics: CLI --json ContractError emits all-False diagnostics and failing_diagnostics=["contract_syntax_valid"]
        bad_contract_file = tmp_path / "malformed_contract.json"
        bad_contract_file.write_text('{"claim": "missing fields only"}', encoding="utf-8")
        bad_receipt_file = tmp_path / "nested" / "malformed_receipt.json"
        stdout_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf):
            bad_exit = main(["--json", "--receipt", str(bad_receipt_file), str(bad_contract_file)])
        assert bad_exit == 1, "Malformed contract CLI invocation must return 1"
        cli_err_receipt = json.loads(stdout_buf.getvalue())
        assert cli_err_receipt["schema"] == "patpat-proof-receipt/v1"
        assert cli_err_receipt["passed"] is False
        assert set(cli_err_receipt["diagnostics"].keys()) == set(DIAGNOSTIC_KEYS)
        assert all(cli_err_receipt["diagnostics"][k] is False for k in DIAGNOSTIC_KEYS)
        assert cli_err_receipt["failing_diagnostics"] == ["contract_syntax_valid"]
        assert "5 canonical fields" in cli_err_receipt["remediation_hint"]
        assert bad_receipt_file.is_file()
        assert json.loads(bad_receipt_file.read_text(encoding="utf-8"))["failing_diagnostics"] == ["contract_syntax_valid"]
        cases_run += 1

        # 31. Diagnostics: expect.exit_code == 127 passes cleanly with all 7 diagnostics True
        exit_127_expected = {
            "claim": "expected exit code 127 passes cleanly",
            "surface": "python",
            "action": py_cmd("import sys; sys.exit(127)"),
            "expect": {"exit_code": 127},
            "cleanup": "true",
        }
        c31 = parse_contract(json.dumps(exit_127_expected))
        r31 = evaluate_contract(c31, cwd=tmp_path)
        assert r31["passed"] is True, f"Case 31 failed: {r31['errors']}"
        assert r31["verdict"] == "pass"
        assert all(r31["diagnostics"][k] is True for k in DIAGNOSTIC_KEYS), f"Expected all True: {r31['diagnostics']}"
        assert r31["failing_diagnostics"] == []
        assert r31["remediation_hint"] == ""
        cases_run += 1

        # 32. Subprocess UTF-8 decoding with replacement on invalid byte sequences
        utf8_contract = {
            "claim": "non-ASCII UTF-8 and replacement handling",
            "surface": "python",
            "action": py_cmd("import sys; sys.stdout.buffer.write(b'utf8-\\xc3\\xa9-bad-\\xff\\n')"),
            "expect": {"exit_code": 0, "stdout_contains": ["utf8-\u00e9-bad-\ufffd"]},
            "cleanup": "true",
        }
        c32 = parse_contract(json.dumps(utf8_contract))
        r32 = evaluate_contract(c32, cwd=tmp_path)
        assert r32["passed"] is True, f"Case 32 failed: {r32['errors']}"
        assert all(r32["diagnostics"][k] is True for k in DIAGNOSTIC_KEYS)
        cases_run += 1

        # 33. Empty and whitespace-only cleanup field rejection
        for empty_cleanup in ("", "   "):
            empty_cleanup_json = json.dumps(
                {
                    "claim": "empty cleanup rejection",
                    "surface": "echo",
                    "action": "echo ok",
                    "expect": {"exit_code": 0},
                    "cleanup": empty_cleanup,
                }
            )
            try:
                parse_contract(empty_cleanup_json)
                raise AssertionError(f"Expected ContractError for cleanup={empty_cleanup!r}")
            except ContractError as err:
                assert "cleanup field cannot be empty" in str(err)

        empty_md_cleanup = (
            "## Claim\nempty cleanup markdown\n\n"
            "## Surface\necho\n\n"
            "## Action\necho ok\n\n"
            "## Expect\nexit_code: 0\n\n"
            "## Cleanup\n   \n"
        )
        try:
            parse_contract(empty_md_cleanup)
            raise AssertionError("Expected ContractError for blank markdown ## Cleanup")
        except ContractError as err:
            assert "cleanup field cannot be empty" in str(err)
        cases_run += 1

        # 34. Unified no-op cleanup handling for primary and falsification_vector.cleanup
        for noop_val in NOOP_CLEANUP_VALUES:
            assert is_noop_cleanup(noop_val) is True
        assert is_noop_cleanup("true") is True
        assert is_noop_cleanup("none") is True
        assert is_noop_cleanup(py_cmd("import sys; sys.exit(0)")) is False

        noop_fals_contract = {
            "claim": "falsification noop cleanup equivalence",
            "surface": "python",
            "action": py_cmd("print('primary_ok')"),
            "expect": {"exit_code": 0, "stdout_contains": ["primary_ok"]},
            "cleanup": "null",
            "falsification_vector": {
                "action": py_cmd("import sys; sys.exit(1)"),
                "cleanup": "true",
            },
        }
        c34 = parse_contract(json.dumps(noop_fals_contract))
        r34 = evaluate_contract(c34, cwd=tmp_path)
        assert r34["passed"] is True, f"Case 34 failed: {r34['errors']}"
        assert r34["cleanup"]["executed"] is False
        assert r34["falsification"]["passed"] is True
        assert "cleanup_exit_code" not in r34["falsification"]
        assert "cleanup_passed" not in r34["falsification"]
        cases_run += 1

        # 35. Executed falsification_vector.cleanup: failing cleanup fails contract, passing succeeds
        fail_fals_cleanup = {
            "claim": "failing falsification cleanup fails contract",
            "surface": "python",
            "action": py_cmd("print('primary_ok')"),
            "expect": {"exit_code": 0, "stdout_contains": ["primary_ok"]},
            "cleanup": "true",
            "falsification_vector": {
                "action": py_cmd("import sys; sys.exit(1)"),
                "cleanup": py_cmd("import sys; sys.exit(3)"),
            },
        }
        c35a = parse_contract(json.dumps(fail_fals_cleanup))
        r35a = evaluate_contract(c35a, cwd=tmp_path)
        assert r35a["passed"] is False, "Case 35a should fail when falsification cleanup fails"
        assert r35a["verdict"] == "fail"
        assert r35a["falsification"]["passed"] is False
        assert r35a["falsification"]["cleanup_exit_code"] == 3
        assert r35a["falsification"]["cleanup_passed"] is False
        assert any("Falsification cleanup command failed with exit code 3" in e for e in r35a["errors"])
        assert r35a["remediation_hint"]

        pass_fals_cleanup = {
            "claim": "passing falsification cleanup succeeds",
            "surface": "python",
            "action": py_cmd("print('primary_ok')"),
            "expect": {"exit_code": 0, "stdout_contains": ["primary_ok"]},
            "cleanup": "true",
            "falsification_vector": {
                "action": py_cmd("import sys; sys.exit(1)"),
                "cleanup": py_cmd("import sys; sys.exit(0)"),
            },
        }
        c35b = parse_contract(json.dumps(pass_fals_cleanup))
        r35b = evaluate_contract(c35b, cwd=tmp_path)
        assert r35b["passed"] is True, f"Case 35b failed: {r35b['errors']}"
        assert r35b["falsification"]["passed"] is True
        assert r35b["falsification"]["cleanup_exit_code"] == 0
        assert r35b["falsification"]["cleanup_passed"] is True
        cases_run += 1

        # 36. Multiline YAML ## Expect parsing with stdout_contains & stdout_not_contains
        action36_pass = py_cmd("print('ok_alpha\\nok_beta')")
        action36_fail = py_cmd("print('ok_alpha\\nok_beta\\nforbidden_err')")
        multiline_md_pass = (
            "## Claim\nmultiline yaml expect pass\n\n"
            "## Surface\npython\n\n"
            f"## Action\n{action36_pass}\n\n"
            "## Expect\n"
            "exit_code: 0\n"
            "stdout_contains:\n"
            "  - ok_alpha\n"
            "  - ok_beta\n"
            "stdout_not_contains:\n"
            "  - forbidden_err\n"
            "stderr_empty: true\n\n"
            "## Cleanup\ntrue\n"
        )
        c36a = parse_contract(multiline_md_pass)
        assert c36a.expect.stdout_contains == ["ok_alpha", "ok_beta"], c36a.expect.stdout_contains
        assert c36a.expect.stdout_not_contains == ["forbidden_err"], c36a.expect.stdout_not_contains
        r36a = evaluate_contract(c36a, cwd=tmp_path)
        assert r36a["passed"] is True, f"Case 36a failed: {r36a['errors']}"

        multiline_md_fail = multiline_md_pass.replace(action36_pass, action36_fail)
        c36b = parse_contract(multiline_md_fail)
        r36b = evaluate_contract(c36b, cwd=tmp_path)
        assert r36b["passed"] is False, "Case 36b should fail when stdout_not_contains matches"
        assert r36b["diagnostics"]["stdout_invariants_satisfied"] is False
        cases_run += 1

        # 37. Inline parse_expectation_string support for stdout_not_contains, stderr_contains, stderr_not_contains
        parsed_no_bullet = parse_expectation_string("exit_code: 0\nstdout_contains:\n  - ok")
        assert parsed_no_bullet == {"exit_code": 0}, f"Unexpected bullet capture: {parsed_no_bullet}"

        action37_pass = py_cmd("import sys; print('good_out'); sys.stderr.write('soft_warn\\n')")
        action37_fail_stdout = py_cmd("import sys; print('bad'); sys.stderr.write('soft_warn\\n')")
        action37_fail_stderr = py_cmd("import sys; print('good_out'); sys.stderr.write('soft_warn fatal\\n')")
        inline_table = (
            "| Field | Value |\n"
            "| --- | --- |\n"
            "| Claim | inline expect invariants |\n"
            "| Surface | python |\n"
            f"| Action | {action37_pass} |\n"
            '| Expect | exit_code: 0, stdout_not_contains: "bad", stderr_contains: [soft_warn], stderr_not_contains: [fatal, panic] |\n'
            "| Cleanup | true |\n"
        )
        c37a = parse_contract(inline_table)
        assert c37a.expect.stdout_not_contains == ["bad"]
        assert c37a.expect.stderr_contains == ["soft_warn"]
        assert c37a.expect.stderr_not_contains == ["fatal", "panic"]
        r37a = evaluate_contract(c37a, cwd=tmp_path)
        assert r37a["passed"] is True, f"Case 37a failed: {r37a['errors']}"

        inline_fail_table = inline_table.replace(action37_pass, action37_fail_stdout)
        c37b = parse_contract(inline_fail_table)
        r37b = evaluate_contract(c37b, cwd=tmp_path)
        assert r37b["passed"] is False, "Case 37b should fail on inline stdout_not_contains"
        assert r37b["diagnostics"]["stdout_invariants_satisfied"] is False

        inline_stderr_fail = inline_table.replace(action37_pass, action37_fail_stderr)
        c37c = parse_contract(inline_stderr_fail)
        r37c = evaluate_contract(c37c, cwd=tmp_path)
        assert r37c["passed"] is False, "Case 37c should fail on inline stderr_not_contains"
        assert r37c["diagnostics"]["stderr_invariants_satisfied"] is False
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
            reconfigure = getattr(sys.stdin, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except (OSError, ValueError):
                    pass
            text = sys.stdin.read()
        else:
            contract_path = Path(args.contract)
            text = contract_path.read_text(encoding="utf-8")
    except OSError as err:
        diagnostics = {key: False for key in DIAGNOSTIC_KEYS}
        failing_diagnostics = ["surface_accessible"]
        errors = [f"Cannot read contract file: {err}"]
        err_receipt = {
            "schema": "patpat-proof-receipt/v1",
            "verdict": "fail",
            "passed": False,
            "diagnostics": diagnostics,
            "failing_diagnostics": failing_diagnostics,
            "remediation_hint": build_remediation_hint(failing_diagnostics, errors),
            "errors": errors,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not args.quiet:
            print(json.dumps(err_receipt, indent=2))
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(err_receipt, indent=2), encoding="utf-8")
        return 1

    # Parse contract
    try:
        contract = parse_contract(text)
    except ContractError as err:
        diagnostics = {key: False for key in DIAGNOSTIC_KEYS}
        failing_diagnostics = ["contract_syntax_valid"]
        errors = [f"Contract parsing error: {err}"]
        err_receipt = {
            "schema": "patpat-proof-receipt/v1",
            "verdict": "fail",
            "passed": False,
            "diagnostics": diagnostics,
            "failing_diagnostics": failing_diagnostics,
            "remediation_hint": build_remediation_hint(failing_diagnostics, errors),
            "errors": errors,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }
        if not args.quiet:
            print(json.dumps(err_receipt, indent=2))
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
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
