#!/usr/bin/env python3
"""Static CI/CD workflow auditor and mechanical verifier for Patpat."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

OTHER_CI_FILES = (
    ".gitlab-ci.yml",
    ".circleci/config.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
    ".buildkite/pipeline.yml",
    ".buildkite/pipeline.yaml",
    ".travis.yml",
    "bitbucket-pipelines.yml",
)

DEPRECATED_ACTIONS: dict[str, tuple[int, str]] = {
    "actions/checkout": (3, "v4+"),
    "actions/setup-python": (4, "v5+"),
    "actions/setup-node": (3, "v4+"),
    "actions/upload-artifact": (3, "v4+"),
    "actions/download-artifact": (3, "v4+"),
    "actions/cache": (3, "v4+"),
    "actions/setup-go": (4, "v5+"),
}

DEPRECATED_RUNNERS: dict[str, str] = {
    "ubuntu-18.04": "ubuntu-24.04 or ubuntu-latest",
    "ubuntu-20.04": "ubuntu-24.04 or ubuntu-latest",
    "macos-11": "macos-14 or macos-latest",
    "macos-12": "macos-14 or macos-latest",
    "windows-2019": "windows-2022 or windows-latest",
}

PUBLISH_ACTIONS = (
    "pypa/gh-action-pypi-publish",
    "softprops/action-gh-release",
    "ncipollo/release-action",
    "js-devtools/npm-publish",
)

PUBLISH_CMD_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:npm\s+publish|pnpm\s+publish|yarn\s+publish|"
    r"twine\s+upload|cargo\s+publish|gh\s+release\s+(?:create|upload))\b"
)

SHELL_BYPASS_RE = re.compile(r"(?:\|\|\s*(?:true|:)\b|;\s*true\b)")
USES_VERSION_RE = re.compile(r"^([^@\s]+)@v(\d+)(?:\.\d+)*$", re.IGNORECASE)
RELEASE_NAME_RE = re.compile(r"(?:release|deploy|publish)", re.IGNORECASE)
BLOCK_SCALAR_RE = re.compile(r"^[|>][+-]?\d*$")
KEY_VALUE_RE = re.compile(r'^([A-Za-z0-9_.-]+|"[^"]+"|\'[^\']+\')\s*:(.*)$')
RUNNER_TOKEN_RE = re.compile(r"\b(ubuntu-18\.04|ubuntu-20\.04|macos-11|macos-12|windows-2019)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    rule: str
    severity: str
    message: str


def _strip_comment(text: str) -> str:
    in_single = False
    in_double = False
    for index, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if index == 0 or text[index - 1].isspace():
                return text[:index].rstrip()
    return text.rstrip()


def _unquote(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _parse_key_value(stripped: str) -> tuple[str, str] | None:
    match = KEY_VALUE_RE.match(stripped)
    if not match:
        return None
    key = _unquote(match.group(1))
    val = _strip_comment(match.group(2)).strip()
    return key, val


def _parse_inline_permissions(val: str) -> tuple[str | None, dict[str, str]]:
    cleaned = _unquote(val)
    if cleaned in {"write-all", "read-all"}:
        return cleaned, {}
    if cleaned.startswith("{") and cleaned.endswith("}"):
        inner = cleaned[1:-1].strip()
        if not inner:
            return "empty", {}
        mapping: dict[str, str] = {}
        for part in inner.split(","):
            if ":" in part:
                k, v = part.split(":", 1)
                mapping[_unquote(k).lower()] = _unquote(v).lower()
        return "mapping", mapping
    return None, {}


def _detect_other_ci(root: Path) -> list[str]:
    found: list[str] = []
    for rel in OTHER_CI_FILES:
        candidate = root / Path(rel)
        if candidate.is_file():
            found.append(candidate.relative_to(root).as_posix())
    return sorted(found)


def _discover_github_workflows(root: Path) -> list[Path]:
    workflows_dir = root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return []
    files = [
        p
        for p in workflows_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".yml", ".yaml"}
    ]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def _is_bool_true(val: str) -> bool:
    return _unquote(val).lower() == "true"


def audit_workflow_text(rel_path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = normalized.split("\n")

    # Workflow-level state
    top_perm_line: int | None = None
    top_perm_mode: str | None = None
    top_perm_map: dict[str, tuple[str, int]] = {}

    top_concurrency_line: int | None = None
    top_cancel_in_progress: tuple[bool, int] | None = None

    on_triggers: set[str] = set()
    on_has_tags = False
    on_has_branches = False

    jobs: list[dict[str, Any]] = []

    section: str | None = None
    section_indent = 0

    current_job: dict[str, Any] | None = None
    job_indent: int | None = None
    job_subsection: str | None = None
    job_subsection_indent = 0

    in_steps = False
    steps_indent = 0
    current_step: dict[str, Any] | None = None
    step_item_indent = 0

    in_run_block = False
    run_block_indent = 0

    for idx, raw_line in enumerate(raw_lines, start=1):
        stripped_raw = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        # Handle multiline `run:` block first so shell contents aren't parsed as YAML keys.
        if in_run_block:
            if not stripped_raw or indent > run_block_indent:
                if current_step is not None and stripped_raw:
                    current_step["run_lines"].append((idx, stripped_raw))
                continue
            in_run_block = False

        if not stripped_raw or stripped_raw.startswith("#"):
            continue

        # Top-level key
        if indent == 0 and not stripped_raw.startswith("-"):
            current_job = None
            job_subsection = None
            in_steps = False
            current_step = None
            kv = _parse_key_value(stripped_raw)
            if kv is None:
                section = None
                continue
            key, val = kv
            key_lower = key.lower()
            section = key_lower
            section_indent = 0

            if key_lower == "on":
                if val:
                    cleaned = val.strip("[]")
                    for token in cleaned.split(","):
                        tok = _unquote(token).lower()
                        if tok:
                            on_triggers.add(tok)
            elif key_lower == "permissions":
                top_perm_line = idx
                if val:
                    mode, mapping = _parse_inline_permissions(val)
                    top_perm_mode = mode
                    for pk, pv in mapping.items():
                        top_perm_map[pk] = (pv, idx)
                else:
                    top_perm_mode = "mapping"
            elif key_lower == "concurrency":
                top_concurrency_line = idx
            continue

        # Inside top-level `on:`
        if section == "on":
            kv = _parse_key_value(stripped_raw)
            if kv is not None:
                k, v = kv
                kl = k.lower()
                if indent <= 2:
                    on_triggers.add(kl)
                if kl == "tags":
                    on_has_tags = True
                if kl == "branches":
                    on_has_branches = True
                if kl == "release":
                    on_triggers.add("release")
            continue

        # Inside top-level `permissions:`
        if section == "permissions":
            kv = _parse_key_value(stripped_raw)
            if kv is not None:
                k, v = kv
                top_perm_map[k.lower()] = (_unquote(v).lower(), idx)
            continue

        # Inside top-level `concurrency:`
        if section == "concurrency":
            kv = _parse_key_value(stripped_raw)
            if kv is not None:
                k, v = kv
                if k.lower() == "cancel-in-progress":
                    top_cancel_in_progress = (_is_bool_true(v), idx)
            continue

        # Inside top-level `jobs:`
        if section == "jobs":
            if job_indent is None or indent <= job_indent:
                kv = _parse_key_value(stripped_raw)
                if kv is not None:
                    job_id, _ = kv
                    job_indent = indent
                    current_job = {
                        "id": job_id,
                        "name": "",
                        "line": idx,
                        "has_permissions": False,
                        "perm_line": None,
                        "perm_mode": None,
                        "perm_map": {},
                        "has_concurrency": False,
                        "cancel_in_progress": None,
                        "has_environment": False,
                        "has_if": False,
                        "runs_on_lines": [],
                        "steps": [],
                    }
                    jobs.append(current_job)
                    job_subsection = None
                    in_steps = False
                    current_step = None
                    continue

            if current_job is None:
                continue

            # Leaving steps if indentation drops back to or below steps_indent
            if in_steps and indent <= steps_indent:
                in_steps = False
                current_step = None

            # Leaving job subsection if indentation drops
            if job_subsection is not None and indent <= job_subsection_indent:
                job_subsection = None

            if in_steps:
                if stripped_raw.startswith("-"):
                    step_item_indent = indent
                    current_step = {
                        "line": idx,
                        "name": "",
                        "uses": [],
                        "continue_on_error": None,
                        "run_lines": [],
                    }
                    current_job["steps"].append(current_step)
                    rest = stripped_raw[1:].strip()
                    if rest:
                        kv = _parse_key_value(rest)
                        if kv is not None:
                            _record_step_kv(current_step, kv[0], kv[1], idx)
                            if kv[0].lower() == "run" and BLOCK_SCALAR_RE.fullmatch(kv[1]):
                                in_run_block = True
                                run_block_indent = indent + 2
                    continue

                if current_step is not None and indent > step_item_indent:
                    kv = _parse_key_value(stripped_raw)
                    if kv is not None:
                        _record_step_kv(current_step, kv[0], kv[1], idx)
                        if kv[0].lower() == "run" and BLOCK_SCALAR_RE.fullmatch(kv[1]):
                            in_run_block = True
                            run_block_indent = indent
                    continue

            # Inside a job subsection (permissions, concurrency, strategy)
            if job_subsection == "permissions":
                kv = _parse_key_value(stripped_raw)
                if kv is not None:
                    current_job["perm_map"][kv[0].lower()] = (_unquote(kv[1]).lower(), idx)
                continue

            if job_subsection == "concurrency":
                kv = _parse_key_value(stripped_raw)
                if kv is not None and kv[0].lower() == "cancel-in-progress":
                    current_job["cancel_in_progress"] = (_is_bool_true(kv[1]), idx)
                continue

            if job_subsection == "strategy":
                # Capture deprecated runners declared in matrix lists
                for match in RUNNER_TOKEN_RE.finditer(_strip_comment(stripped_raw)):
                    current_job["runs_on_lines"].append((idx, match.group(1).lower()))
                continue

            # Direct job-level property
            kv = _parse_key_value(stripped_raw)
            if kv is None:
                continue
            jk, jv = kv
            jkl = jk.lower()

            if jkl == "name":
                current_job["name"] = _unquote(jv)
            elif jkl == "permissions":
                current_job["has_permissions"] = True
                current_job["perm_line"] = idx
                if jv:
                    mode, mapping = _parse_inline_permissions(jv)
                    current_job["perm_mode"] = mode
                    for pk, pv in mapping.items():
                        current_job["perm_map"][pk] = (pv, idx)
                else:
                    current_job["perm_mode"] = "mapping"
                    job_subsection = "permissions"
                    job_subsection_indent = indent
            elif jkl == "concurrency":
                current_job["has_concurrency"] = True
                if not jv:
                    job_subsection = "concurrency"
                    job_subsection_indent = indent
            elif jkl == "environment":
                current_job["has_environment"] = True
            elif jkl == "if":
                current_job["has_if"] = True
            elif jkl == "runs-on":
                for match in RUNNER_TOKEN_RE.finditer(jv):
                    current_job["runs_on_lines"].append((idx, match.group(1).lower()))
            elif jkl == "strategy":
                job_subsection = "strategy"
                job_subsection_indent = indent
            elif jkl == "steps":
                in_steps = True
                steps_indent = indent
                current_step = None

    # --- Evaluate static rules ---

    # Determine whether workflow is release/deploy-oriented
    filename = Path(rel_path).name
    is_release_workflow = (
        bool(RELEASE_NAME_RE.search(filename))
        or "release" in on_triggers
        or on_has_tags
    )
    is_restricted_release_trigger = (
        bool(on_triggers)
        and "pull_request" not in on_triggers
        and "pull_request_target" not in on_triggers
        and (
            on_triggers.issubset({"release", "workflow_dispatch"})
            or (
                on_triggers.issubset({"push", "release", "workflow_dispatch"})
                and on_has_tags
                and not on_has_branches
            )
        )
    )

    # 1. Permissions checks
    if top_perm_line is not None:
        if top_perm_mode == "write-all":
            findings.append(
                Finding(
                    rel_path,
                    top_perm_line,
                    "broad-permissions",
                    "error",
                    "top-level `permissions: write-all` grants unrestricted token scope; use `contents: read` or `{}` and scope writes per job",
                )
            )
        for scope, (level, line_no) in top_perm_map.items():
            if level == "write":
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        "broad-top-level-permissions",
                        "error",
                        f"top-level `{scope}: write` is overly broad; keep top-level permissions read-only and grant `{scope}: write` on the specific job",
                    )
                )
    else:
        if not jobs or any(not job["has_permissions"] for job in jobs):
            findings.append(
                Finding(
                    rel_path,
                    1,
                    "missing-permissions",
                    "error",
                    "workflow lacks explicit `permissions:`; declare top-level `permissions: { contents: read }` (or `{}`) and scope job overrides",
                )
            )

    for job in jobs:
        if job["perm_mode"] == "write-all":
            findings.append(
                Finding(
                    rel_path,
                    job["perm_line"] or job["line"],
                    "broad-permissions",
                    "error",
                    f"job `{job['id']}` sets `permissions: write-all`; grant only the minimal scopes required",
                )
            )

    # 2. Concurrency checks
    if top_concurrency_line is None:
        if not jobs or any(not job["has_concurrency"] for job in jobs):
            findings.append(
                Finding(
                    rel_path,
                    1,
                    "missing-concurrency",
                    "error",
                    "workflow lacks `concurrency:` group; set `cancel-in-progress: true` on PR/branch CI or `false` on release/deploy workflows",
                )
            )
    elif top_cancel_in_progress is not None:
        cancel_val, cancel_line = top_cancel_in_progress
        if cancel_val and is_release_workflow:
            findings.append(
                Finding(
                    rel_path,
                    cancel_line,
                    "release-cancel-in-progress",
                    "error",
                    "release/deploy workflow must not set `cancel-in-progress: true`; use `cancel-in-progress: false` to avoid aborted releases",
                )
            )

    for job in jobs:
        if job["cancel_in_progress"] is not None:
            cancel_val, cancel_line = job["cancel_in_progress"]
            job_is_release = is_release_workflow or bool(
                RELEASE_NAME_RE.search(job["id"]) or RELEASE_NAME_RE.search(job["name"])
            )
            if cancel_val and job_is_release:
                findings.append(
                    Finding(
                        rel_path,
                        cancel_line,
                        "release-cancel-in-progress",
                        "error",
                        f"release/deploy job `{job['id']}` must not set `cancel-in-progress: true`",
                    )
                )

    # 3, 4, 5. Per-job and per-step checks
    top_has_oidc = top_perm_map.get("id-token", ("", 0))[0] == "write"
    for job in jobs:
        # Deprecated runners
        seen_runners: set[tuple[int, str]] = set()
        for line_no, runner in job["runs_on_lines"]:
            key = (line_no, runner)
            if key in seen_runners:
                continue
            seen_runners.add(key)
            replacement = DEPRECATED_RUNNERS.get(runner)
            if replacement:
                findings.append(
                    Finding(
                        rel_path,
                        line_no,
                        "deprecated-runner",
                        "error",
                        f"deprecated runner `{runner}` in job `{job['id']}`; upgrade to {replacement}",
                    )
                )

        # Unguarded OIDC
        job_oidc_entry = job["perm_map"].get("id-token")
        job_has_oidc = job_oidc_entry is not None and job_oidc_entry[0] == "write"
        if job_has_oidc or top_has_oidc:
            if not job["has_environment"] and not job["has_if"]:
                oidc_line = (
                    job_oidc_entry[1]
                    if job_has_oidc and job_oidc_entry is not None
                    else top_perm_map["id-token"][1]
                )
                findings.append(
                    Finding(
                        rel_path,
                        oidc_line,
                        "unguarded-oidc",
                        "error",
                        f"job `{job['id']}` uses `id-token: write` without an explicit `environment:` or `if:` guard",
                    )
                )

        for step in job["steps"]:
            # Gate weakening: continue-on-error
            if step["continue_on_error"] is not None:
                coe_val, coe_line = step["continue_on_error"]
                if coe_val:
                    findings.append(
                        Finding(
                            rel_path,
                            coe_line,
                            "gate-weakening-continue-on-error",
                            "error",
                            f"step in job `{job['id']}` sets `continue-on-error: true`, weakening the CI gate",
                        )
                    )

            # Deprecated actions + unguarded publish actions
            for uses_line, uses_ref in step["uses"]:
                cleaned_uses = _unquote(uses_ref)
                match = USES_VERSION_RE.match(cleaned_uses)
                if match:
                    action_name = match.group(1).lower()
                    major = int(match.group(2))
                    dep = DEPRECATED_ACTIONS.get(action_name)
                    if dep and major <= dep[0]:
                        findings.append(
                            Finding(
                                rel_path,
                                uses_line,
                                "deprecated-action",
                                "error",
                                f"deprecated action `{cleaned_uses}` in job `{job['id']}`; upgrade to {dep[1]}",
                            )
                        )
                lower_uses = cleaned_uses.lower()
                if any(lower_uses.startswith(pub + "@") for pub in PUBLISH_ACTIONS):
                    if (
                        not job["has_environment"]
                        and not job["has_if"]
                        and not is_restricted_release_trigger
                    ):
                        findings.append(
                            Finding(
                                rel_path,
                                uses_line,
                                "unguarded-publish",
                                "error",
                                f"publish/release action `{cleaned_uses}` in job `{job['id']}` lacks `environment:`, `if:`, or tag/release-only trigger",
                            )
                        )

            # Gate weakening (`|| true`) + unguarded publish commands in `run:`
            for run_line, cmd_text in step["run_lines"]:
                stripped_cmd = cmd_text.strip()
                if not stripped_cmd or stripped_cmd.startswith("#"):
                    continue
                effective_cmd = _strip_comment(stripped_cmd)
                if SHELL_BYPASS_RE.search(effective_cmd):
                    findings.append(
                        Finding(
                            rel_path,
                            run_line,
                            "gate-weakening-shell-bypass",
                            "error",
                            f"command in job `{job['id']}` swallows failures with `|| true` / `|| :` / `; true`",
                        )
                    )
                if PUBLISH_CMD_RE.search(effective_cmd):
                    if (
                        not job["has_environment"]
                        and not job["has_if"]
                        and not is_restricted_release_trigger
                    ):
                        findings.append(
                            Finding(
                                rel_path,
                                run_line,
                                "unguarded-publish",
                                "error",
                                f"publish/release command in job `{job['id']}` lacks `environment:`, `if:`, or tag/release-only trigger",
                            )
                        )

    return findings


def _record_step_kv(step: dict[str, Any], key: str, val: str, line_no: int) -> None:
    kl = key.lower()
    if kl == "name":
        step["name"] = _unquote(val)
    elif kl == "uses" and val:
        step["uses"].append((line_no, val))
    elif kl == "continue-on-error":
        step["continue_on_error"] = (_is_bool_true(val), line_no)
    elif kl == "run" and val and not BLOCK_SCALAR_RE.fullmatch(val):
        step["run_lines"].append((line_no, val))


def audit_repository(root: Path) -> dict[str, Any]:
    resolved_root = root.resolve()
    gh_workflows = _discover_github_workflows(resolved_root)
    other_ci = _detect_other_ci(resolved_root)

    if not gh_workflows:
        provider_status = "non-github-ci" if other_ci else "no-ci-workflows"
        return {
            "root": resolved_root.as_posix(),
            "provider_status": provider_status,
            "workflows_checked": 0,
            "other_ci_files": other_ci,
            "findings": [],
            "ok": True,
        }

    all_findings: list[Finding] = []
    for wf in gh_workflows:
        rel_path = wf.relative_to(resolved_root).as_posix()
        try:
            text = wf.read_bytes().decode("utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            all_findings.append(
                Finding(
                    rel_path,
                    1,
                    "unreadable-workflow",
                    "error",
                    f"unable to read workflow as UTF-8: {exc}",
                )
            )
            continue
        all_findings.extend(audit_workflow_text(rel_path, text))

    has_errors = any(f.severity == "error" for f in all_findings)
    return {
        "root": resolved_root.as_posix(),
        "provider_status": "github-actions",
        "workflows_checked": len(gh_workflows),
        "other_ci_files": other_ci,
        "findings": [asdict(f) for f in all_findings],
        "ok": not has_errors,
    }


def _write_workflow(root: Path, name: str, content: str, *, crlf: bool = False) -> Path:
    wf_dir = root / ".github" / "workflows"
    wf_dir.mkdir(parents=True, exist_ok=True)
    path = wf_dir / name
    payload = content.replace("\n", "\r\n") if crlf else content
    path.write_bytes(payload.encode("utf-8"))
    return path


def self_test() -> int:
    # 1. Clean passing PR CI workflow + guarded release workflow (including CRLF)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "ci.yml",
            """name: CI
on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Run checks
        run: |
          # comments with || true are ignored
          ruff check .
          pytest -q
""",
            crlf=True,
        )
        _write_workflow(
            root,
            "release.yml",
            """name: Release
on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  publish:
    runs-on: ubuntu-24.04
    environment: pypi
    permissions:
      contents: write
      id-token: write
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v4
      - uses: pypa/gh-action-pypi-publish@release/v1
""",
        )
        res = audit_repository(root)
        assert res["ok"], f"expected clean workflows to pass, got: {res['findings']}"
        assert res["workflows_checked"] == 2
        assert res["provider_status"] == "github-actions"

    # 2. Graceful behavior when no CI workflows exist
    with tempfile.TemporaryDirectory() as td:
        res = audit_repository(Path(td))
        assert res["ok"], f"expected no-ci repo to pass gracefully: {res}"
        assert res["provider_status"] == "no-ci-workflows"

    # 3. Graceful behavior when another CI provider exists
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".gitlab-ci.yml").write_text("stages:\n  - test\n", encoding="utf-8")
        res = audit_repository(root)
        assert res["ok"], f"expected non-github CI repo to pass gracefully: {res}"
        assert res["provider_status"] == "non-github-ci"
        assert ".gitlab-ci.yml" in res["other_ci_files"]

    # 4. Missing permissions + missing concurrency + deprecated actions/runner + gate weakening
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "broken.yaml",
            """name: Broken
on: [pull_request]
jobs:
  test:
    runs-on: ubuntu-20.04
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - name: Weak lint
        continue-on-error: true
        run: ruff check .
      - name: Weak test
        run: |
          pytest || true
""",
        )
        res = audit_repository(root)
        assert not res["ok"], "expected broken workflow to fail"
        rules = {f["rule"] for f in res["findings"]}
        expected = {
            "missing-permissions",
            "missing-concurrency",
            "deprecated-runner",
            "deprecated-action",
            "gate-weakening-continue-on-error",
            "gate-weakening-shell-bypass",
        }
        assert expected.issubset(rules), f"missing expected rules: {expected - rules} (got {rules})"
        assert all("\\" not in f["file"] for f in res["findings"]), "paths must be POSIX-normalized"

    # 5. Broad permissions (write-all & top-level write) + release cancel-in-progress + unguarded OIDC/publish
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "release-bad.yml",
            """name: Release Bad
on:
  pull_request:
  push:
    tags:
      - "v*"

permissions:
  contents: write
  id-token: write

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm publish
""",
        )
        _write_workflow(
            root,
            "write-all.yml",
            """name: WriteAll
on: [push]
permissions: write-all
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
""",
        )
        res = audit_repository(root)
        assert not res["ok"], "expected insecure release/write-all workflows to fail"
        rules = {f["rule"] for f in res["findings"]}
        expected = {
            "broad-top-level-permissions",
            "broad-permissions",
            "release-cancel-in-progress",
            "unguarded-oidc",
            "unguarded-publish",
        }
        assert expected.issubset(rules), f"missing expected rules: {expected - rules} (got {rules})"

    # 6. Guarded OIDC with `if:` (without `environment:`) passes
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "guarded-if.yml",
            """name: Guarded
on:
  push:
    tags:
      - "v*"

permissions: {}

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  publish:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-latest
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - run: twine upload dist/*
""",
        )
        res = audit_repository(root)
        assert res["ok"], f"expected if-guarded OIDC workflow to pass, got: {res['findings']}"

    # 7. Dash-line block scalar (`- run: |`) followed by sibling `continue-on-error: true`
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "dash-run-block.yml",
            """name: Dash Run Block
on: [pull_request]
permissions:
  contents: read
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: |
          pytest -q
        continue-on-error: true
""",
        )
        res = audit_repository(root)
        assert not res["ok"], "expected sibling continue-on-error after `- run: |` to fail"
        rules = {f["rule"] for f in res["findings"]}
        assert "gate-weakening-continue-on-error" in rules, f"expected gate-weakening-continue-on-error, got: {rules}"

    # 8. `on: push:` with both `branches:` and `tags:` is not treated as tag-restricted
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_workflow(
            root,
            "push-branches-and-tags.yml",
            """name: Push Branches And Tags
on:
  push:
    branches:
      - main
    tags:
      - "v*"
permissions:
  contents: read
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm publish
""",
        )
        res = audit_repository(root)
        assert not res["ok"], "expected push with branches+tags and unguarded publish to fail"
        rules = {f["rule"] for f in res["findings"]}
        assert "unguarded-publish" in rules, f"expected unguarded-publish, got: {rules}"

    print("verify_cicd.py self-test: PASS (8 scenarios verified)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Statically audit CI/CD workflow files for least-privilege, concurrency, gate integrity, and supply-chain hygiene."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("."),
        help="Workspace root directory to inspect (default: current directory).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON report.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in self-tests and exit.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    if not args.root.exists():
        print(f"ERROR: root path does not exist: {args.root}", file=sys.stderr)
        return 2

    report = audit_repository(args.root)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        status = report["provider_status"]
        if status == "no-ci-workflows":
            print(f"OK: no CI workflows detected under {report['root']} (vendor-agnostic; no workflows required)")
        elif status == "non-github-ci":
            providers = ", ".join(report["other_ci_files"])
            print(f"OK: non-GitHub CI detected ({providers}); GitHub Actions static audit skipped")
        else:
            count = report["workflows_checked"]
            findings = report["findings"]
            if not findings:
                print(f"OK: {count} GitHub Actions workflow(s) passed static CI/CD verification")
            else:
                print(f"FAIL: {len(findings)} issue(s) found across {count} GitHub Actions workflow(s):")
                for item in findings:
                    print(
                        f"  - {item['file']}:{item['line']} [{item['severity']}:{item['rule']}] {item['message']}"
                    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
