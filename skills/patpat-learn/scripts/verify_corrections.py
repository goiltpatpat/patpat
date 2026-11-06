#!/usr/bin/env python3
"""Verify a repository's correction ledger: every rule names its enforcement or an expiring exception."""

from __future__ import annotations

import argparse
import datetime as dt
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

START_MARKER = "<!-- patpat:corrections:start -->"
END_MARKER = "<!-- patpat:corrections:end -->"
DEFAULT_FILES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".github/copilot-instructions.md")
NO_LEDGER_EXIT = 3
COLUMNS = ("ID", "Kind", "Class", "Evidence", "Rule", "Level", "Enforcer", "Proof", "Exception")
KINDS = {"mistake", "policy"}
LEVELS = ("architecture", "type", "validator", "test", "script", "hook", "ci", "prose")
EMPTY = {"", "-", "—", "none"}
ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-?[0-9]+$")
SHA_REF = re.compile(r"^[0-9a-f]{7,64}$")
PR_REF = re.compile(r"^(?:[\w.-]+/[\w.-]+)?#[0-9]+$")
EXCEPTION_PATTERN = re.compile(
    r"^(?P<reason>[^;]+);\s*expires\s+(?P<expires>\d{4}-\d{2}-\d{2});\s*approved-by\s+(?P<approver>\S.*)$"
)
MAX_EXCEPTION_DAYS = 180
PROOF_TIMEOUT_SECONDS = 600

TEMPLATE = f"""## Correction ledger

Each rule names the mechanism that enforces it. A `prose` row needs an expiring exception that says why nothing stronger fits.
Check with `python3 <loaded-skill-directory>/scripts/verify_corrections.py --root .`. To run it in CI, copy the script into the repository.

{START_MARKER}
| {' | '.join(COLUMNS)} |
| {' | '.join('---' for _ in COLUMNS)} |
| C1 | mistake | <failure class> | <sha>, #<pr> | <rule> | test | <path>::<symbol> | `<command that exercises the enforcer>` | - |
{END_MARKER}
"""


@dataclass(frozen=True)
class Row:
    line: int
    cells: dict[str, str]


class LedgerError(ValueError):
    """The ledger cannot be located or parsed."""


class NoLedger(LedgerError):
    """The repository has no correction ledger yet."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise LedgerError(f"{path}: not UTF-8 at byte {error.start} -> save the file as UTF-8") from error


def split_row(line: str) -> list[str]:
    text = line.strip()
    if not (text.startswith("|") and text.endswith("|")):
        raise LedgerError("table row must start and end with |")
    cells, current, escaped = [], [], False
    for char in text[1:-1]:
        if escaped:
            current.append(char if char == "|" else "\\" + char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


def locate_ledger(root: Path, explicit: str | None) -> Path:
    candidates = [explicit] if explicit else list(DEFAULT_FILES)
    for name in candidates:
        path = (root / name) if not Path(name).is_absolute() else Path(name)
        if path.is_file() and START_MARKER in read_text(path):
            return path
    searched = ", ".join(candidates)
    raise NoLedger(
        f"no correction ledger found in {searched} -> add one with: verify_corrections.py --template"
    )


def parse_ledger(path: Path) -> list[Row]:
    lines = read_text(path).splitlines()
    starts = [i for i, line in enumerate(lines) if line.strip() == START_MARKER]
    ends = [i for i, line in enumerate(lines) if line.strip() == END_MARKER]
    if len(starts) != 1 or len(ends) != 1 or ends[0] < starts[0]:
        raise LedgerError(f"{path}: need exactly one {START_MARKER} followed by one {END_MARKER}")
    body = [(i + 1, line) for i, line in enumerate(lines[starts[0] + 1 : ends[0]], start=starts[0] + 1) if line.strip()]
    if len(body) < 2:
        raise LedgerError(f"{path}: ledger needs a header row and a separator row")
    header_line, header = body[0]
    if tuple(split_row(header)) != COLUMNS:
        raise LedgerError(f"{path}:{header_line}: header must be | {' | '.join(COLUMNS)} |")
    if not all(set(cell) <= {"-", ":", " "} and cell for cell in split_row(body[1][1])):
        raise LedgerError(f"{path}:{body[1][0]}: second row must be the --- separator")
    rows = []
    for number, line in body[2:]:
        try:
            cells = split_row(line)
        except LedgerError as error:
            raise LedgerError(f"{path}:{number}: {error}") from error
        if len(cells) != len(COLUMNS):
            raise LedgerError(f"{path}:{number}: expected {len(COLUMNS)} cells, found {len(cells)} (escape a literal pipe as \\|)")
        rows.append(Row(number, dict(zip(COLUMNS, cells))))
    return rows


def unquote(cell: str) -> str:
    return cell[1:-1].strip() if len(cell) >= 2 and cell.startswith("`") and cell.endswith("`") else cell


def git_output(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def resolve_commit(root: Path, sha: str) -> str | None:
    return git_output(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")


def is_shallow(root: Path) -> bool:
    return git_output(root, "rev-parse", "--is-shallow-repository") == "true"


def safe_relative(root: Path, value: str) -> Path | None:
    candidate = Path(value)
    if not value or candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        return None
    resolved = (root / candidate).resolve()
    return resolved if resolved.is_relative_to(root.resolve()) else None


def defines(text: str, symbol: str) -> bool:
    name = re.escape(symbol)
    patterns = (
        rf"^\s*(?:async\s+)?def\s+{name}\b",
        rf"^\s*class\s+{name}\b",
        rf"^\s*{name}\s*(?::[^=\n]*)?=",
        rf"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\*?\s+{name}\b",
        rf"^\s*(?:export\s+)?(?:const|let|var|type|interface|enum|class)\s+{name}\b",
        rf"^\s*(?:pub\s+)?fn\s+{name}\b",
        rf"^\s*func\s+(?:\([^)]*\)\s*)?{name}\b",
        rf"^\s*-?\s*[\"']?{name}[\"']?\s*:",
    )
    return any(re.search(pattern, text, re.MULTILINE) for pattern in patterns)


def check_row(root: Path, ledger: Path, row: Row, today: dt.date) -> list[str]:
    cell = row.cells
    rid = cell["ID"] or "?"
    where = f"{ledger}:{row.line}: {rid}"
    errors: list[str] = []

    if not ID_PATTERN.fullmatch(cell["ID"]):
        errors.append(f"{where}: ID must look like C1 or AUTH-2")
    kind = cell["Kind"].lower()
    if kind not in KINDS:
        errors.append(f"{where}: Kind must be one of {', '.join(sorted(KINDS))}")
    for column in ("Class", "Rule"):
        if cell[column].lower() in EMPTY:
            errors.append(f"{where}: {column} is required")

    refs = [ref.strip() for ref in cell["Evidence"].split(",") if ref.strip() and ref.strip().lower() not in EMPTY]
    occurrences: set[str] = set()
    for ref in refs:
        bare = unquote(ref)
        if SHA_REF.fullmatch(bare):
            full = resolve_commit(root, bare)
            if full:
                occurrences.add(full)
            elif is_shallow(root):
                errors.append(f"{where}: evidence commit {bare} is not in this shallow clone -> fetch full history (CI: actions/checkout fetch-depth: 0)")
            else:
                errors.append(f"{where}: evidence commit {bare} is not in this repository -> use a reachable SHA or a #PR reference")
        elif PR_REF.fullmatch(bare):
            occurrences.add(bare.lower())
        else:
            errors.append(f"{where}: evidence {ref!r} must be a commit SHA or #PR reference")
    if kind == "mistake" and len(occurrences) < 2:
        errors.append(f"{where}: a mistake class needs two independent occurrences in Evidence -> keep it out of the ledger until it recurs, or record it as Kind policy")

    level = cell["Level"].lower()
    if level not in LEVELS:
        errors.append(f"{where}: Level must be one of {', '.join(LEVELS)}")
    enforcer = unquote(cell["Enforcer"])
    proof = unquote(cell["Proof"])
    exception = cell["Exception"]

    if level == "prose":
        if exception.lower() in EMPTY:
            errors.append(f"{where}: a prose rule needs an Exception that says why no test, validator, script, hook, or CI check fits")
    elif level in LEVELS:
        if enforcer.lower() in EMPTY:
            errors.append(f"{where}: Level {level} needs an Enforcer path or path::symbol")
        else:
            path_text, _, symbol = enforcer.partition("::")
            symbol = symbol.strip().rstrip(":")
            target = safe_relative(root, path_text.strip())
            if target is None:
                errors.append(f"{where}: Enforcer {path_text!r} must be a path inside the repository")
            elif not target.is_file():
                errors.append(f"{where}: Enforcer file {path_text.strip()} does not exist -> restore it or move the rule to its new enforcer")
            elif symbol and not defines(target.read_text(encoding="utf-8", errors="replace"), symbol):
                errors.append(f"{where}: Enforcer symbol {symbol!r} is not defined in {path_text.strip()} (a mention in a comment or string does not count)")
        if proof.lower() in EMPTY:
            errors.append(f"{where}: Level {level} needs a Proof command that exercises the enforcer")
        elif not (cell["Proof"].startswith("`") and cell["Proof"].endswith("`")):
            errors.append(f"{where}: Proof must be one command in backticks")

    if exception.lower() not in EMPTY:
        match = EXCEPTION_PATTERN.fullmatch(exception)
        if not match:
            errors.append(f"{where}: Exception must read '<reason>; expires YYYY-MM-DD; approved-by <name>'")
        else:
            try:
                expires = dt.date.fromisoformat(match["expires"])
            except ValueError:
                errors.append(f"{where}: Exception expiry {match['expires']} is not a date")
            else:
                if expires < today:
                    errors.append(f"{where}: Exception expired on {expires} -> enforce the rule, renew with approval, or delete the row")
                elif (expires - today).days > MAX_EXCEPTION_DAYS:
                    errors.append(f"{where}: Exception expiry is more than {MAX_EXCEPTION_DAYS} days away")
    return errors


def run_proof(root: Path, ledger: Path, row: Row) -> str | None:
    command = unquote(row.cells["Proof"])
    try:
        lexer = shlex.shlex(command, posix=True)
        lexer.whitespace_split = True
        lexer.escape = ""  # keep backslashes: regexes and Windows paths reach the command unchanged
        argv = list(lexer)
    except ValueError as error:
        return f"{ledger}:{row.line}: {row.cells['ID']}: Proof is not a parseable command: {error}"
    if argv and argv[0] in {"python", "python3"}:
        argv[0] = sys.executable
    elif argv:
        argv[0] = shutil.which(argv[0]) or argv[0]
    try:
        completed = subprocess.run(
            argv, cwd=root, capture_output=True, text=True, timeout=PROOF_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"{ledger}:{row.line}: {row.cells['ID']}: Proof did not run: {error}"
    if completed.returncode != 0:
        tail = (completed.stdout + completed.stderr).strip().splitlines()[-3:]
        return f"{ledger}:{row.line}: {row.cells['ID']}: Proof exited {completed.returncode}: {' / '.join(tail)}"
    return None


def verify(root: Path, ledger_file: str | None, run_proofs: set[str] | None, today: dt.date) -> tuple[list[str], str]:
    try:
        ledger = locate_ledger(root, ledger_file)
        rows = parse_ledger(ledger)
    except NoLedger:
        raise
    except LedgerError as error:
        return [str(error)], ""
    shown = ledger.relative_to(root) if ledger.is_relative_to(root) else ledger
    errors: list[str] = []
    seen: dict[str, int] = {}
    for row in rows:
        if row.cells["ID"] in seen:
            errors.append(f"{shown}:{row.line}: {row.cells['ID']}: duplicate ID (first on line {seen[row.cells['ID']]})")
        seen.setdefault(row.cells["ID"], row.line)
        errors.extend(check_row(root, shown, row, today))
    if not rows:
        errors.append(f"{shown}: ledger has no rows")
    if run_proofs and not errors:
        unknown = run_proofs - {"all"} - set(seen)
        if unknown:
            errors.append(f"{shown}: --run-proofs names unknown row(s): {', '.join(sorted(unknown))}")
        for row in rows:
            selected = "all" in run_proofs or row.cells["ID"] in run_proofs
            if selected and row.cells["Level"].lower() != "prose":
                failure = run_proof(root, shown, row)
                if failure:
                    errors.append(failure)
    prose = sum(1 for row in rows if row.cells["Level"].lower() == "prose")
    summary = (
        f"correction ledger ok: {len(rows)} rows, {len(rows) - prose} enforced, {prose} prose with expiring exception"
        f"{', proofs ran for ' + ','.join(sorted(run_proofs)) if run_proofs else ''} ({shown})"
    )
    return errors, summary


# A proof containing a literal backslash-n must reach the command unchanged.
BACKSLASH_PROOF = "`python -c \"import sys; sys.exit(0 if len('\\\\n') == 2 else 4)\"`"


def self_test() -> int:
    today = dt.date(2026, 11, 6)
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)

        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

        git("init", "-q")
        git("config", "user.email", "self-test@example.invalid")
        git("config", "user.name", "self-test")
        (root / "check.py").write_text("# mentioned_only is not a guard\ndef guard_head():\n    return 0\n", encoding="utf-8")
        (root / "ci.yml").write_text("jobs:\n  windows-paths:\n    runs-on: windows-latest\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-q", "-m", "seed")
        sha = git("rev-parse", "--short", "HEAD")
        full_sha = git("rev-parse", "HEAD")
        proof = f"`python -c \"import sys; sys.exit(0)\"`"

        def ledger(*rows: str) -> None:
            header = f"| {' | '.join(COLUMNS)} |\n| {' | '.join('---' for _ in COLUMNS)} |\n"
            (root / "AGENTS.md").write_text(
                f"# Rules\n\n{START_MARKER}\n{header}" + "\n".join(rows) + f"\n{END_MARKER}\n", encoding="utf-8"
            )

        valid = f"| C1 | mistake | stale head | {sha}, #12 | bind to head | script | check.py::guard_head | {proof} | — |"
        cases = [
            ("valid", [valid], True, None),
            ("missing enforcer file", [valid.replace("check.py::", "gone.py::")], False, "does not exist"),
            ("missing symbol", [valid.replace("guard_head", "other_guard")], False, "is not defined"),
            ("single occurrence", [valid.replace(f"{sha}, #12", "#12")], False, "two independent occurrences"),
            ("unknown sha", [valid.replace(sha, "deadbeef1")], False, "not in this repository"),
            ("prose without exception", ["| C2 | policy | style | — | no em dash | prose | — | — | — |"], False, "needs an Exception"),
            ("prose with live exception", ["| C2 | policy | style | — | no em dash | prose | — | — | judgment call; expires 2027-01-01; approved-by pat |"], True, None),
            ("expired exception", ["| C2 | policy | style | — | no em dash | prose | — | — | judgment call; expires 2026-01-01; approved-by pat |"], False, "expired"),
            ("far exception", ["| C2 | policy | style | — | no em dash | prose | — | — | judgment call; expires 2028-01-01; approved-by pat |"], False, "more than"),
            ("duplicate id", [valid, valid], False, "duplicate ID"),
            ("path escape", [valid.replace("check.py::guard_head", "../check.py")], False, "inside the repository"),
            ("short and long sha count once", [valid.replace(f"{sha}, #12", f"{sha}, {full_sha}")], False, "two independent occurrences"),
            ("symbol only in a comment", [valid.replace("guard_head", "mentioned_only")], False, "is not defined"),
            ("yaml key enforcer", [valid.replace("check.py::guard_head", "ci.yml::windows-paths:")], True, None),
            ("backslash kept in proof", [valid.replace(proof, BACKSLASH_PROOF)], True, None),
            ("failing proof", [valid.replace(proof, "`python -c \"import sys; sys.exit(3)\"`")], False, "Proof exited 3"),
        ]
        failures = 0
        for name, rows, ok, needle in cases:
            ledger(*rows)
            errors, _ = verify(root, None, run_proofs={"all"}, today=today)
            passed = (not errors) if ok else any(needle in error for error in errors)
            if not passed:
                failures += 1
                print(f"FAIL {name}: {errors}", file=sys.stderr)
        ledger(valid)
        errors, _ = verify(root, None, run_proofs={"C9"}, today=today)
        if not any("unknown row" in error for error in errors):
            failures += 1
            print(f"FAIL unknown proof id: {errors}", file=sys.stderr)
        (root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        try:
            verify(root, None, run_proofs=None, today=today)
        except NoLedger as error:
            if "--template" not in str(error):
                failures += 1
                print(f"FAIL missing ledger message: {error}", file=sys.stderr)
        else:
            failures += 1
            print("FAIL missing ledger must raise NoLedger", file=sys.stderr)
        (root / "AGENTS.md").write_bytes(START_MARKER.encode("ascii") + b"\n| x \x97 |\n")
        errors, _ = verify(root, None, run_proofs=None, today=today)
        if not any("not UTF-8" in error for error in errors):
            failures += 1
            print(f"FAIL non-utf8 ledger: {errors}", file=sys.stderr)
        (root / "AGENTS.md").write_text("# Rules\n", encoding="utf-8")
        (root / "CLAUDE.md").write_text(TEMPLATE, encoding="utf-8")
        errors, _ = verify(root, None, run_proofs=None, today=today)
        if not errors:
            failures += 1
            print("FAIL template placeholders must not verify", file=sys.stderr)
    if failures:
        return 1
    print(f"verify_corrections self-test ok: {len(cases) + 4} cases")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--file", help=f"ledger file relative to root (default: first of {', '.join(DEFAULT_FILES)} with the marker)")
    parser.add_argument(
        "--run-proofs",
        metavar="IDS",
        help="comma-separated row IDs, or 'all', whose Proof commands to execute; proofs are repository commands, so review them with --list-proofs first",
    )
    parser.add_argument("--list-proofs", action="store_true", help="print each row's Proof command without running it")
    parser.add_argument("--template", action="store_true", help="print an empty ledger section to paste into the instruction file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    if args.self_test:
        return self_test()
    if args.template:
        print(TEMPLATE, end="")
        return 0
    root = args.root.resolve()
    selected = {part.strip() for part in args.run_proofs.split(",") if part.strip()} if args.run_proofs else None
    try:
        if args.list_proofs:
            for row in parse_ledger(locate_ledger(root, args.file)):
                print(f"{row.cells['ID']}: {unquote(row.cells['Proof'])}")
            return 0
        errors, summary = verify(root, args.file, selected, dt.date.today())
    except NoLedger as error:
        print(f"{error} (exit {NO_LEDGER_EXIT}: nothing recorded)", file=sys.stderr)
        return NO_LEDGER_EXIT
    except LedgerError as error:
        print(error, file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"correction ledger failed: {len(errors)} problem(s)", file=sys.stderr)
        return 1
    print(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
