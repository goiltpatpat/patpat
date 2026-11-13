#!/usr/bin/env python3
"""Deterministic AST linter enforcing patpat-unslop rules 12/16, 19, and 20.

Pure Python 3 standard library with zero external dependencies.

Rule 12/16 (apologetic or conversational AI commentary):
- Conversational or apologetic AI markers in # and // comments while preserving
  legitimate engineering comments (e.g. upstream workarounds, temporary fixes).

Rule 19 (structural code inflation):
- Single-caller pass-through wrappers (trivial forwarding functions).
- Silent broad exception swallowing (except Exception: pass, except: pass without re-raise).

Rule 20 (anti-reward-hacking and verifier integrity):
- Test-skipping annotations (@pytest.mark.skip, @unittest.skip, etc.) and skip calls.
- Warning and linter suppressions (# noqa, // eslint-disable, #pragma warning disable, etc.).
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import tokenize
from typing import Sequence

PYTHON_EXTENSIONS = frozenset({".py"})
JS_TS_EXTENSIONS = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
SUPPORTED_EXTENSIONS = PYTHON_EXTENSIONS | JS_TS_EXTENSIONS


@dataclass(frozen=True)
class Violation:
    file_path: str
    line: int
    col: int
    rule: str  # "Rule 12/16", "Rule 19", or "Rule 20"
    category: str
    message: str
    end_line: int | None = None

    def format_diagnostic(self) -> str:
        return f"{self.file_path}:{self.line}:{self.col}: [{self.rule}] {self.category}: {self.message}"

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file_path,
            "line": self.line,
            "col": self.col,
            "rule": self.rule,
            "category": self.category,
            "message": self.message,
            "end_line": self.end_line or self.line,
        }


# Rule 12/16 conversational/apologetic AI comment marker patterns
AI_SLOP_COMMENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(?:I\s+apologize|apologies\s+for)\b", re.IGNORECASE), "conversational apology"),
    (re.compile(r"\b(?:sorry\s+for\s+the|I(?:'m|\s+am)\s+sorry)\b", re.IGNORECASE), "conversational apology"),
    (re.compile(r"\bas\s+an\s+AI\b", re.IGNORECASE), "AI persona marker"),
    (re.compile(r"\bAI[- ]generated\b", re.IGNORECASE), "AI-generated marker"),
    (
        re.compile(
            r"\bgenerated\s+(?:by|with)\s+(?:claude|chatgpt|openai|gemini|grok|copilot|codex|patpat|llm)\b",
            re.IGNORECASE,
        ),
        "AI attribution marker",
    ),
    (re.compile(r"^Patpat:(?:\s|$)", re.IGNORECASE), "Patpat conversational prefix"),
    (re.compile(r"^Certainly[!.,](?:\s|$)", re.IGNORECASE), "sycophantic conversational opener"),
    (re.compile(r"\bI(?:'d|\s+would)\s+be\s+happy\s+to\b", re.IGNORECASE), "sycophantic conversational phrase"),
    (re.compile(r"\bYou(?:'re|\s+are)\s+absolutely\s+right\b", re.IGNORECASE), "sycophantic conversational phrase"),
]


# Rule 20 JS/TS // suppression patterns (matched against comment body after '//')
JS_SUPPRESSION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^pragma\s+warning\s+disable\b", re.IGNORECASE), "pragma warning disable"),
    (re.compile(r"^eslint-disable\b", re.IGNORECASE), "eslint-disable"),
    (re.compile(r"^@ts-(?:ignore|nocheck)\b", re.IGNORECASE), "@ts-ignore/nocheck"),
]

# Rule 20 suppression comment patterns (matched against # comments via tokenize)
SUPPRESSION_COMMENT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^#+\s*noqa\b", re.IGNORECASE), "noqa"),
    (re.compile(r"^#+\s*type:\s*ignore\b", re.IGNORECASE), "type: ignore"),
    (re.compile(r"^#+\s*pylint:\s*disable\b", re.IGNORECASE), "pylint: disable"),
    (re.compile(r"^#+\s*pyright:\s*ignore\b", re.IGNORECASE), "pyright: ignore"),
    (re.compile(r"^#+\s*mypy:\s*ignore\b", re.IGNORECASE), "mypy: ignore"),
    (re.compile(r"^(?:#+|//)\s*(?://\s*)?pragma\s+warning\s+disable\b", re.IGNORECASE), "pragma warning disable"),
    (re.compile(r"^(?:#+|//)\s*(?://\s*)?eslint-disable\b", re.IGNORECASE), "eslint-disable"),
    (re.compile(r"^(?:#+|//)\s*(?://\s*)?@ts-(?:ignore|nocheck)\b", re.IGNORECASE), "@ts-ignore/nocheck"),
    (re.compile(r"^#+\s*nosemgrep\b", re.IGNORECASE), "nosemgrep"),
]

# Rule 20 test-skipping decorator names
TEST_SKIP_DECORATOR_NAMES = {
    "pytest.mark.skip",
    "pytest.mark.skipif",
    "unittest.skip",
    "unittest.skipIf",
    "unittest.skipUnless",
    "skip",
    "skipIf",
    "skipUnless",
}

# Rule 20 test-skipping call names
TEST_SKIP_CALL_NAMES = {
    "pytest.skip",
    "test.skip",
    "it.skip",
}


def get_decorator_name(dec: ast.expr) -> str:
    """Extract string representation of decorator path."""
    if isinstance(dec, ast.Name):
        return dec.id
    if isinstance(dec, ast.Attribute):
        parent = get_decorator_name(dec.value)
        return f"{parent}.{dec.attr}" if parent else dec.attr
    if isinstance(dec, ast.Call):
        return get_decorator_name(dec.func)
    return ""


def get_call_name(func: ast.expr) -> str:
    """Extract callable name representation."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = get_call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    return ""


def is_broad_exception_type(exc_type: ast.AST | None) -> tuple[bool, str]:
    """Determine whether an except clause catches a broad exception."""
    if exc_type is None:
        return True, "bare 'except:'"
    if isinstance(exc_type, ast.Name):
        if exc_type.id in ("Exception", "BaseException"):
            return True, f"'except {exc_type.id}:'"
    elif isinstance(exc_type, ast.Attribute):
        if exc_type.attr in ("Exception", "BaseException"):
            return True, f"'except ...{exc_type.attr}:'"
    elif isinstance(exc_type, ast.Tuple):
        broad_items = []
        for elt in exc_type.elts:
            is_broad, desc = is_broad_exception_type(elt)
            if is_broad:
                broad_items.append(desc)
        if broad_items:
            return True, f"caught tuple containing {', '.join(broad_items)}"
    return False, ""


def handler_has_raise(handler: ast.ExceptHandler) -> bool:
    """Check if the except handler contains a raise statement outside inner function/class defs."""
    nodes_to_visit = list(handler.body)
    while nodes_to_visit:
        curr = nodes_to_visit.pop()
        if isinstance(curr, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(curr, ast.Raise):
            return True
        nodes_to_visit.extend(ast.iter_child_nodes(curr))
    return False


def check_broad_exceptions(tree: ast.AST, file_path: str) -> list[Violation]:
    """Rule 19: detect silent broad exception swallowing."""
    violations: list[Violation] = []
    for node in ast.walk(tree):
        handlers = []
        if isinstance(node, ast.Try):
            handlers = node.handlers
        elif hasattr(ast, "TryStar") and isinstance(node, getattr(ast, "TryStar")):
            handlers = node.handlers

        for handler in handlers:
            is_broad, desc = is_broad_exception_type(handler.type)
            if is_broad and not handler_has_raise(handler):
                end_line = getattr(handler, "end_lineno", handler.lineno)
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=handler.lineno,
                        col=handler.col_offset + 1,
                        rule="Rule 19",
                        category="broad-exception-swallowing",
                        message=f"broad exception caught ({desc}) and swallowed without re-raise",
                        end_line=end_line,
                    )
                )
    return violations


def is_trivial_forwarding_function(
    fn: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[bool, str]:
    """Check if function is a trivial pass-through wrapper forwarding to another callable."""
    # Exclude magic / dunder methods
    if fn.name.startswith("__") and fn.name.endswith("__"):
        return False, ""

    # Exclude abstract methods and typing overloads
    for dec in fn.decorator_list:
        dec_name = get_decorator_name(dec)
        if any(dec_name.endswith(ex) for ex in ("abstractmethod", "overload", "override")):
            return False, ""

    # Strip leading docstring if present
    body = fn.body
    if body and isinstance(body[0], ast.Expr):
        val = body[0].value
        if isinstance(val, ast.Constant) and isinstance(val.value, str):
            body = body[1:]

    # Trivial wrapper must have exactly one statement
    if len(body) != 1:
        return False, ""

    stmt = body[0]
    call_expr = None
    if isinstance(stmt, ast.Return) and stmt.value is not None:
        call_expr = stmt.value
    elif isinstance(stmt, ast.Expr) and stmt.value is not None:
        call_expr = stmt.value
    else:
        return False, ""

    if isinstance(call_expr, ast.Await):
        call_expr = call_expr.value

    if not isinstance(call_expr, ast.Call):
        return False, ""

    target = call_expr.func
    target_name = ""
    target_receiver: str | None = None
    if isinstance(target, ast.Name):
        target_name = target.id
    elif isinstance(target, ast.Attribute):
        target_name = target.attr
        if isinstance(target.value, ast.Name):
            target_receiver = target.value.id
    else:
        return False, ""

    # Avoid flagging recursive calls as forwarding wrappers
    if target_name == fn.name:
        return False, ""

    # Analyze function parameters
    pos_params = [a.arg for a in fn.args.posonlyargs + fn.args.args]
    vararg = fn.args.vararg.arg if fn.args.vararg else None
    kwonly_params = [a.arg for a in fn.args.kwonlyargs]
    kwarg = fn.args.kwarg.arg if fn.args.kwarg else None

    # Handle method self/cls receiver
    if pos_params and pos_params[0] in ("self", "cls"):
        receiver_name = pos_params[0]
        if target_receiver == receiver_name:
            forward_pos_params = pos_params[1:]
        elif (
            call_expr.args
            and isinstance(call_expr.args[0], ast.Name)
            and call_expr.args[0].id == receiver_name
        ):
            forward_pos_params = pos_params
        else:
            forward_pos_params = pos_params[1:]
    else:
        forward_pos_params = pos_params

    # Check trivial argument forwarding patterns:
    # Pattern 1: Pure variadic forwarding (*args, **kwargs)
    if vararg and kwarg and not forward_pos_params and not kwonly_params:
        if len(call_expr.args) == 1 and isinstance(call_expr.args[0], ast.Starred):
            star_val = call_expr.args[0].value
            if isinstance(star_val, ast.Name) and star_val.id == vararg:
                if len(call_expr.keywords) == 1 and call_expr.keywords[0].arg is None:
                    kw_val = call_expr.keywords[0].value
                    if isinstance(kw_val, ast.Name) and kw_val.id == kwarg:
                        return True, target_name

    # Pattern 2: Matching positional parameters
    if len(call_expr.args) == len(forward_pos_params):
        all_pos_match = True
        for c_arg, p_name in zip(call_expr.args, forward_pos_params):
            if not (isinstance(c_arg, ast.Name) and c_arg.id == p_name):
                all_pos_match = False
                break
        if all_pos_match:
            if not call_expr.keywords and not kwonly_params and not kwarg:
                return True, target_name

            all_kw_match = True
            for kw in call_expr.keywords:
                if kw.arg is None:
                    if kwarg and isinstance(kw.value, ast.Name) and kw.value.id == kwarg:
                        continue
                    all_kw_match = False
                    break
                else:
                    if kw.arg in kwonly_params and isinstance(kw.value, ast.Name) and kw.value.id == kw.arg:
                        continue
                    all_kw_match = False
                    break
            expected_kw_count = len(kwonly_params) + (1 if kwarg and any(k.arg is None for k in call_expr.keywords) else 0)
            if all_kw_match and len(call_expr.keywords) == expected_kw_count:
                return True, target_name

    # Pattern 3: Positional parameters forwarded as keywords (e.g. target(a=a, b=b))
    if not call_expr.args and len(call_expr.keywords) == len(forward_pos_params) + len(kwonly_params):
        all_kw_match = True
        for kw in call_expr.keywords:
            if kw.arg and (kw.arg in forward_pos_params or kw.arg in kwonly_params):
                if isinstance(kw.value, ast.Name) and kw.value.id == kw.arg:
                    continue
            all_kw_match = False
            break
        if all_kw_match:
            return True, target_name

    return False, ""


def count_function_references(
    trees: Sequence[ast.AST], func_name: str, def_node: ast.AST
) -> int:
    """Count calls and references to func_name across the given ASTs outside def_node."""
    count = 0
    for tree in trees:
        for node in ast.walk(tree):
            if node is def_node:
                continue
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
                continue
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == func_name:
                    count += 1
                elif isinstance(node.func, ast.Attribute) and node.func.attr == func_name:
                    count += 1
    return count


def check_passthrough_wrappers(
    tree: ast.AST, file_path: str, all_trees: Sequence[ast.AST] | None = None
) -> list[Violation]:
    """Rule 19: detect single-caller pass-through wrappers (trivial forwarding functions)."""
    violations: list[Violation] = []
    search_trees = all_trees if all_trees is not None else [tree]

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        is_wrapper, target_name = is_trivial_forwarding_function(node)
        if not is_wrapper:
            continue

        caller_count = count_function_references(search_trees, node.name, node)
        # Single-caller condition: called at most once in the analyzed scope
        if caller_count <= 1:
            end_line = getattr(node, "end_lineno", node.lineno)
            violations.append(
                Violation(
                    file_path=file_path,
                    line=node.lineno,
                    col=node.col_offset + 1,
                    rule="Rule 19",
                    category="single-caller-wrapper",
                    message=(
                        f"single-caller pass-through wrapper '{node.name}' trivially forwards "
                        f"to '{target_name}' (call count: {caller_count})"
                    ),
                    end_line=end_line,
                )
            )
    return violations


def check_test_skipping(tree: ast.AST, file_path: str) -> list[Violation]:
    """Rule 20: detect test-skipping annotations and calls."""
    violations: list[Violation] = []
    for node in ast.walk(tree):
        # Check annotations/decorators
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                dec_name = get_decorator_name(dec)
                if dec_name in TEST_SKIP_DECORATOR_NAMES or any(
                    dec_name.startswith(f"{prefix}.") for prefix in ("pytest.mark.skip", "unittest.skip")
                ):
                    end_line = getattr(dec, "end_lineno", dec.lineno)
                    violations.append(
                        Violation(
                            file_path=file_path,
                            line=dec.lineno,
                            col=dec.col_offset + 1,
                            rule="Rule 20",
                            category="test-skipping-annotation",
                            message=f"test-skipping annotation '@{dec_name}' silences verifier integrity",
                            end_line=end_line,
                        )
                    )

        # Check skip calls
        if isinstance(node, ast.Call):
            call_name = get_call_name(node.func)
            if call_name in TEST_SKIP_CALL_NAMES or call_name.endswith(".skipTest"):
                end_line = getattr(node, "end_lineno", node.lineno)
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=node.lineno,
                        col=node.col_offset + 1,
                        rule="Rule 20",
                        category="test-skipping-call",
                        message=f"test-skipping call '{call_name}(...)' silences verifier integrity",
                        end_line=end_line,
                    )
                )
    return violations


def _collect_python_token_ranges(
    source_bytes: bytes,
) -> tuple[list[tuple[tuple[int, int], tuple[int, int]]], list[tuple[int, int, str]], int]:
    """Tokenize Python bytes into (protected_ranges, comment_tokens, last_tokenized_line)."""
    protected_ranges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    comment_tokens: list[tuple[int, int, str]] = []
    last_tokenized_line = 0
    try:
        for tok in tokenize.tokenize(io.BytesIO(source_bytes).readline):
            last_tokenized_line = max(last_tokenized_line, tok.end[0])
            if tok.type in (tokenize.STRING, tokenize.COMMENT):
                protected_ranges.append((tok.start, tok.end))
            if tok.type == tokenize.COMMENT:
                comment_tokens.append((tok.start[0], tok.start[1] + 1, tok.string))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return protected_ranges, comment_tokens, last_tokenized_line
    return protected_ranges, comment_tokens, last_tokenized_line


def extract_js_line_comments(source_text: str) -> list[tuple[int, int, str]]:
    """Extract // line comments as (1-based line, 1-based col, body) skipping strings and /* ... */."""
    comments: list[tuple[int, int, str]] = []
    n = len(source_text)
    i = 0
    line = 1
    col = 1
    state = "NORMAL"
    url_scheme_re = re.compile(
        r"(?:^|[\s=\"'(\[,])(?:https?|ftp|file|wss?|ssh|git):$",
        re.IGNORECASE,
    )

    while i < n:
        ch = source_text[i]
        nxt = source_text[i + 1] if i + 1 < n else ""

        if state == "NORMAL":
            if ch == "/" and nxt == "/":
                line_start = source_text.rfind("\n", 0, i) + 1
                prefix = source_text[line_start:i]
                if not url_scheme_re.search(prefix):
                    end = source_text.find("\n", i + 2)
                    if end == -1:
                        end = n
                    body = source_text[i + 2 : end].rstrip("\r").strip()
                    comments.append((line, col, body))
                    i = end
                    continue
            if ch == "/" and nxt == "*":
                state = "BLOCK"
                i += 2
                col += 2
                continue
            if ch == "'":
                state = "SINGLE"
            elif ch == '"':
                state = "DOUBLE"
            elif ch == "`":
                state = "TEMPLATE"
        elif state == "BLOCK":
            if ch == "*" and nxt == "/":
                state = "NORMAL"
                i += 2
                col += 2
                continue
        elif state in ("SINGLE", "DOUBLE", "TEMPLATE"):
            if ch == "\\":
                if i + 1 < n and source_text[i + 1] == "\n":
                    line += 1
                    col = 1
                    i += 2
                    continue
                i += 2
                col += 2
                continue
            if (
                (state == "SINGLE" and ch == "'")
                or (state == "DOUBLE" and ch == '"')
                or (state == "TEMPLATE" and ch == "`")
            ):
                state = "NORMAL"

        if ch == "\n":
            line += 1
            col = 1
        else:
            col += 1
        i += 1

    return comments


def _pos_in_ranges(
    line_no: int, col0: int, ranges: Sequence[tuple[tuple[int, int], tuple[int, int]]]
) -> bool:
    pos = (line_no, col0)
    for start, end in ranges:
        if start <= pos < end:
            return True
    return False


def _iter_comments(source_bytes: bytes, file_path: str) -> list[tuple[int, int, str, bool]]:
    """Collect deduplicated (# and //) comments as (line, col_1, text, is_js)."""
    source_text = source_bytes.decode("utf-8", errors="replace")
    is_js_ts = Path(file_path).suffix.lower() in JS_TS_EXTENSIONS
    protected_ranges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    seen_lines: set[int] = set()
    comments: list[tuple[int, int, str, bool]] = []

    if not is_js_ts:
        protected_ranges, comment_tokens, last_tokenized_line = _collect_python_token_ranges(source_bytes)
        for line_no, col_1, comment_text in comment_tokens:
            if line_no not in seen_lines:
                comments.append((line_no, col_1, comment_text, False))
                seen_lines.add(line_no)
        lines = source_text.splitlines()
        if last_tokenized_line < len(lines):
            for idx, line in enumerate(lines, start=1):
                if idx <= last_tokenized_line or idx in seen_lines:
                    continue
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    comments.append((idx, (len(line) - len(stripped)) + 1, stripped, False))
                    seen_lines.add(idx)

    for line_no, col_1, body in extract_js_line_comments(source_text):
        if line_no in seen_lines:
            continue
        if not is_js_ts and _pos_in_ranges(line_no, col_1 - 1, protected_ranges):
            continue
        comments.append((line_no, col_1, body, True))
        seen_lines.add(line_no)

    return comments


def check_suppression_comments(source_bytes: bytes, file_path: str) -> list[Violation]:
    """Rule 20: detect warning and linter suppression comments in # and // comments."""
    violations: list[Violation] = []
    for line_no, col_1, text, is_js in _iter_comments(source_bytes, file_path):
        patterns = JS_SUPPRESSION_PATTERNS if is_js else SUPPRESSION_COMMENT_PATTERNS
        for pattern, label in patterns:
            if pattern.search(text):
                violations.append(
                    Violation(
                        file_path=file_path,
                        line=line_no,
                        col=col_1,
                        rule="Rule 20",
                        category="linter-suppression",
                        message=f"linter/warning suppression '{label}' silences checker integrity",
                        end_line=line_no,
                    )
                )
                break
    return violations


def _match_ai_slop_comment(comment_body: str) -> str | None:
    for pattern, label in AI_SLOP_COMMENT_PATTERNS:
        if pattern.search(comment_body):
            return label
    return None


def check_ai_slop_comments(source_bytes: bytes, file_path: str) -> list[Violation]:
    """Rule 12/16: detect conversational or apologetic AI markers in # and // comments only."""
    violations: list[Violation] = []
    for line_no, col_1, text, is_js in _iter_comments(source_bytes, file_path):
        body = text if is_js else text.lstrip("#").strip()
        label = _match_ai_slop_comment(body)
        if label is not None:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=line_no,
                    col=col_1,
                    rule="Rule 12/16",
                    category="ai-conversational-slop",
                    message=f"conversational/AI marker ({label}) in comment violates code comment discipline",
                    end_line=line_no,
                )
            )
    return violations


def parse_unified_diff(diff_text: str) -> dict[str, set[int]]:
    """Parse unified diff text into a map of target filename -> added/modified line numbers."""
    added_lines: dict[str, set[int]] = {}
    current_file: str | None = None
    current_new_line = 0

    hunk_header = re.compile(r"^@@\s+-[0-9]+(?:,[0-9]+)?\s+\+([0-9]+)(?:,[0-9]+)?\s+@@")

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            raw_path = line[4:].strip().replace("\\", "/")
            if raw_path == "/dev/null":
                current_file = None
                continue
            if raw_path.startswith("b/"):
                raw_path = raw_path[2:]
            current_file = raw_path
            if current_file not in added_lines:
                added_lines[current_file] = set()
        elif line.startswith("@@ ") and current_file:
            match = hunk_header.match(line)
            if match:
                current_new_line = int(match.group(1))
        elif current_file is not None:
            if line.startswith("+") and not line.startswith("+++"):
                added_lines[current_file].add(current_new_line)
                current_new_line += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass
            elif line.startswith("\\"):
                pass
            else:
                current_new_line += 1

    return added_lines


def _finalize_violations(
    violations: list[Violation],
    allowed_lines: set[int] | None,
) -> list[Violation]:
    violations.sort(key=lambda v: (v.line, v.col, v.category))
    if allowed_lines is not None:
        filtered: list[Violation] = []
        for v in violations:
            span = set(range(v.line, (v.end_line or v.line) + 1))
            if span.intersection(allowed_lines):
                filtered.append(v)
        return filtered
    return violations


def check_source_code(
    source: str,
    file_path: str,
    all_sources: Sequence[str] | None = None,
    allowed_lines: set[int] | None = None,
) -> list[Violation]:
    """Check a Python or JS/TS source string against Rules 12/16, 19, and 20."""
    source_bytes = source.encode("utf-8")
    violations: list[Violation] = []
    violations.extend(check_suppression_comments(source_bytes, file_path))
    violations.extend(check_ai_slop_comments(source_bytes, file_path))

    if Path(file_path).suffix.lower() in JS_TS_EXTENSIONS:
        return _finalize_violations(violations, allowed_lines)

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as err:
        if not violations:
            violations.append(
                Violation(
                    file_path=file_path,
                    line=err.lineno or 1,
                    col=err.offset or 1,
                    rule="Syntax",
                    category="syntax-error",
                    message=f"Python syntax error: {err.msg}",
                    end_line=err.lineno or 1,
                )
            )
        return _finalize_violations(violations, allowed_lines)

    all_trees = None
    if all_sources is not None:
        all_trees = []
        for s in all_sources:
            try:
                all_trees.append(ast.parse(s))
            except SyntaxError:
                pass

    violations.extend(check_broad_exceptions(tree, file_path))
    violations.extend(check_passthrough_wrappers(tree, file_path, all_trees))
    violations.extend(check_test_skipping(tree, file_path))

    return _finalize_violations(violations, allowed_lines)


def collect_target_files(
    paths: Sequence[Path],
    extensions: frozenset[str] = SUPPORTED_EXTENSIONS,
) -> list[Path]:
    """Recursively collect supported source files from given paths, ignoring hidden/build folders."""
    ignore_dirs = {".git", ".venv", "venv", "__pycache__", ".tox", ".eggs", "build", "dist", "node_modules"}
    results: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix.lower() in extensions:
            results.append(path)
        elif path.is_dir():
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
                for f in sorted(files):
                    if Path(f).suffix.lower() in extensions:
                        results.append(Path(root) / f)
    return results


def check_diff_content(diff_text: str, root: Path | None = None) -> list[Violation]:
    """Run linter against files and line numbers specified in unified diff."""
    base_root = root or Path.cwd()
    added_lines_map = parse_unified_diff(diff_text)
    violations: list[Violation] = []

    for rel_path, added_lines in sorted(added_lines_map.items()):
        if Path(rel_path).suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        file_path = base_root / rel_path
        if file_path.is_file():
            source = file_path.read_text(encoding="utf-8", errors="replace")
            violations.extend(check_source_code(source, file_path.as_posix(), allowed_lines=added_lines))
        else:
            # Synthetic reconstruction from patch added lines if file not on disk
            hunk_lines: list[str] = []
            is_in_file = False
            for line in diff_text.splitlines():
                if line.startswith("+++ "):
                    target = line[4:].strip().replace("\\", "/")
                    if target.startswith("b/"):
                        target = target[2:]
                    is_in_file = (target == rel_path)
                elif is_in_file:
                    if line.startswith("+") and not line.startswith("+++"):
                        hunk_lines.append(line[1:])
                    elif line.startswith("@@ ") or line.startswith("diff "):
                        if line.startswith("diff "):
                            is_in_file = False
            synthetic_source = "\n".join(hunk_lines)
            if synthetic_source.strip():
                violations.extend(check_source_code(synthetic_source, rel_path))

    return violations


def _read_utf8_stdin() -> str:
    reconfigure = getattr(sys.stdin, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
    return sys.stdin.read()


def run_checks(
    paths: Sequence[Path], diff_file: str | None = None, root: Path | None = None
) -> list[Violation]:
    """Run all linter checks based on provided CLI inputs."""
    if diff_file is not None:
        if diff_file == "-":
            diff_text = _read_utf8_stdin()
        else:
            diff_text = Path(diff_file).read_text(encoding="utf-8", errors="replace")
        return check_diff_content(diff_text, root=root)

    target_files = collect_target_files(paths)
    if not target_files and not paths and not sys.stdin.isatty():
        stdin_source = _read_utf8_stdin()
        return check_source_code(stdin_source, "<stdin>")

    all_python_sources: list[str] = []
    file_contents: list[tuple[Path, str]] = []
    for f in target_files:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
            file_contents.append((f, content))
            if f.suffix.lower() in PYTHON_EXTENSIONS:
                all_python_sources.append(content)
        except OSError as err:
            sys.stderr.write(f"Warning: could not read {f}: {err}\n")

    violations: list[Violation] = []
    for file_path, content in file_contents:
        all_src = all_python_sources if file_path.suffix.lower() in PYTHON_EXTENSIONS else None
        violations.extend(
            check_source_code(
                content,
                file_path.as_posix(),
                all_sources=all_src,
            )
        )
    return violations


def run_self_test() -> int:
    """Run comprehensive self-tests verifying deterministic detection and zero false-positives."""
    test_cases_run = 0

    def assert_test(condition: bool, msg: str) -> None:
        nonlocal test_cases_run
        test_cases_run += 1
        if not condition:
            raise AssertionError(f"Self-test failed: {msg}")

    # --- Rule 19: Broad Exception Swallowing ---
    # 1. Broad exception swallowed with pass -> Must flag
    code = "try:\n    do_work()\nexcept Exception:\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "except Exception: pass flagged")

    # 2. Bare except swallowed with pass -> Must flag
    code = "try:\n    do_work()\nexcept:\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "bare except: pass flagged")

    # 3. BaseException swallowed with pass -> Must flag
    code = "try:\n    do_work()\nexcept BaseException:\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "except BaseException: pass flagged")

    # 4. Caught tuple containing Exception -> Must flag
    code = "try:\n    do_work()\nexcept (ValueError, Exception):\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "except (ValueError, Exception) flagged")

    # 5. Broad exception with ellipsis (...) -> Must flag
    code = "try:\n    do_work()\nexcept Exception:\n    ...\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "except Exception: ... flagged")

    # 6. Broad exception logged but no re-raise -> Must flag
    code = "try:\n    do_work()\nexcept Exception as e:\n    print(e)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "except Exception logging without raise flagged")

    # 7. Broad exception with re-raise -> MUST NOT flag (negative case)
    code = "try:\n    do_work()\nexcept Exception as e:\n    logger.error(e)\n    raise\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "except Exception with re-raise not flagged")

    # 8. Broad exception wrapped in new exception -> MUST NOT flag (negative case)
    code = "try:\n    do_work()\nexcept Exception as e:\n    raise CustomError('wrapped') from e\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "except Exception with raise from e not flagged")

    # 9. Specific exception swallowed (ValueError) -> MUST NOT flag (negative case)
    code = "try:\n    do_work()\nexcept ValueError:\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "specific except ValueError: pass not flagged")

    # 10. Specific exception (FileNotFoundError) -> MUST NOT flag (negative case)
    code = "try:\n    f = open('absent')\nexcept FileNotFoundError:\n    return None\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "specific except FileNotFoundError not flagged")

    # --- Rule 19: Single-caller pass-through wrappers ---
    # 11. Single-caller wrapper forwarding positional params -> Must flag
    code = "def wrapper(a, b):\n    return target(a, b)\n\nwrapper(1, 2)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "single-caller positional wrapper flagged")

    # 12. Single-caller wrapper forwarding variadics -> Must flag
    code = "def delegate(*args, **kwargs):\n    return target(*args, **kwargs)\n\ndelegate(1)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "single-caller variadic wrapper flagged")

    # 13. Method forwarding to self._target -> Must flag
    code = "class Client:\n    def call(self, x):\n        return self._call(x)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "method forwarding to self._call flagged")

    # 14. Zero callers defined in snippet -> Must flag (candidate uncalled wrapper)
    code = "def unused_wrapper(a, b):\n    return real_target(a, b)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "zero-caller forwarding wrapper flagged")

    # 15. Multi-caller wrapper (called 2 times) -> MUST NOT flag (negative case)
    code = "def shared_wrapper(x):\n    return target(x)\n\nshared_wrapper(1)\nshared_wrapper(2)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "multi-caller wrapper (2 callers) not flagged")

    # 16. Function modifying arguments -> MUST NOT flag (negative case)
    code = "def transform(x):\n    return target(x + 1)\n\ntransform(1)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "function transforming argument not flagged")

    # 17. Function with multiple statements -> MUST NOT flag (negative case)
    code = "def multi_step(x):\n    validate(x)\n    return target(x)\n\nmulti_step(1)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "multi-statement function not flagged")

    # 18. Property getter returning attribute -> MUST NOT flag (negative case)
    code = "class Foo:\n    @property\n    def bar(self):\n        return self._bar\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "property getter returning attribute not flagged")

    # 19. Abstract method -> MUST NOT flag (negative case)
    code = "from abc import abstractmethod\nclass Foo:\n    @abstractmethod\n    def bar(self, x):\n        pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "abstractmethod not flagged")

    # --- Rule 20: Test-skipping annotations and calls ---
    # 20. @pytest.mark.skip -> Must flag
    code = "@pytest.mark.skip(reason='broken')\ndef test_something():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "@pytest.mark.skip flagged")

    # 21. Bare @pytest.mark.skip -> Must flag
    code = "@pytest.mark.skip\ndef test_something():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "bare @pytest.mark.skip flagged")

    # 22. @pytest.mark.skipif -> Must flag
    code = "@pytest.mark.skipif(condition, reason='platform')\ndef test_platform():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "@pytest.mark.skipif flagged")

    # 23. @unittest.skip -> Must flag
    code = "@unittest.skip('not ready')\ndef test_unit():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "@unittest.skip flagged")

    # 24. pytest.skip() call -> Must flag
    code = "def test_dynamic():\n    pytest.skip('dynamic skip')\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-call", "pytest.skip() call flagged")

    # 25. self.skipTest() call -> Must flag
    code = "def test_dynamic(self):\n    self.skipTest('skip test')\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-call", "self.skipTest() call flagged")

    # 26. @pytest.mark.parametrize -> MUST NOT flag (negative case)
    code = "@pytest.mark.parametrize('x', [1, 2])\ndef test_param(x):\n    assert x > 0\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "@pytest.mark.parametrize not flagged")

    # 27. Normal test function -> MUST NOT flag (negative case)
    code = "def test_clean():\n    assert 1 + 1 == 2\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "normal test not flagged")

    # --- Rule 20: Suppression comments ---
    # 28. # noqa -> Must flag
    code = "x = 1  # noqa\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# noqa flagged")

    # 29. # noqa: E501 -> Must flag
    code = "x = 1  # noqa: E501\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# noqa: E501 flagged")

    # 30. # type: ignore -> Must flag
    code = "x: int = 'bad'  # type: ignore\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# type: ignore flagged")

    # 31. # pylint: disable=... -> Must flag
    code = "# pylint: disable=broad-except\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# pylint: disable flagged")

    # 32. // eslint-disable -> Must flag
    code = "// eslint-disable-next-line\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "// eslint-disable flagged")

    # 33. #pragma warning disable -> Must flag
    code = "#pragma warning disable 104\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "#pragma warning disable flagged")

    # 34. Prose comment mentioning noqa -> MUST NOT flag (negative case)
    code = "# Note: do not introduce noqa comments in this module\nx = 1\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "prose comment mentioning noqa not flagged")

    # 35. String literal containing '# noqa' in docstring -> MUST NOT flag (negative case)
    code = "'''\nExample usage:\n  # noqa: E501\n'''\nx = 1\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "string literal containing # noqa not flagged")

    # --- Unified Diff filtering ---
    # 36. Diff parser identifies added lines
    diff_sample = """--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,4 @@
 def existing():
     pass
+x = 1  # noqa
"""
    diff_map = parse_unified_diff(diff_sample)
    assert_test("src/app.py" in diff_map and 12 in diff_map["src/app.py"], "diff parser identifies added line 12")

    # 37. Diff filtering flags added violation but ignores unchanged line violation
    full_source = "x = 1  # noqa\ndef clean():\n    return 42\ny = 2  # noqa\n"
    # only line 3 was added in diff:
    v_diff = check_source_code(full_source, "src/app.py", allowed_lines={3})
    assert_test(len(v_diff) == 0, "line 1 and 4 ignored when only line 3 allowed")
    v_diff_hit = check_source_code(full_source, "src/app.py", allowed_lines={4})
    assert_test(len(v_diff_hit) == 1 and v_diff_hit[0].line == 4, "line 4 flagged when in allowed_lines")

    # 38. Synthetic diff check without files on disk
    v_synth = check_diff_content(diff_sample)
    assert_test(len(v_synth) == 1 and v_synth[0].category == "linter-suppression", "synthetic diff check flagged")

    # --- Additional Edge Cases ---
    # 39. Async pass-through wrapper -> Must flag
    code = "async def forward(x):\n    return await target(x)\n\nawait forward(1)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "async pass-through wrapper flagged")

    # 40. Non-returning call wrapper (ast.Expr) -> Must flag
    code = "def log_forward(msg):\n    send_log(msg)\n\nlog_forward('hello')\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "non-returning call wrapper flagged")

    # 41. Forwarding wrapper with docstring -> Must flag
    code = "def documented(x):\n    '''Trivial wrapper docstring.'''\n    return target(x)\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "single-caller-wrapper", "documented wrapper flagged")

    # 42. Bare except with raise -> MUST NOT flag (negative case)
    code = "try:\n    work()\nexcept:\n    clean_up()\n    raise\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 0, "bare except with raise not flagged")

    # 43. 1-element tuple exception (Exception,) -> Must flag
    code = "try:\n    work()\nexcept (Exception,):\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "broad-exception-swallowing", "1-element tuple exception flagged")

    # 44. @unittest.skipUnless -> Must flag
    code = "@unittest.skipUnless(sys.platform == 'win32', 'windows only')\ndef test_win():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "@unittest.skipUnless flagged")

    # 45. @skipIf -> Must flag
    code = "@skipIf(True, 'broken')\ndef test_broken():\n    pass\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "test-skipping-annotation", "@skipIf flagged")

    # 46. # type: ignore[arg-type] -> Must flag
    code = "x = calc('str')  # type: ignore[arg-type]\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# type: ignore[arg-type] flagged")

    # 47. # pyright: ignore[reportUnused] -> Must flag
    code = "unused_var = 1  # pyright: ignore[reportUnused]\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# pyright: ignore flagged")

    # 48. # nosemgrep -> Must flag
    code = "eval(code)  # nosemgrep: dangerous-eval\n"
    v = check_source_code(code, "test.py")
    assert_test(len(v) == 1 and v[0].category == "linter-suppression", "# nosemgrep flagged")

    # 49. Clean file returns 0 violations
    clean_code = "def add(a: int, b: int) -> int:\n    return a + b\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    v_clean = check_source_code(clean_code, "clean.py")
    assert_test(len(v_clean) == 0, "clean code produces zero violations")

    # --- Rule 12/16: Conversational / apologetic AI comment markers ---
    # 50. Apologetic # comment -> Must flag
    code = "# I apologize for this quick patch\nx = 1\n"
    v = check_source_code(code, "test.py")
    assert_test(
        len(v) == 1 and v[0].rule == "Rule 12/16" and v[0].category == "ai-conversational-slop",
        "apologetic # comment flagged",
    )

    # 51. AI persona marker in # comment -> Must flag
    code = "x = 1  # as an AI, I kept the fallback\n"
    v = check_source_code(code, "test.py")
    assert_test(
        len(v) == 1 and v[0].rule == "Rule 12/16" and v[0].category == "ai-conversational-slop",
        "AI persona # comment flagged",
    )

    # 52. Synthetic marker strings and agent attribution comments -> Must flag
    for marker in (
        "# AI-generated helper\nx = 1\n",
        "# generated by claude\nx = 1\n",
        "# Generated by chatgpt\nx = 1\n",
        "# generated by openai\nx = 1\n",
        "# generated by gemini\nx = 1\n",
        "# generated by grok\nx = 1\n",
        "# generated by copilot\nx = 1\n",
        "# generated by codex\nx = 1\n",
        "# generated by patpat\nx = 1\n",
        "# generated by llm\nx = 1\n",
        "# Patpat: fixed the bug\nx = 1\n",
        "# sorry for the messy code\nx = 1\n",
    ):
        v_m = check_source_code(marker, "test.py")
        assert_test(
            len(v_m) == 1 and v_m[0].category == "ai-conversational-slop",
            f"marker flagged: {marker.splitlines()[0]}",
        )

    # 53. // line comment markers (standalone and trailing) -> Must flag
    v_c1 = check_source_code("// I apologize for the workaround\n", "test.js")
    assert_test(
        len(v_c1) == 1 and v_c1[0].rule == "Rule 12/16" and v_c1[0].category == "ai-conversational-slop",
        "standalone // marker flagged",
    )
    v_c2 = check_source_code("const val = 1; // AI-generated stub\n", "test.ts")
    assert_test(
        len(v_c2) == 1 and v_c2[0].category == "ai-conversational-slop",
        "trailing // marker flagged",
    )

    # 54. Negative cases: legitimate engineering comments -> MUST NOT flag
    legit_comments = (
        "# workaround for upstream issue #123\nx = 1\n",
        "# temporary fix until v2\nx = 1\n",
        "# Generated by scripts/stage_plugin.py\nx = 1\n",
        "# Normalize /patpat:patpat paths across adapters\nx = 1\n",
        "url = 'https://example.com'  # endpoint\n",
        "quotient = total // count\n",
    )
    for sample in legit_comments:
        v_legit = check_source_code(sample, "test.py")
        assert_test(len(v_legit) == 0, f"legitimate code/comment not flagged: {sample.strip()}")

    # 55. Negative case: AI marker text inside string literals / docstrings -> MUST NOT flag
    string_sample = '"""\n# I apologize inside docstring\n// as an AI inside docstring\n"""\nmsg = "# Patpat: string"\n'
    assert_test(len(check_source_code(string_sample, "test.py")) == 0, "markers inside strings not flagged")
    assert_test(len(check_ai_slop_comments(b'const s = "// I apologize";\n', "test.js")) == 0, "quoted // string not flagged")

    # 56. Diff mode (allowed_lines) filtering for # and // comments
    diff_py = "# I apologize\nx = 1\n# sorry for the delay\n"
    v_py_diff = check_source_code(diff_py, "test.py", allowed_lines={3})
    assert_test(len(v_py_diff) == 1 and v_py_diff[0].line == 3, "allowed_lines filters # slop comments")
    diff_js = "// I apologize\nconst x = 1;\n// sorry for the delay\n"
    v_js_diff = check_source_code(diff_js, "test.js", allowed_lines={3})
    assert_test(len(v_js_diff) == 1 and v_js_diff[0].line == 3, "allowed_lines filters // slop comments")

    # 57. Inline foo();// marker, block comment exclusion, and JS suppression comments
    v_inline = check_source_code("foo();// I apologize\n", "app.ts")
    assert_test(
        len(v_inline) == 1 and v_inline[0].category == "ai-conversational-slop" and v_inline[0].col == 7,
        "inline foo();// slop marker flagged",
    )
    v_block = check_source_code("/* // I apologize */\n/* multi\n * // eslint-disable-next-line\n */\n", "app.ts")
    assert_test(len(v_block) == 0, "block comment containing // markers not flagged")
    v_js_supp = check_source_code("foo();// @ts-ignore\nclass Foo { #noqa = 1; }\n", "app.ts")
    assert_test(
        len(v_js_supp) == 1 and v_js_supp[0].category == "linter-suppression" and v_js_supp[0].line == 1,
        "inline JS // @ts-ignore flagged without false positive on JS #privateField",
    )

    # 58. parse_unified_diff ignores '\ No newline at end of file' markers
    no_nl_diff = (
        "--- a/src/app.ts\n"
        "+++ b/src/app.ts\n"
        "@@ -1,2 +1,2 @@\n"
        "-const a = 1;\n"
        "\\ No newline at end of file\n"
        "+const a = 2; // I apologize\n"
        "\\ No newline at end of file\n"
    )
    no_nl_map = parse_unified_diff(no_nl_diff)
    assert_test(no_nl_map.get("src/app.ts") == {1}, "no-newline marker does not shift diff line numbers")

    # 59. check_diff_content and CLI path collection for .ts/.js files
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        ts_file = tmp_root / "src" / "widget.ts"
        ts_file.parent.mkdir(parents=True, exist_ok=True)
        ts_file.write_text(
            "// existing clean comment\nexport function run() { return 1; }\nfoo();// sorry for the hack\n// @ts-ignore\n",
            encoding="utf-8",
        )
        ts_diff = (
            "--- a/src/widget.ts\n"
            "+++ b/src/widget.ts\n"
            "@@ -1,2 +1,4 @@\n"
            " // existing clean comment\n"
            " export function run() { return 1; }\n"
            "+foo();// sorry for the hack\n"
            "+// @ts-ignore\n"
        )
        v_ts_diff = check_diff_content(ts_diff, root=tmp_root)
        assert_test(
            len(v_ts_diff) == 2
            and {x.category for x in v_ts_diff} == {"ai-conversational-slop", "linter-suppression"}
            and {x.line for x in v_ts_diff} == {3, 4},
            "check_diff_content scans .ts files with allowed_lines filtering",
        )
        v_ts_synth = check_diff_content(no_nl_diff, root=tmp_root)
        assert_test(
            len(v_ts_synth) == 1 and v_ts_synth[0].category == "ai-conversational-slop",
            "synthetic .ts diff content scanned cleanly without Python ast.parse",
        )
        js_file = tmp_root / "src" / "helper.mjs"
        js_file.write_text("export const ok = 1;\n", encoding="utf-8")
        collected = collect_target_files([tmp_root])
        assert_test(ts_file in collected and js_file in collected, "collect_target_files includes .ts and .mjs")
        cli_hits = run_checks([tmp_root])
        assert_test(len(cli_hits) == 2, "run_checks scans JS/TS files collected from directory")

    print(f"unslop_ast_check self-test passed: {test_cases_run} test cases.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="unslop_ast_check.py",
        description="Deterministic AST and comment linter enforcing patpat-unslop rules 12/16, 19, and 20.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Source files or directories to check (.py, .js, .jsx, .ts, .tsx, .mjs, .cjs)",
    )
    parser.add_argument(
        "--diff",
        nargs="?",
        const="-",
        default=None,
        metavar="DIFF_PATH",
        help="Check only files and added lines in unified diff (pass '-' or omit argument for stdin)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Repository root for relative diff resolution",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run comprehensive self-tests and exit",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output diagnostic format (default: text)",
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress summary output on success",
    )

    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    violations = run_checks(args.paths, diff_file=args.diff, root=args.root)

    if args.format == "json":
        payload = {
            "status": "FAIL" if violations else "PASS",
            "violation_count": len(violations),
            "violations": [v.to_dict() for v in violations],
        }
        print(json.dumps(payload, indent=2))
    else:
        for v in violations:
            print(v.format_diagnostic())
        if violations:
            print(f"Found {len(violations)} violation(s) enforcing rules 12/16, 19, and 20.", file=sys.stderr)
        elif not args.quiet:
            print("Patpat unslop AST check passed: zero violations found.")

    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
