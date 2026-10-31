#!/usr/bin/env python3
"""Pure-Python AST symbol extractor and ranked dependency indexer for Patpat workspace mapping.

Extracts key structural symbols (classes, functions, interfaces, entrypoints) from workspace source
files using Python standard library only (ast, re, pathlib). Ranks symbols by reference in-degree
centrality and enforces a strict token budget (< 1,200 tokens) to prevent context window bloat.
Zero external dependencies.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, NamedTuple


IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    ".gemini",
    ".cursor",
    ".vscode",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".coverage",
    "coverage",
    "htmlcov",
    ".patpat",
}

MAX_FILE_BYTES = 512 * 1024  # 512 KiB per file scan limit
DEFAULT_TOKEN_BUDGET = 1200
DEFAULT_MAX_PER_FILE = 3  # Diversity cap: prevent monolith files from monopolizing the budget
ESTIMATED_CHARS_PER_TOKEN = 4  # Standard heuristic: ~4 chars per token

# Pure-Python standard library detection (Python 3.10+ built-in sys.stdlib_module_names)
STDLIB_MODULES: frozenset[str] = getattr(
    sys,
    "stdlib_module_names",
    frozenset(
        {
            "os", "sys", "re", "json", "ast", "math", "time", "pathlib", "typing",
            "subprocess", "collections", "argparse", "shutil", "tempfile", "stat",
            "io", "copy", "functools", "itertools", "dataclasses", "unittest",
        }
    ),
)


class ExtractedSymbol(NamedTuple):
    name: str
    kind: str  # "class", "function", "interface", "entrypoint", "manifest"
    file_path: str
    line: int
    signature: str
    docstring: str | None
    references: list[str]


def is_safe_subpath(root: Path, target: Path) -> bool:
    """Ensure path is within root without escaping or traversing symlinks."""
    try:
        resolved_root = root.resolve(strict=True)
        resolved_target = target.resolve(strict=True)
        resolved_target.relative_to(resolved_root)
        return True
    except (ValueError, OSError):
        return False


def extract_python_symbols(content: str, rel_path: str) -> list[ExtractedSymbol]:
    """Extract top-level and class-level symbols from Python source using standard ast."""
    symbols: list[ExtractedSymbol] = []
    try:
        tree = ast.parse(content, filename=rel_path)
    except SyntaxError:
        return symbols

    module_refs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod_name = alias.name.split(".")[0]
                if mod_name not in STDLIB_MODULES:
                    module_refs.append(mod_name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mod_name = node.module.split(".")[0]
            if mod_name not in STDLIB_MODULES:
                module_refs.append(mod_name)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            doc = ast.get_docstring(node)
            first_line_doc = doc.strip().splitlines()[0] if doc else None
            bases = [ast.unparse(b) for b in node.bases if hasattr(ast, "unparse")]
            sig = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"
            methods = [
                m.name for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
            ]
            if methods:
                sig += f" [{', '.join(methods[:5])}{'...' if len(methods) > 5 else ''}]"
            symbols.append(
                ExtractedSymbol(
                    name=node.name,
                    kind="class",
                    file_path=rel_path,
                    line=node.lineno,
                    signature=sig,
                    docstring=first_line_doc[:120] if first_line_doc else None,
                    references=module_refs,
                )
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("_") and not node.name.startswith("__"):
                continue  # skip internal helpers for compact indexing
            doc = ast.get_docstring(node)
            first_line_doc = doc.strip().splitlines()[0] if doc else None
            args = [a.arg for a in node.args.args if a.arg != "self"]
            prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
            sig = f"{prefix}{node.name}({', '.join(args[:4])}{'...' if len(args) > 4 else ''})"
            symbols.append(
                ExtractedSymbol(
                    name=node.name,
                    kind="function",
                    file_path=rel_path,
                    line=node.lineno,
                    signature=sig,
                    docstring=first_line_doc[:120] if first_line_doc else None,
                    references=module_refs,
                )
            )
    return symbols


def extract_regex_symbols(content: str, rel_path: str, ext: str) -> list[ExtractedSymbol]:
    """Lightweight regex extraction for TS/JS/Rust/Go without native parser requirements."""
    symbols: list[ExtractedSymbol] = []
    lines = content.splitlines()

    # JS/TS exported items (including async, abstract, declare)
    ts_export_pat = re.compile(
        r"^export\s+(?:default\s+)?(?:async\s+|abstract\s+|declare\s+)?(class|interface|type|function|const|enum)\s+([A-Za-z0-9_$]+)"
    )
    # Rust pub fn / pub struct / pub enum (including async, const, unsafe)
    rust_pub_pat = re.compile(
        r"^pub(?:\s*\([^)]*\))?\s+(?:async\s+|const\s+|unsafe\s+)?(fn|struct|enum|trait)\s+([A-Za-z0-9_]+)"
    )
    # Go top-level exported functions, struct methods, and types
    go_func_pat = re.compile(r"^func\s+(?:\([^)]+\)\s+)?([A-Z][A-Za-z0-9_]*)")
    go_type_pat = re.compile(r"^type\s+([A-Z][A-Za-z0-9_]*)")

    for idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("#"):
            continue

        if ext in {".ts", ".tsx", ".js", ".jsx", ".mjs"}:
            m = ts_export_pat.match(stripped)
            if m:
                kind, name = m.group(1), m.group(2)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        kind="interface" if kind in {"interface", "type"} else ("class" if kind == "class" else "function"),
                        file_path=rel_path,
                        line=idx,
                        signature=f"export {kind} {name}",
                        docstring=None,
                        references=[],
                    )
                )
        elif ext == ".rs":
            m = rust_pub_pat.match(stripped)
            if m:
                kind, name = m.group(1), m.group(2)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        kind="class" if kind in {"struct", "enum", "trait"} else "function",
                        file_path=rel_path,
                        line=idx,
                        signature=f"pub {kind} {name}",
                        docstring=None,
                        references=[],
                    )
                )
        elif ext == ".go":
            m_func = go_func_pat.match(stripped)
            m_type = go_type_pat.match(stripped) if not m_func else None
            if m_func:
                name = m_func.group(1)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        kind="function",
                        file_path=rel_path,
                        line=idx,
                        signature=stripped.split("{")[0].strip(),
                        docstring=None,
                        references=[],
                    )
                )
            elif m_type:
                name = m_type.group(1)
                symbols.append(
                    ExtractedSymbol(
                        name=name,
                        kind="class",
                        file_path=rel_path,
                        line=idx,
                        signature=stripped.split("{")[0].strip(),
                        docstring=None,
                        references=[],
                    )
                )
    return symbols


def extract_manifest_symbols(content: str, rel_path: str) -> list[ExtractedSymbol]:
    """Extract entrypoint or package metadata from manifests."""
    symbols: list[ExtractedSymbol] = []
    file_name = Path(rel_path).name

    if file_name == "package.json":
        try:
            data = json.loads(content)
            name = data.get("name", "package")
            main = data.get("main") or data.get("module") or "index.js"
            scripts = list(data.get("scripts", {}).keys())
            symbols.append(
                ExtractedSymbol(
                    name=name,
                    kind="manifest",
                    file_path=rel_path,
                    line=1,
                    signature=f"npm:{name} (main: {main}, scripts: [{', '.join(scripts[:4])}])",
                    docstring=data.get("description"),
                    references=[],
                )
            )
        except json.JSONDecodeError:
            pass
    elif file_name == "pyproject.toml" or file_name == "Cargo.toml":
        symbols.append(
            ExtractedSymbol(
                name=file_name,
                kind="manifest",
                file_path=rel_path,
                line=1,
                signature=f"config:{file_name}",
                docstring=None,
                references=[],
            )
        )
    return symbols


def scan_workspace(root: Path) -> list[ExtractedSymbol]:
    """Walk the workspace and extract symbols while respecting security and ignore boundaries."""
    all_symbols: list[ExtractedSymbol] = []

    for dirpath, dirnames, filenames in os.walk(root):
        # In-place filter out ignored directories
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]

        current_dir = Path(dirpath)
        for fname in filenames:
            if fname.startswith("."):
                continue

            file_path = current_dir / fname
            if file_path.is_symlink():
                continue

            try:
                stat_res = file_path.stat()
                if stat_res.st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue

            try:
                rel_path = file_path.relative_to(root).as_posix()
            except ValueError:
                continue

            ext = file_path.suffix.lower()
            if ext not in {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs", ".go"} and fname not in {
                "package.json", "pyproject.toml", "Cargo.toml"
            }:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            if ext == ".py":
                all_symbols.extend(extract_python_symbols(content, rel_path))
            elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".rs", ".go"}:
                all_symbols.extend(extract_regex_symbols(content, rel_path, ext))
            elif fname in {"package.json", "pyproject.toml", "Cargo.toml"}:
                all_symbols.extend(extract_manifest_symbols(content, rel_path))

    return all_symbols


def rank_symbols(symbols: list[ExtractedSymbol]) -> list[tuple[ExtractedSymbol, int]]:
    """Compute in-degree centrality / reference scores to rank the most central symbols."""
    # Count references across symbols, deduplicated per calling file to prevent monolith inflation
    ref_counts: Counter[str] = Counter()
    file_refs: dict[str, set[str]] = defaultdict(set)
    for s in symbols:
        for ref in s.references:
            file_refs[s.file_path].add(ref)
    for refs in file_refs.values():
        for ref in refs:
            ref_counts[ref] += 1

    # Group symbols by file to evaluate intra-file quality and harmonic decay
    by_file: dict[str, list[ExtractedSymbol]] = defaultdict(list)
    for s in symbols:
        by_file[s.file_path].append(s)

    scored: list[tuple[ExtractedSymbol, int]] = []
    for file_path, file_syms in by_file.items():
        stem = Path(file_path).stem
        file_ref_score = ref_counts[stem] * 2

        def intrinsic_quality(sym: ExtractedSymbol) -> int:
            q = 1
            if sym.kind == "manifest":
                q += 15
            elif sym.kind == "class":
                q += 6
            if sym.docstring:
                q += 3
            lower_name = sym.name.lower()
            if any(kw in lower_name for kw in ("main", "app", "cli", "run", "validate", "check", "render", "stage", "verify")):
                q += 5
            q += ref_counts[sym.name] * 4
            return q

        file_syms.sort(key=intrinsic_quality, reverse=True)

        for k, sym in enumerate(file_syms):
            intrinsic = intrinsic_quality(sym)
            # Harmonic decay: 1st symbol in a file gets 100% of the file reference score,
            # 2nd gets 50%, 3rd gets 33%, etc.
            decayed_file_score = file_ref_score // (1 + k)
            total_score = intrinsic + decayed_file_score
            scored.append((sym, total_score))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored


def format_budgeted_index(
    ranked: list[tuple[ExtractedSymbol, int]],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_per_file: int = DEFAULT_MAX_PER_FILE,
    output_format: str = "markdown",
) -> str:
    """Format ranked symbols within a strict character/token budget and per-file diversity cap."""
    char_budget = token_budget * ESTIMATED_CHARS_PER_TOKEN
    file_counts: Counter[str] = Counter()

    if output_format == "json":
        items: list[dict[str, Any]] = []
        for s, score in ranked:
            if max_per_file > 0 and file_counts[s.file_path] >= max_per_file:
                continue
            item = {
                "name": s.name,
                "kind": s.kind,
                "file": s.file_path,
                "line": s.line,
                "signature": s.signature,
                "docstring": s.docstring,
                "rank_score": score,
            }
            candidate_items = items + [item]
            candidate_payload = json.dumps(
                {"token_budget": token_budget, "symbol_count": len(candidate_items), "symbols": candidate_items},
                indent=2,
            )
            if len(candidate_payload) > char_budget and items:
                break
            items.append(item)
            file_counts[s.file_path] += 1
        return json.dumps({"token_budget": token_budget, "symbol_count": len(items), "symbols": items}, indent=2)

    # Markdown format
    header_cap = f", Max/File: {max_per_file}" if max_per_file > 0 else ""
    lines = [
        f"### Ranked Workspace Symbols (Budget: ~{token_budget} tokens{header_cap})",
        "",
        "| Symbol | Kind | File & Location | Signature / Summary | Rank |",
        "| :--- | :--- | :--- | :--- | :---: |",
    ]
    current_chars = sum(len(line) + 1 for line in lines)
    total_selected = 0

    truncation_reserve = 100
    for s, score in ranked:
        if max_per_file > 0 and file_counts[s.file_path] >= max_per_file:
            continue
        doc = f" - *{s.docstring}*" if s.docstring else ""
        row = f"| `{s.name}` | {s.kind} | `{s.file_path}:{s.line}` | `{s.signature}`{doc} | {score} |"
        if current_chars + len(row) + 1 + truncation_reserve > char_budget:
            lines.append(f"*(Truncated {len(ranked) - total_selected} additional symbols to fit token budget)*")
            break
        lines.append(row)
        current_chars += len(row) + 1
        file_counts[s.file_path] += 1
        total_selected += 1

    return "\n".join(lines)


def run_self_test() -> int:
    """Self-test verifying extraction, ranking, budgeting, and safety boundaries."""
    # Test 1: Python AST extraction
    py_code = """
import os
import sys

class ModelRegistry(dict):
    '''Central repository for model descriptors.'''
    def register(self, name, model):
        pass
    def lookup(self, name):
        pass

def load_default_config(path: str):
    '''Load configuration from disk.'''
    return {}
"""
    symbols = extract_python_symbols(py_code, "src/core.py")
    assert len(symbols) == 2, f"Expected 2 symbols, got {len(symbols)}"
    cls_sym = next(s for s in symbols if s.name == "ModelRegistry")
    assert cls_sym.kind == "class"
    assert "Central repository" in (cls_sym.docstring or "")
    assert "register" in cls_sym.signature

    fn_sym = next(s for s in symbols if s.name == "load_default_config")
    assert fn_sym.kind == "function"
    assert "Load configuration" in (fn_sym.docstring or "")

    # Test 2: Regex extraction (TS)
    ts_code = """
export interface UserState {
    id: string;
    active: boolean;
}
export class AccountService {
    verify() {}
}
"""
    ts_symbols = extract_regex_symbols(ts_code, "src/account.ts", ".ts")
    assert len(ts_symbols) == 2, f"Expected 2 TS symbols, got {len(ts_symbols)}"
    assert any(s.name == "UserState" and s.kind == "interface" for s in ts_symbols)
    assert any(s.name == "AccountService" and s.kind == "class" for s in ts_symbols)

    # Test 3: Ranking and Budgeting
    all_syms = symbols + ts_symbols
    ranked = rank_symbols(all_syms)
    assert len(ranked) == 4
    md = format_budgeted_index(ranked, token_budget=500, max_per_file=3, output_format="markdown")
    assert "ModelRegistry" in md
    assert "AccountService" in md

    # Test 4: Token Budget Enforcement
    small_md = format_budgeted_index(ranked, token_budget=50, max_per_file=3, output_format="markdown")
    assert len(small_md) < 50 * ESTIMATED_CHARS_PER_TOKEN + 100

    # Test 5: Monolith diversity & per-file capping
    monolith_syms = [
        ExtractedSymbol(
            name=f"fn_worker_{i}",
            kind="function",
            file_path="src/monolith.py",
            line=i * 10,
            signature=f"def fn_worker_{i}()",
            docstring=f"Worker {i}",
            references=["monolith"],
        )
        for i in range(10)
    ]
    secondary_sym = ExtractedSymbol(
        name="RouterService",
        kind="class",
        file_path="src/router.py",
        line=1,
        signature="class RouterService",
        docstring="Main request router",
        references=[],
    )
    test_mix = monolith_syms + [secondary_sym]
    ranked_mix = rank_symbols(test_mix)
    capped_md = format_budgeted_index(ranked_mix, token_budget=1000, max_per_file=2, output_format="markdown")
    assert capped_md.count("src/monolith.py") == 2, f"Expected exactly 2 entries from monolith.py, got {capped_md.count('src/monolith.py')}"
    assert "RouterService" in capped_md, "RouterService should be visible when monolith is capped"

    # Test 6: Advanced regex patterns (TS async/abstract, Rust async/const, Go methods)
    poly_ts = """
export async function queryUserAsync(id: string) {}
export abstract class AbstractController {}
export declare const API_KEY: string;
"""
    poly_ts_syms = extract_regex_symbols(poly_ts, "src/api.ts", ".ts")
    assert any(s.name == "queryUserAsync" and s.kind == "function" for s in poly_ts_syms)
    assert any(s.name == "AbstractController" and s.kind == "class" for s in poly_ts_syms)

    poly_rs = """
pub async fn handle_request() {}
pub const fn default_port() {}
"""
    poly_rs_syms = extract_regex_symbols(poly_rs, "src/server.rs", ".rs")
    assert any(s.name == "handle_request" and s.kind == "function" for s in poly_rs_syms)
    assert any(s.name == "default_port" and s.kind == "function" for s in poly_rs_syms)

    poly_go = """
func (s *Server) ListenAndServe() error {
    return nil
}
type Config struct {}
"""
    poly_go_syms = extract_regex_symbols(poly_go, "src/server.go", ".go")
    assert any(s.name == "ListenAndServe" and s.kind == "function" for s in poly_go_syms)
    assert any(s.name == "Config" and s.kind == "class" for s in poly_go_syms)

    # Test 7: Centrality deduplication per caller file
    file_a_syms = [
        ExtractedSymbol(name=f"helper_{i}", kind="function", file_path="file_a.py", line=i, signature="", docstring=None, references=["shared_lib"])
        for i in range(20)
    ]
    file_b_syms = [
        ExtractedSymbol(name="core_fn", kind="function", file_path="file_b.py", line=1, signature="", docstring=None, references=["shared_lib"])
    ]
    target_sym = ExtractedSymbol(name="shared_lib", kind="class", file_path="shared.py", line=1, signature="", docstring=None, references=[])
    test_centrality = rank_symbols(file_a_syms + file_b_syms + [target_sym])
    target_ranked = next(item for item in test_centrality if item[0].name == "shared_lib")
    # File A (1 ref) + File B (1 ref) = 2 file references (weight = 2*2 = 4 or 2*4 = 8, not 21*4)
    # Target score should not be 80+
    assert target_ranked[1] <= 30, f"Centrality score should reflect file deduplication, got {target_ranked[1]}"

    # Test 8: JSON formatting budget compliance
    json_out = format_budgeted_index(ranked, token_budget=100, max_per_file=3, output_format="json")
    assert len(json_out) <= 100 * ESTIMATED_CHARS_PER_TOKEN + 50, f"JSON output length {len(json_out)} exceeded budget"

    print("extract_symbols.py: self-test passed successfully (8/8 checks passed)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pure-Python AST symbol extractor and ranked dependency indexer."
    )
    parser.add_argument("--root", type=str, default=".", help="Workspace root path")
    parser.add_argument("--budget", type=int, default=DEFAULT_TOKEN_BUDGET, help="Token budget (default: 1200)")
    parser.add_argument("--max-per-file", type=int, default=DEFAULT_MAX_PER_FILE, help="Max symbols per file in output (default: 3, 0=unlimited)")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown", help="Output format")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests and exit")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    root_path = Path(args.root).resolve()
    if not root_path.is_dir():
        print(f"Error: Workspace root not found or not a directory: {args.root}", file=sys.stderr)
        return 1

    symbols = scan_workspace(root_path)
    ranked = rank_symbols(symbols)
    output = format_budgeted_index(
        ranked,
        token_budget=args.budget,
        max_per_file=args.max_per_file,
        output_format=args.format,
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
