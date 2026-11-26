#!/usr/bin/env python3
"""PreToolUse safety guard blocking plugin-cache edits, destructive Git/PR actions, and P1 AI attribution."""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

MAX_STDIN_BYTES = 256 * 1024
MAX_OVERSIZED_SCAN_BYTES = 2 * 1024 * 1024

BASH_TOOLS = {"bash", "shell", "terminal", "run_command", "exec"}
FILE_WRITE_TOOLS = {
    "write",
    "edit",
    "multiedit",
    "write_file",
    "edit_file",
    "replace_file_content",
    "multi_replace_file_content",
    "write_to_file",
    "notebookedit",
}

# Enforces .out-of-scope/plugin-cache-self-edit.md
PLUGIN_CACHE_PATH = re.compile(
    r"(?:^|/)(?:plugins/cache|\.claude/plugins/cache|\.cursor/plugins|\.gemini/config/plugins)(?:/|$)"
)

PATH_KEYS = ("file_path", "path", "target_file", "TargetFile", "AbsolutePath", "notebook_path")
OVERSIZED_TOOL_NAME = re.compile(r'"(?:tool_name|toolName)"\s*:\s*"([^"\r\n]{1,128})"')
OVERSIZED_PATH_FIELD = re.compile(
    r'"(?:' + "|".join(PATH_KEYS) + r')"\s*:\s*"([^"\r\n]{1,4096})"'
)

BASH_CACHE_WRITE_COMMANDS = {
    "tee",
    "cp",
    "mv",
    "rm",
    "mkdir",
    "rmdir",
    "touch",
    "install",
    "ln",
    "chmod",
    "chown",
    "truncate",
    "dd",
    "sed",
    "awk",
    "perl",
    "python",
    "python3",
    "py",
    "node",
    "ruby",
    "sh",
    "bash",
    "zsh",
    "dash",
    "pwsh",
    "powershell",
    "tar",
    "unzip",
    "rsync",
    "patch",
}

WRAPPER_VALUE_FLAGS: dict[str, set[str]] = {
    "sudo": {
        "-u",
        "--user",
        "-g",
        "--group",
        "-h",
        "--host",
        "-p",
        "--prompt",
        "-r",
        "--role",
        "-t",
        "--type",
        "-C",
        "--close-from",
        "-D",
        "--chdir",
        "-R",
        "--chroot",
        "-T",
        "--command-timeout",
        "-U",
        "--other-user",
    },
    "env": {"-u", "--unset", "-C", "--chdir"},
    "command": set(),
}

GIT_VALUE_FLAGS = {
    "-c",
    "-C",
    "--git-dir",
    "--work-tree",
    "--namespace",
    "--super-prefix",
    "--config-env",
}
GIT_PUSH_VALUE_FLAGS = {
    "-o",
    "--push-option",
    "--repo",
    "--receive-pack",
    "--exec",
}
SHELL_EXECUTABLES = {"sh", "bash", "zsh", "dash"}
SHELL_VALUE_FLAGS = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}
MAX_RECURSION_DEPTH = 3

PROTECTED_BRANCHES = {"main", "master"}
ENV_ASSIGNMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")

# Mirrors scripts/check_attribution.py::find_attribution (P1).
AGENT_NAMES = re.compile(
    r"\b(claude|anthropic|openai|chatgpt|codex|copilot|cursor ?agent|gemini|grok|devin|aider|windsurf)\b",
    re.IGNORECASE,
)
AGENT_EMAILS = {"noreply@anthropic.com", "cursoragent@cursor.com"}
CO_AUTHOR = re.compile(
    r"""(?im)(?:^|['"`])[\t ]*co-authored-by:\s*(?P<name>[^<\n'"`]*?)\s*(?:<(?P<email>[^>\n'"`]*)>)?[\t ]*(?:['"`]|$)"""
)
GENERATED = re.compile(
    r"""(?im)(?:^|['"`])[>*_~\t -]*(?:🤖[ \t]*)?generated (?:with|by)\b(?P<rest>[^\n'"`]*)"""
)
STRIP_CHARS = " \t'\"`"

MappingLike = dict[str, Any]


def _normalize_path(raw_path: str) -> str:
    cleaned = raw_path.strip().replace("\\", "/")
    if not cleaned:
        return ""
    return posixpath.normpath(cleaned).lower()


def is_plugin_cache_path(raw_path: str) -> bool:
    normalized = _normalize_path(raw_path)
    if not normalized:
        return False
    return PLUGIN_CACHE_PATH.search(normalized) is not None


def _normalize_command_text(command: str) -> str:
    """Expand escaped newlines in inline shell strings so line-anchored checks see them."""
    return command.replace("\\r\\n", "\n").replace("\\n", "\n")


def find_attribution(text: str) -> list[str]:
    """Return forbidden AI-agent attribution hits; human co-authors and tool-generated notes pass."""
    normalized = _normalize_command_text(text)
    hits: list[str] = []
    seen: set[str] = set()
    for match in CO_AUTHOR.finditer(normalized):
        name = match.group("name") or ""
        email = (match.group("email") or "").strip().lower()
        if AGENT_NAMES.search(name) or email in AGENT_EMAILS:
            snippet = match.group(0).strip(STRIP_CHARS)
            hit = f"agent Co-Authored-By trailer: {snippet}"
            if hit not in seen:
                seen.add(hit)
                hits.append(hit)
    for match in GENERATED.finditer(normalized):
        rest = match.group("rest") or ""
        raw = match.group(0)
        if AGENT_NAMES.search(rest) or "🤖" in raw:
            snippet = raw.strip(STRIP_CHARS)
            hit = f"'Generated with' footer: {snippet}"
            if hit not in seen:
                seen.add(hit)
                hits.append(hit)
    return hits


def _split_shell_commands(command: str) -> list[list[str]]:
    """Split a shell command string into unquoted command segments and tokens without raising."""
    segments: list[list[str]] = []
    current_segment: list[str] = []
    buf: list[str] = []
    in_single = False
    in_double = False
    escaped = False

    def flush_token() -> None:
        if buf:
            current_segment.append("".join(buf))
            buf.clear()

    def flush_segment() -> None:
        flush_token()
        if current_segment:
            segments.append(list(current_segment))
            current_segment.clear()

    i = 0
    length = len(command)
    while i < length:
        ch = command[i]
        if escaped:
            buf.append(ch)
            escaped = False
            i += 1
            continue
        if in_single:
            if ch == "'":
                in_single = False
            else:
                buf.append(ch)
            i += 1
            continue
        if in_double:
            if ch == "\\":
                if i + 1 < length and command[i + 1] in ('"', "\\", "$", "`", "\n"):
                    escaped = True
                else:
                    buf.append(ch)
            elif ch == '"':
                in_double = False
            else:
                buf.append(ch)
            i += 1
            continue

        if ch == "\\":
            if i + 1 < length and command[i + 1] in (" ", "\t", "\n", ";", "&", "|", "<", ">", "(", ")", '"', "'", "\\"):
                escaped = True
            else:
                buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "&" and i + 1 < length and command[i + 1] == ">":
            flush_token()
            if i + 2 < length and command[i + 2] == ">":
                current_segment.append("&>>")
                i += 3
            else:
                current_segment.append("&>")
                i += 2
            continue
        if ch in (";", "\n", "|", "&", "(", ")"):
            flush_segment()
            if ch in ("|", "&") and i + 1 < length and command[i + 1] == ch:
                i += 2
            else:
                i += 1
            continue
        if ch == "<":
            flush_token()
            if i + 1 < length and command[i + 1] == "<":
                current_segment.append("<<")
                i += 2
            else:
                current_segment.append("<")
                i += 1
            continue
        if ch == ">":
            flush_token()
            if i + 1 < length and command[i + 1] in (">", "|"):
                current_segment.append(">" + command[i + 1])
                i += 2
            else:
                current_segment.append(">")
                i += 1
            continue
        if ch.isspace():
            flush_token()
            i += 1
            continue
        buf.append(ch)
        i += 1

    flush_segment()
    return segments


def _unwrap_command(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
    """Strip leading inline env assignments and thin wrappers (env/command/sudo)."""
    env_vars: dict[str, str] = {}
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        match = ENV_ASSIGNMENT.match(token)
        if match:
            env_vars[match.group(1)] = match.group(2)
            idx += 1
            continue
        base = posixpath.basename(token.replace("\\", "/")).lower()
        if base in WRAPPER_VALUE_FLAGS:
            value_flags = WRAPPER_VALUE_FLAGS[base]
            idx += 1
            while idx < len(tokens):
                arg = tokens[idx]
                if arg == "--":
                    idx += 1
                    break
                if arg.startswith("-"):
                    if arg in value_flags and idx + 1 < len(tokens):
                        idx += 2
                    else:
                        idx += 1
                    continue
                break
            continue
        break
    return env_vars, tokens[idx:]


def _executable_name(token: str) -> str:
    base = posixpath.basename(token.replace("\\", "/")).lower()
    if base.endswith(".exe") or base.endswith(".cmd") or base.endswith(".bat"):
        base = base[:-4]
    return base


def _git_subcommand(argv: list[str]) -> tuple[str | None, int]:
    idx = 1
    while idx < len(argv) and argv[idx].startswith("-"):
        if argv[idx] in GIT_VALUE_FLAGS:
            idx += 2
        else:
            idx += 1
    if idx >= len(argv):
        return None, idx
    return argv[idx].lower(), idx


def _check_git_push(argv: list[str]) -> str | None:
    subcmd, idx = _git_subcommand(argv)
    if subcmd != "push":
        return None
    push_args = argv[idx + 1 :]
    has_force_with_lease = False
    has_delete = False
    positional: list[str] = []
    after_double_dash = False
    arg_idx = 0
    while arg_idx < len(push_args):
        arg = push_args[arg_idx]
        if not after_double_dash and arg == "--":
            after_double_dash = True
            arg_idx += 1
            continue
        if not after_double_dash and arg.startswith("-"):
            if arg in GIT_PUSH_VALUE_FLAGS:
                arg_idx += 2
                continue
            if arg.startswith("-o") and len(arg) > 2:
                arg_idx += 1
                continue
            if arg == "--force" or arg == "-f":
                return (
                    "Blocked by Patpat safety guard: `git push --force` / `-f` is disabled. "
                    "Use a regular push or explicitly confirmed `--force-with-lease` on a non-protected branch."
                )
            if arg.startswith("--force-with-lease"):
                has_force_with_lease = True
                arg_idx += 1
                continue
            if arg in ("--delete", "-d"):
                has_delete = True
                arg_idx += 1
                continue
            if not arg.startswith("--"):
                flags = arg[1:]
                o_pos = flags.find("o")
                flag_prefix = flags[: o_pos + 1] if o_pos != -1 else flags
                if "f" in flag_prefix:
                    return (
                        f"Blocked by Patpat safety guard: force-push flag `{arg}` in `git push` is disabled."
                    )
                if "d" in flag_prefix:
                    has_delete = True
                if o_pos != -1 and o_pos == len(flags) - 1:
                    arg_idx += 2
                    continue
            arg_idx += 1
        else:
            positional.append(arg)
            arg_idx += 1
    for ref in positional:
        if ref.startswith("+"):
            return (
                f"Blocked by Patpat safety guard: force refspec `{ref}` in `git push` is disabled."
            )
    for ref in positional[1:]:
        if ref.startswith(":"):
            target = ref[1:].removeprefix("refs/heads/").lower()
            if target in PROTECTED_BRANCHES:
                return (
                    f"Blocked by Patpat safety guard: deleting protected branch `{target}` via `git push` is disabled."
                )
    if has_delete:
        for ref in positional[1:]:
            target = ref.removeprefix("refs/heads/").lower()
            if target in PROTECTED_BRANCHES:
                return (
                    f"Blocked by Patpat safety guard: deleting protected branch `{target}` via `git push --delete` is disabled."
                )
    if has_force_with_lease:
        if len(positional) < 2:
            return (
                "Blocked by Patpat safety guard: `git push --force-with-lease` requires an explicit "
                "remote and non-protected branch refspec."
            )
        for ref in positional[1:]:
            target = ref.split(":", 1)[-1]
            target = target.removeprefix("refs/heads/").lower()
            if target in PROTECTED_BRANCHES:
                return (
                    f"Blocked by Patpat safety guard: force-pushing to protected branch `{target}` is disabled."
                )
    return None


def _check_gh_merge(argv: list[str]) -> str | None:
    if len(argv) < 3 or argv[1].lower() != "pr" or argv[2].lower() != "merge":
        return None
    for arg in argv[3:]:
        if arg == "--auto" or arg.startswith("--auto="):
            return (
                "Blocked by Patpat safety guard: `gh pr merge --auto` is prohibited "
                "(.out-of-scope/auto-merge-without-provider-head.md)."
            )
    return None


def _check_bash_plugin_cache_write(argv: list[str]) -> str | None:
    for idx, token in enumerate(argv):
        if token in (">", ">>", ">|", "&>", "&>>") and idx + 1 < len(argv):
            target = argv[idx + 1]
            if is_plugin_cache_path(target):
                return (
                    f"Blocked by Patpat safety guard: refusing to write installed plugin cache path `{target}` "
                    "(.out-of-scope/plugin-cache-self-edit.md)."
                )
    if not argv:
        return None
    exe = _executable_name(argv[0])
    if exe not in BASH_CACHE_WRITE_COMMANDS:
        return None
    for token in argv[1:]:
        if is_plugin_cache_path(token):
            return (
                f"Blocked by Patpat safety guard: refusing to modify installed plugin cache path via `{exe}` "
                "(.out-of-scope/plugin-cache-self-edit.md)."
            )
    return None


def _extract_backtick_commands(command: str) -> list[str]:
    """Extract unescaped backtick command substitutions outside single quotes."""
    extracted: list[str] = []
    in_single = False
    in_double = False
    in_backtick = False
    escaped = False
    buf: list[str] = []
    for ch in command:
        if escaped:
            if in_backtick:
                buf.append(ch)
            escaped = False
            continue
        if in_single:
            if ch == "'":
                in_single = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if not in_backtick:
            if not in_double and ch == "'":
                in_single = True
                continue
            if ch == '"':
                in_double = not in_double
                continue
        if ch == "`":
            if in_backtick:
                snippet = "".join(buf).strip()
                if snippet:
                    extracted.append(snippet)
                buf.clear()
                in_backtick = False
            else:
                in_backtick = True
            continue
        if in_backtick:
            buf.append(ch)
    return extracted


def _extract_dollar_paren_commands(command: str) -> list[str]:
    """Extract unescaped $(...) command substitutions outside single quotes."""
    extracted: list[str] = []
    in_single = False
    in_double = False
    escaped = False
    i = 0
    length = len(command)
    while i < length:
        ch = command[i]
        if escaped:
            escaped = False
            i += 1
            continue
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "\\":
            escaped = True
            i += 1
            continue
        if not in_double and ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = not in_double
            i += 1
            continue
        if ch == "$" and i + 1 < length and command[i + 1] == "(":
            # Skip arithmetic $((...)) only if doubled; otherwise capture balanced $(...).
            start = i + 2
            depth = 1
            sub_single = False
            sub_double = False
            sub_escaped = False
            j = start
            while j < length and depth > 0:
                c = command[j]
                if sub_escaped:
                    sub_escaped = False
                    j += 1
                    continue
                if sub_single:
                    if c == "'":
                        sub_single = False
                    j += 1
                    continue
                if c == "\\":
                    sub_escaped = True
                    j += 1
                    continue
                if not sub_double and c == "'":
                    sub_single = True
                    j += 1
                    continue
                if c == '"':
                    sub_double = not sub_double
                    j += 1
                    continue
                if not sub_double:
                    if c == "(":
                        depth += 1
                    elif c == ")":
                        depth -= 1
                        if depth == 0:
                            break
                j += 1
            snippet = command[start:j].strip()
            if snippet:
                extracted.append(snippet)
            i = j + 1
            continue
        i += 1
    return extracted


def _extract_shell_c_script(argv: list[str]) -> str | None:
    """Return the inline command string passed to `sh/bash/zsh/dash -c`, if any."""
    seen_c = False
    idx = 1
    while idx < len(argv):
        arg = argv[idx]
        if arg == "--":
            idx += 1
            break
        if arg in SHELL_VALUE_FLAGS:
            idx += 2
            continue
        if arg.startswith(("-", "+")) and len(arg) > 1:
            if not arg.startswith("--"):
                flags = arg[1:]
                if arg.startswith("-") and "c" in flags:
                    seen_c = True
                extra = sum(1 for ch in flags if ch in ("o", "O"))
                idx += 1 + extra
                continue
            idx += 1
            continue
        break
    if seen_c and idx < len(argv):
        return argv[idx]
    return None


def _check_attribution_block(text: str) -> str | None:
    hits = find_attribution(text)
    if not hits:
        return None
    detail = "; ".join(hits)
    return (
        f"Blocked by Patpat safety guard (P1 attribution): {detail}. "
        "Remove AI-agent Co-Authored-By trailers and 'Generated with' footers per AGENTS.md."
    )


def _evaluate_bash_command_inner(command: str, depth: int) -> tuple[str | None, bool]:
    check_attribution = False
    for segment in _split_shell_commands(command):
        _, argv = _unwrap_command(segment)
        if not argv:
            continue
        exe = _executable_name(argv[0])
        if exe == "git":
            reason = _check_git_push(argv)
            if reason:
                return reason, check_attribution
            subcmd, _ = _git_subcommand(argv)
            if subcmd == "commit":
                check_attribution = True
        elif exe == "gh":
            reason = _check_gh_merge(argv)
            if reason:
                return reason, check_attribution
            if len(argv) >= 3 and argv[1].lower() == "pr" and argv[2].lower() in {"create", "edit", "merge"}:
                check_attribution = True
        elif exe in SHELL_EXECUTABLES and depth < MAX_RECURSION_DEPTH:
            script = _extract_shell_c_script(argv)
            if script:
                sub_reason, sub_attr = _evaluate_bash_command_inner(script, depth + 1)
                if sub_reason:
                    return sub_reason, True
                check_attribution = check_attribution or sub_attr
        reason = _check_bash_plugin_cache_write(argv)
        if reason:
            return reason, check_attribution
    if depth < MAX_RECURSION_DEPTH:
        for sub_cmd in (*_extract_backtick_commands(command), *_extract_dollar_paren_commands(command)):
            sub_reason, sub_attr = _evaluate_bash_command_inner(sub_cmd, depth + 1)
            if sub_reason:
                return sub_reason, True
            check_attribution = check_attribution or sub_attr
    if check_attribution:
        attr_reason = _check_attribution_block(command)
        if attr_reason:
            return attr_reason, True
    return None, check_attribution


def evaluate_bash_command(command: str) -> str | None:
    reason, check_attribution = _evaluate_bash_command_inner(command, 0)
    if reason:
        return reason
    if check_attribution:
        return _check_attribution_block(command)
    return None


def extract_tool_name(payload: MappingLike) -> str:
    raw = payload.get("tool_name") or payload.get("toolName") or ""
    return raw.strip().lower() if isinstance(raw, str) else ""


def extract_command(payload: MappingLike) -> str | None:
    for container_key in ("tool_input", "input"):
        container = payload.get(container_key)
        if isinstance(container, dict):
            cmd = container.get("command")
            if isinstance(cmd, str) and cmd.strip():
                return cmd
    cmd = payload.get("command")
    if isinstance(cmd, str) and cmd.strip():
        return cmd
    return None


def extract_file_paths(payload: MappingLike) -> list[str]:
    paths: list[str] = []
    containers: list[MappingLike] = []
    for key in ("tool_input", "input"):
        container = payload.get(key)
        if isinstance(container, dict):
            containers.append(container)
    containers.append(payload)
    for container in containers:
        for key in PATH_KEYS:
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value)
        edits = container.get("edits")
        if isinstance(edits, list):
            for item in edits:
                if isinstance(item, dict):
                    for key in PATH_KEYS:
                        value = item.get(key)
                        if isinstance(value, str) and value.strip():
                            paths.append(value)
    return paths


def evaluate_payload(payload: Any) -> tuple[int, str]:
    """Return (exit_code, stderr_message). 0 = allow (fail-open), 2 = block."""
    if not isinstance(payload, dict):
        return 0, ""
    tool_name = extract_tool_name(payload)
    if tool_name in FILE_WRITE_TOOLS or (not tool_name and extract_file_paths(payload)):
        for raw_path in extract_file_paths(payload):
            if is_plugin_cache_path(raw_path):
                return (
                    2,
                    f"Blocked by Patpat safety guard: refusing to edit installed plugin cache path `{raw_path}` "
                    "(.out-of-scope/plugin-cache-self-edit.md). Route edits to the canonical source repository "
                    "or an explicit user-approved local override path.",
                )
        return 0, ""
    if tool_name in BASH_TOOLS or (not tool_name and extract_command(payload)):
        command = extract_command(payload)
        if not command:
            return 0, ""
        reason = evaluate_bash_command(command)
        if reason:
            return 2, reason
    return 0, ""


OVERSIZED_COMMAND_START = re.compile(r'"command"\s*:\s*"')


def _extract_oversized_command_prefixes(scanned: str) -> list[str]:
    """Decode every JSON string prefix of `"command": "..."` fields in a truncated payload."""
    results: list[str] = []
    length = len(scanned)
    for match in OVERSIZED_COMMAND_START.finditer(scanned):
        chars: list[str] = []
        idx = match.end()
        while idx < length:
            ch = scanned[idx]
            if ch == '"':
                break
            if ch == "\\":
                if idx + 1 >= length:
                    break
                nxt = scanned[idx + 1]
                if nxt == "n":
                    chars.append("\n")
                elif nxt == "r":
                    chars.append("\r")
                elif nxt == "t":
                    chars.append("\t")
                elif nxt in ('"', "\\", "/"):
                    chars.append(nxt)
                elif nxt == "u" and idx + 5 < length:
                    try:
                        chars.append(chr(int(scanned[idx + 2 : idx + 6], 16)))
                        idx += 6
                        continue
                    except ValueError:
                        chars.append(nxt)
                else:
                    chars.append(nxt)
                idx += 2
                continue
            chars.append(ch)
            idx += 1
        decoded = "".join(chars)
        if decoded.strip():
            results.append(decoded)
    return results


def _scan_oversized_payload(raw_prefix: str, stream: io.TextIOBase) -> tuple[int, str]:
    """Scan oversized (>MAX_STDIN_BYTES) payloads up to MAX_OVERSIZED_SCAN_BYTES."""
    remaining = MAX_OVERSIZED_SCAN_BYTES - len(raw_prefix)
    scanned = raw_prefix + (stream.read(remaining) if remaining > 0 else "")
    tool_match = OVERSIZED_TOOL_NAME.search(scanned[:4096]) or OVERSIZED_TOOL_NAME.search(scanned[-4096:])
    tool_name = tool_match.group(1).strip().lower() if tool_match else ""
    if tool_name and tool_name not in FILE_WRITE_TOOLS and tool_name not in BASH_TOOLS:
        return 0, ""
    if tool_name in BASH_TOOLS or not tool_name:
        try:
            payload = json.loads(scanned)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            return evaluate_payload(payload)
    for match in OVERSIZED_PATH_FIELD.finditer(scanned):
        candidate = match.group(1).replace("\\\\", "/")
        if is_plugin_cache_path(candidate):
            return (
                2,
                f"Blocked by Patpat safety guard: refusing to edit installed plugin cache path `{candidate}` "
                "(.out-of-scope/plugin-cache-self-edit.md).",
            )
    if tool_name in BASH_TOOLS or (not tool_name and OVERSIZED_COMMAND_START.search(scanned)):
        normalized = scanned.replace("\\\\", "/").replace("\\", "/").lower()
        if PLUGIN_CACHE_PATH.search(normalized):
            return (
                2,
                "Blocked by Patpat safety guard: oversized Bash payload references installed plugin cache path "
                "(.out-of-scope/plugin-cache-self-edit.md).",
            )
        for extracted_cmd in _extract_oversized_command_prefixes(scanned):
            reason = evaluate_bash_command(extracted_cmd)
            if reason:
                return 2, reason
    return 0, ""


def handle_stream(stream: io.TextIOBase) -> tuple[int, str]:
    raw = stream.read(MAX_STDIN_BYTES + 1)
    if not raw or not raw.strip():
        return 0, ""
    if len(raw) > MAX_STDIN_BYTES:
        return _scan_oversized_payload(raw, stream)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0, ""
    return evaluate_payload(payload)


def self_test() -> int:
    big_content = "x" * (MAX_STDIN_BYTES + 4096)
    cases: list[tuple[str, str, int]] = [
        # Fail-open basics
        ("empty stdin fails open", "", 0),
        ("malformed json fails open", "{not json", 0),
        ("read tool on plugin cache passes", json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/home/u/.claude/plugins/cache/patpat/SKILL.md"}}), 0),
        # Write|Edit plugin-cache guard
        ("Write to plugins/cache blocks", json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/opt/host/plugins/cache/patpat/SKILL.md"}}), 2),
        ("Edit to .claude/plugins/cache blocks", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/home/alice/.claude/plugins/cache/patpat/hooks.json"}}), 2),
        ("Edit to Windows .claude\\plugins\\cache blocks", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": r"C:\Users\alice\.claude\plugins\cache\patpat\SKILL.md"}}), 2),
        ("Write to .cursor/plugins blocks", json.dumps({"tool_name": "Write", "tool_input": {"file_path": "~/.cursor/plugins/patpat/skills/patpat/SKILL.md"}}), 2),
        ("Edit to .gemini/config/plugins blocks", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/home/alice/.gemini/config/plugins/patpat/SKILL.md"}}), 2),
        ("Path traversal into plugins/cache blocks", json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/repo/plugins/cache/../cache/patpat/SKILL.md"}}), 2),
        ("Edit to canonical repo skill passes", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/home/alice/patpat/skills/patpat-loop/SKILL.md"}}), 0),
        ("Edit to .out-of-scope doc passes", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/home/alice/patpat/.out-of-scope/plugin-cache-self-edit.md"}}), 0),
        ("Edit to .claude-plugin manifest passes", json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "/home/alice/patpat/.claude-plugin/plugin.json"}}), 0),
        # Oversized (>256 KB) plugin-cache bypass prevention
        ("oversized Write with file_path at tail blocks", json.dumps({"tool_name": "Write", "tool_input": {"content": big_content, "file_path": "/home/alice/.claude/plugins/cache/patpat/SKILL.md"}}), 2),
        ("oversized Write with file_path at head blocks", json.dumps({"tool_name": "Write", "tool_input": {"file_path": "/home/alice/.claude/plugins/cache/patpat/SKILL.md", "content": big_content}}), 2),
        ("oversized Write with Windows path at tail blocks", json.dumps({"tool_name": "Write", "tool_input": {"content": big_content, "file_path": r"C:\Users\alice\.claude\plugins\cache\patpat\SKILL.md"}}), 2),
        ("oversized Write to repo doc mentioning cache passes", json.dumps({"tool_name": "Write", "tool_input": {"content": big_content + " .claude/plugins/cache/patpat ", "file_path": "/home/alice/patpat/docs/guide.md"}}), 0),
        ("oversized Read on plugin cache passes", json.dumps({"tool_name": "Read", "tool_input": {"content": big_content, "file_path": "/home/alice/.claude/plugins/cache/patpat/SKILL.md"}}), 0),
        # Bash plugin-cache write guard
        ("Bash append redirect to .claude/plugins/cache blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo x >> ~/.claude/plugins/cache/patpat/SKILL.md"}}), 2),
        ("Bash overwrite redirect to plugins/cache blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo x>/opt/host/plugins/cache/patpat/a"}}), 2),
        ("Bash tee to .claude/plugins/cache blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo x | tee ~/.claude/plugins/cache/patpat/SKILL.md"}}), 2),
        ("Bash cp to .cursor/plugins blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "cp a.md ~/.cursor/plugins/patpat/SKILL.md"}}), 2),
        ("Bash python3 write to .claude/plugins/cache blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "python3 -c \"open('/home/u/.claude/plugins/cache/patpat/x', 'w').write('y')\""}}), 2),
        ("Bash grep mentioning .claude/plugins/cache passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep '.claude/plugins/cache' hooks/scripts/patpat_safety_guard.py"}}), 0),
        ("Bash cat on .claude/plugins/cache passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "cat ~/.claude/plugins/cache/patpat/SKILL.md"}}), 0),
        # Bash force-push & protected-branch deletion guard
        ("git push --force blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force origin feat/x"}}), 2),
        ("git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -f"}}), 2),
        ("sudo -u root git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sudo -u root git push -f origin main"}}), 2),
        ("env -C /repo git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "env -C /repo git push -f origin feat/x"}}), 2),
        ("env -u HOME -C /repo -- git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "env -u HOME -C /repo -- git push -f"}}), 2),
        ("git -C repo push -uf blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git -C /tmp/repo push -uf origin feat/x"}}), 2),
        ("git push --force-with-lease on main blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin main"}}), 2),
        ("git push --force-with-lease on HEAD:master blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin HEAD:master"}}), 2),
        ("bare git push --force-with-lease blocks fail-closed", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease"}}), 2),
        ("remote-only git push --force-with-lease origin blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin"}}), 2),
        ("git push +main force refspec blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin +main"}}), 2),
        ("git push +HEAD:main force refspec blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin +HEAD:main"}}), 2),
        ("git push --delete origin main blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --delete origin main"}}), 2),
        ("git push -d origin master blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -d origin master"}}), 2),
        ("git push origin :main blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin :main"}}), 2),
        ("git push origin :refs/heads/master blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin :refs/heads/master"}}), 2),
        ("git push --delete origin feat/old passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --delete origin feat/old"}}), 0),
        ("git push origin :feat/old passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push origin :feat/old"}}), 0),
        ("git push --force-with-lease on feature branch passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --force-with-lease origin feat/x"}}), 0),
        ("normal git push passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -u origin feat/x"}}), 0),
        ("echo git push --force passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo 'git push --force'"}}), 0),
        ("git commit mentioning -f passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'docs: block git push -f'"}}), 0),
        # Bash gh pr merge guard (--auto blocked unconditionally; regular merge allowed)
        ("regular gh pr merge passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 42 --squash"}}), 0),
        ("gh pr merge --auto blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 42 --auto --squash"}}), 2),
        ("sudo -u root gh pr merge --auto blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sudo -u root gh pr merge 42 --auto"}}), 2),
        ("gh pr view passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr view 42"}}), 0),
        ("grep gh pr merge passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep 'gh pr merge' docs/guide.md"}}), 0),
        # P1 AI-attribution guard
        ("non-matching echo attribution passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo 'Co-Authored-By: Claude <noreply@anthropic.com>'"}}), 0),
        ("non-matching grep attribution passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "grep 'Generated with' scripts/check_attribution.py"}}), 0),
        ("clean git commit with human co-author passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'feat: clean' -m 'Generated by scripts/stage_plugin.py' -m 'Co-Authored-By: Pat Human <pat@openai.com>'"}}), 0),
        ("git commit with agent trailer and email blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'fix: x' -m 'Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>'"}}), 2),
        ("git commit with agent trailer without email blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m 'fix: x\\n\\nCo-Authored-By: Claude'"}}), 2),
        ("sudo -u root git commit with agent trailer blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sudo -u root git commit -m 'fix: x\\n\\nCo-Authored-By: Claude'"}}), 2),
        ("git commit heredoc with cursor agent blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -F - <<'EOF'\nfix: y\n\nCo-Authored-By: Cursor Agent <cursoragent@cursor.com>\nEOF"}}), 2),
        ("gh pr create with robot generated footer blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create --title 'x' --body 'Summary\\n\\n🤖 Generated with [Claude Code](https://claude.com/claude-code)'"}}), 2),
        ("gh pr edit with generated by codex blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr edit 42 --body 'Generated by Codex'"}}), 2),
        ("gh pr merge with gemini co-author blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 42 --squash --body 'Co-Authored-By: Gemini'"}}), 2),
        ("chained git add && git commit attribution blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git add . && git commit -m 'fix\\n\\nGenerated with Claude'"}}), 2),
        # Hardened bypass regressions: value-taking push flags, backticks, bash -c, Markdown attribution, oversized Bash
        ("git push -o ci.skip --force-with-lease origin blocks fail-closed", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -o ci.skip --force-with-lease origin"}}), 2),
        ("git push --push-option a --force-with-lease origin feat/x passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --push-option a --force-with-lease origin feat/x"}}), 0),
        ("backtick command substitution git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo `git push -f origin main`"}}), 2),
        ("double-quoted backtick git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": 'echo "`git push -f origin main`"'}}), 2),
        ("single-quoted backtick git push -f passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo '`git push -f origin main`'"}}), 0),
        ("bash -c git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -c 'git push -f origin main'"}}), 2),
        ("sh -lc gh pr merge --auto blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sh -lc 'gh pr merge 42 --auto'"}}), 2),
        ("bash -c git commit attribution blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -c \"git commit -m 'fix\\n\\nCo-Authored-By: Claude'\""}}), 2),
        ("blockquote generated footer in PR create blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create --title 'x' --body 'Summary\\n\\n> Generated with Claude'"}}), 2),
        ("emphasized generated footer in PR create blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create --title 'x' --body 'Summary\\n\\n*Generated with [Claude Code](https://claude.com)*'"}}), 2),
        ("oversized Bash git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": f"echo {big_content} && git push -f origin main"}}), 2),
        ("oversized Bash P1 attribution blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": f"gh pr create --title x --body '{big_content}\\n\\nCo-Authored-By: Claude <noreply@anthropic.com>'"}}), 2),
        # Review hardening regressions: ReDoS guard, >2 MiB Bash truncation, omitted tool_name, POSIX shell -c/quotes, attached -o flags
        ("long markdown rule in commit passes fast without ReDoS", json.dumps({"tool_name": "Bash", "tool_input": {"command": f"git commit -m 'docs\\n\\n{'-' * 60}\\nbody'"}}), 0),
        ("over-2MiB truncated Bash git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -f origin main && echo " + ("x" * (MAX_OVERSIZED_SCAN_BYTES + 1024))}}), 2),
        ("oversized Bash without tool_name git push -f blocks", json.dumps({"command": f"echo {big_content} && git push -f origin main"}), 2),
        ("bash -c -- git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -c -- 'git push -f origin main'"}}), 2),
        ("bash -c -e git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -c -e 'git push -f origin main'"}}), 2),
        ("bash -o pipefail -c git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -o pipefail -c 'git push -f origin main'"}}), 2),
        ("sh +e -c git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sh +e -c 'git push -f origin main'"}}), 2),
        ("apostrophe inside double quotes before backtick git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": 'echo "don\'t `git push -f origin main`"'}}), 2),
        ("git push -uo ci.skip --force-with-lease origin blocks fail-closed", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -uo ci.skip --force-with-lease origin"}}), 2),
        ("git push -ofast origin feat/x passes without false-positive -f", json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push -ofast origin feat/x"}}), 0),
        # Round-2 review regressions: bundled -o/-O shell flags, escaped quotes P1 inside bash -c, decoy command field >2MiB, double-quoted $(...)
        ("bash -euo pipefail -c git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -euo pipefail -c 'git push -f origin main'"}}), 2),
        ("bash -co pipefail git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "bash -co pipefail 'git push -f origin main'"}}), 2),
        ("sh +eo errexit -c gh pr merge --auto blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": "sh +eo errexit -c 'gh pr merge 42 --auto'"}}), 2),
        ("bash -c escaped double-quote Co-Authored-By email blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": 'bash -c "git commit -m \\"fix\\" -m \\"Co-Authored-By: Claude <noreply@anthropic.com>\\""'}}), 2),
        ("over-2MiB payload with earlier decoy command field blocks", json.dumps({"meta": {"command": "noop"}, "tool_name": "Bash", "tool_input": {"command": "git push -f origin main && echo " + ("x" * (MAX_OVERSIZED_SCAN_BYTES + 1024))}}), 2),
        ("double-quoted dollar-paren git push -f blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": 'echo "$(git push -f origin main)"'}}), 2),
        ("double-quoted dollar-paren gh pr merge --auto blocks", json.dumps({"tool_name": "Bash", "tool_input": {"command": 'X="$(gh pr merge 42 --auto)"'}}), 2),
        ("single-quoted dollar-paren git push -f passes", json.dumps({"tool_name": "Bash", "tool_input": {"command": "echo '$(git push -f origin main)'"}}), 0),
    ]
    failed: list[str] = []
    for name, raw_input, expected_code in cases:
        code, message = handle_stream(io.StringIO(raw_input))
        if code != expected_code:
            failed.append(f"{name}: expected exit {expected_code}, got {code} ({message!r})")
        elif expected_code == 2 and "Patpat safety guard" not in message:
            failed.append(f"{name}: missing guard message on block")

    # P1 parity self-test against scripts/check_attribution.py
    check_attr = Path(__file__).resolve().parents[2] / "scripts" / "check_attribution.py"
    if check_attr.is_file():
        spec = importlib.util.spec_from_file_location("patpat_check_attribution", check_attr)
        if not spec or not spec.loader:
            failed.append("P1 parity check: failed to load scripts/check_attribution.py")
        else:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if AGENT_NAMES.pattern != mod.AGENT_NAMES.pattern or AGENT_EMAILS != mod.AGENT_EMAILS:
                failed.append("P1 parity drift: AGENT_NAMES.pattern or AGENT_EMAILS differs from scripts/check_attribution.py")

    if failed:
        for item in failed:
            print(f"FAIL {item}", file=sys.stderr)
        return 1
    print(f"patpat_safety_guard self-test ok: {len(cases)} cases")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    stream: io.TextIOBase = (
        io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "buffer")
        else sys.stdin
    )
    code, message = handle_stream(stream)
    if message:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
