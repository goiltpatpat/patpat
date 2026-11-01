#!/usr/bin/env python3
"""Measure the ambient skill surface a host loads into every session. No git writes.

A skill is ambient when the model may trigger it on its own: its SKILL.md lacks
`disable-model-invocation: true` (Claude Code, Cursor) and its Codex
`agents/openai.yaml` does not set `allow_implicit_invocation: false`. Every
ambient description is loaded into context on each session, so this eval
reports their count and bytes and gates them against the invocation policy.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# The skills the model may trigger without an explicit user request, per host.
# Everything else is reached through /patpat (or $patpat) or a direct slash call.
# Codex keeps the Patpat entry explicit-only; Claude Code and Cursor need it
# loadable so "Use patpat to ..." and the sticky hook context can reach it.
CODEX_AMBIENT_SKILLS = frozenset({"patpat-inspect"})
CLAUDE_AMBIENT_SKILLS = CODEX_AMBIENT_SKILLS | {"patpat", "patpat-loop"}
# Upper bound on the bytes of ambient descriptions loaded per session on any host.
AMBIENT_DESCRIPTION_BUDGET = 600

FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
CODEX_EXPLICIT = re.compile(r"(?m)^policy:\r?\n[ \t]+allow_implicit_invocation:[ \t]*false[ \t]*$")


def _frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER.match(text)
    if match is None:
        raise ValueError("missing frontmatter")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if line[:1].isspace() or ":" not in line:
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip().strip("'\"")
    return fields


def survey(root: Path) -> list[dict[str, object]]:
    rows = []
    for skill_file in sorted((root / "skills").glob("*/SKILL.md")):
        fields = _frontmatter(skill_file.read_text(encoding="utf-8"))
        codex_config = skill_file.parent / "agents" / "openai.yaml"
        codex_explicit = codex_config.is_file() and CODEX_EXPLICIT.search(
            codex_config.read_text(encoding="utf-8")
        ) is not None
        rows.append(
            {
                "skill": skill_file.parent.name,
                "description_bytes": len(fields.get("description", "").encode("utf-8")),
                "claude_ambient": fields.get("disable-model-invocation") != "true",
                "codex_ambient": not codex_explicit,
            }
        )
    return rows


def summarize(rows: list[dict[str, object]]) -> dict[str, object]:
    summary: dict[str, object] = {"skills": len(rows)}
    for host in ("claude", "codex"):
        ambient = [row for row in rows if row[f"{host}_ambient"]]
        summary[f"{host}_ambient_skills"] = sorted(str(row["skill"]) for row in ambient)
        summary[f"{host}_ambient_description_bytes"] = sum(
            int(row["description_bytes"]) for row in ambient
        )
    return summary


def policy_errors(summary: dict[str, object]) -> list[str]:
    errors = []
    for host, expected in (("claude", CLAUDE_AMBIENT_SKILLS), ("codex", CODEX_AMBIENT_SKILLS)):
        ambient = set(summary[f"{host}_ambient_skills"])  # type: ignore[arg-type]
        if ambient != expected:
            errors.append(f"{host} ambient skills {sorted(ambient)} differ from policy {sorted(expected)}")
        used = int(summary[f"{host}_ambient_description_bytes"])  # type: ignore[arg-type]
        if used > AMBIENT_DESCRIPTION_BUDGET:
            errors.append(
                f"{host} ambient descriptions use {used} bytes, over the {AMBIENT_DESCRIPTION_BUDGET}-byte budget"
            )
    return errors


def render_report(rows: list[dict[str, object]], summary: dict[str, object]) -> str:
    lines = [
        "| Skill | Description bytes | Claude ambient | Codex ambient |",
        "| --- | ---: | :---: | :---: |",
    ]
    for row in rows:
        lines.append(
            f"| `{row['skill']}` | {row['description_bytes']} | "
            f"{'yes' if row['claude_ambient'] else 'no'} | {'yes' if row['codex_ambient'] else 'no'} |"
        )
    lines.append("")
    for host in ("claude", "codex"):
        lines.append(
            f"{host} ambient: {len(summary[f'{host}_ambient_skills'])} of {summary['skills']} skills, "  # type: ignore[arg-type]
            f"{summary[f'{host}_ambient_description_bytes']} description bytes."
        )
    return "\n".join(lines) + "\n"


def run_self_test() -> None:
    sample = [
        {"skill": "a", "description_bytes": 100, "claude_ambient": True, "codex_ambient": True},
        {"skill": "b", "description_bytes": 900, "claude_ambient": False, "codex_ambient": True},
    ]
    summary = summarize(sample)
    assert summary["claude_ambient_skills"] == ["a"], summary
    assert summary["codex_ambient_skills"] == ["a", "b"], summary
    assert summary["codex_ambient_description_bytes"] == 1000, summary
    assert len(policy_errors(summary)) == 3, policy_errors(summary)
    assert _frontmatter("---\nname: x\ndisable-model-invocation: true\n---\n") == {
        "name": "x",
        "disable-model-invocation": "true",
    }

    errors = policy_errors(summarize(survey(ROOT)))
    if errors:
        raise AssertionError("; ".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    parser.add_argument("--report", type=Path, help="write a Markdown table to this path")
    parser.add_argument("--self-test", action="store_true", help="check the eval and gate the repository policy")
    args = parser.parse_args()

    if args.self_test:
        try:
            run_self_test()
        except AssertionError as error:
            print(f"Routing surface eval failed: {error}", file=sys.stderr)
            return 1
        print("Routing surface eval passed.")
        return 0

    rows = survey(args.root)
    summary = summarize(rows)
    if args.report:
        args.report.write_text(render_report(rows, summary), encoding="utf-8")
    print(json.dumps(summary, indent=2) if args.json else render_report(rows, summary), end="")
    errors = policy_errors(summary)
    for error in errors:
        print(f"policy: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
