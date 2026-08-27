#!/usr/bin/env python3
"""Validate Patpat manifests, skills, and internal references."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path


NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ALLOWED_FRONTMATTER = {"name", "description"}
PUBLISHED_SOURCE = "https://github.com/goiltpatpat/patpat"
ALLOWED_SKILL_POLICIES = {"mutating", "read-only", "support", "router"}
SKILL_POLICIES = {
    "patpat-architect": "read-only",
    "patpat-automation": "mutating",
    "patpat-change": "mutating",
    "patpat-debug": "mutating",
    "patpat-engineer": "mutating",
    "patpat-eval": "support",
    "patpat-impact": "read-only",
    "patpat-inspect": "read-only",
    "patpat-learn": "mutating",
    "patpat-loop": "router",
    "patpat-perf": "mutating",
    "patpat-plan": "read-only",
    "patpat-review": "read-only",
    "patpat-run": "mutating",
    "patpat-setup": "mutating",
    "patpat-ship": "mutating",
    "patpat-skill": "mutating",
    "patpat-verifier": "mutating",
    "patpat-verify": "read-only",
}
EXPECTED_MUTATING_SKILLS = {
    "patpat-automation",
    "patpat-change",
    "patpat-debug",
    "patpat-engineer",
    "patpat-learn",
    "patpat-perf",
    "patpat-run",
    "patpat-setup",
    "patpat-ship",
    "patpat-skill",
    "patpat-verifier",
}
MUTATING_SKILLS = {name for name, policy in SKILL_POLICIES.items() if policy == "mutating"}
REVIEWER_DESCRIPTION = (
    "Independently challenge an implementation and its verification evidence "
    "without modifying repository or external state."
)
PROOF_CLOSURE_BLOCK = """## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)"""
READ_ONLY_BOUNDARY_BLOCK = """## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`."""
UNADMITTED_COMPONENT_PATHS = {
    ".cursor",
    ".mcp.json",
    "automations",
    "commands",
    "hooks",
    "hooks.json",
    "mcp",
    "mcp-servers",
    "mcp_config.json",
    "rules",
}


def operational_markdown(text: str) -> str:
    without_comments = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    return re.sub(r"```.*?```|~~~.*?~~~", "", without_comments, flags=re.DOTALL)


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as error:
        raise ValueError("missing closing frontmatter delimiter") from error

    data: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise ValueError(f"unsupported frontmatter line: {line}")
        normalized_key = key.strip()
        if normalized_key in data:
            raise ValueError(f"duplicate frontmatter key: {normalized_key}")
        data[normalized_key] = value.strip().strip('"').strip("'")
    return data, "\n".join(lines[end + 1 :]).strip()


def validate_json(path: Path, errors: list[str]) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"{path}: invalid JSON: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path}: root must be an object")
        return {}
    return value


def validate_links(path: Path, root: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    for raw_target in LINK_PATTERN.findall(text):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            errors.append(f"{path}: reference escapes plugin root: {raw_target}")
            continue
        if not resolved.exists():
            errors.append(f"{path}: broken reference: {raw_target}")


def linked_markdown(path: Path, root: Path) -> list[Path]:
    targets: list[Path] = []
    text = path.read_text(encoding="utf-8")
    for raw_target in LINK_PATTERN.findall(text):
        target = raw_target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        resolved = (path.parent / target).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        if resolved.is_file() and resolved.suffix.lower() == ".md":
            targets.append(resolved)
    return targets


def reachable_markdown(entrypoint: Path, root: Path, excluded: set[Path] | None = None) -> set[Path]:
    reached: set[Path] = set()
    pending = [entrypoint.resolve()]
    excluded = excluded or set()
    while pending:
        path = pending.pop()
        if path in reached or path in excluded or not path.is_file():
            continue
        reached.add(path)
        pending.extend(linked_markdown(path, root))
    return reached


def parse_agent_frontmatter(path: Path) -> tuple[dict[str, object], str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening frontmatter delimiter")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as error:
        raise ValueError("missing closing frontmatter delimiter") from error

    data: dict[str, object] = {}
    active_list: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("  - "):
            if active_list is None:
                raise ValueError(f"list item without key: {line}")
            value = line[4:].strip()
            assert isinstance(data[active_list], list)
            data[active_list].append(value)
            continue
        if line[:1].isspace():
            raise ValueError(f"unsupported nested frontmatter: {line}")
        key, separator, value = line.partition(":")
        if not separator or not key.strip():
            raise ValueError(f"unsupported frontmatter line: {line}")
        key = key.strip()
        if key in data:
            raise ValueError(f"duplicate frontmatter key: {key}")
        value = value.strip()
        if not value:
            data[key] = []
            active_list = key
        elif value in {"true", "false"}:
            data[key] = value == "true"
            active_list = None
        else:
            data[key] = value.strip('"').strip("'")
            active_list = None
    return data, "\n".join(lines[end + 1 :]).strip()


def validate_agent_adapters(root: Path, parsed: dict[str, dict[str, object]], errors: list[str]) -> None:
    cursor_directory = root / "adapters" / "cursor" / "agents"
    antigravity_directory = root / "agents"
    expected = {"patpat-reviewer"}

    if parsed.get("cursor", {}).get("agents") != "./adapters/cursor/agents/":
        errors.append("Cursor manifest agents must point to ./adapters/cursor/agents/")
    if "agents" in parsed.get("codex", {}):
        errors.append("Codex manifest must not claim packaged agents")

    for directory in (cursor_directory, antigravity_directory):
        if not directory.is_dir():
            errors.append(f"{directory}: missing agent adapter directory")
            continue
        files = {
            path.relative_to(directory)
            for path in directory.rglob("*")
            if path.is_file() or path.is_symlink()
        }
        expected_files = {Path("patpat-reviewer.md")}
        if files != expected_files:
            errors.append(f"{directory}: expected agent adapters {sorted(expected)}")
        for path in directory.rglob("*"):
            if path.is_symlink():
                errors.append(f"{path}: symlinks are not allowed in agent adapters")

    cursor_expected = {"patpat-reviewer": {"readonly": True}}
    for name, required in cursor_expected.items():
        path = cursor_directory / f"{name}.md"
        if not path.is_file():
            continue
        try:
            data, body = parse_agent_frontmatter(path)
        except (OSError, ValueError) as error:
            errors.append(f"{path}: {error}")
            continue
        unknown = set(data) - {"name", "description", "model", "readonly", "is_background"}
        if unknown:
            errors.append(f"{path}: unsupported Cursor agent fields {sorted(unknown)}")
        if data.get("name") != name or data.get("model") != "inherit":
            errors.append(f"{path}: invalid Cursor agent identity or model")
        if data.get("description") != REVIEWER_DESCRIPTION:
            errors.append(f"{path}: Cursor agent description must remain canonical")
        if data.get("readonly") is not required["readonly"]:
            errors.append(f"{path}: unexpected Cursor readonly policy")
        if data.get("is_background") is not False:
            errors.append(f"{path}: Cursor agent must not run in background by default")
        if not body:
            errors.append(f"{path}: agent body is required")
        expected_body = (
            "# Patpat Reviewer Adapter\n\n"
            "Read and follow the canonical [`patpat-review`](../../../skills/patpat-review/SKILL.md) "
            "contract in full. Remain read-only, report evidence-backed findings, and never authorize delivery."
        )
        if body != expected_body:
            errors.append(f"{path}: Cursor adapter body must remain the canonical thin wrapper")

    antigravity_expected = {
        "patpat-reviewer": {
            "skills": ["skills/patpat-review"],
            "tools": ["view_file", "grep_search"],
        },
    }
    for name, required in antigravity_expected.items():
        path = antigravity_directory / f"{name}.md"
        if not path.is_file():
            continue
        try:
            data, body = parse_agent_frontmatter(path)
        except (OSError, ValueError) as error:
            errors.append(f"{path}: {error}")
            continue
        unknown = set(data) - {
            "name",
            "description",
            "tools",
            "mainAgent",
            "subagent",
            "model",
            "commandExecutionPolicy",
            "skills",
        }
        if unknown:
            errors.append(f"{path}: unsupported Antigravity agent fields {sorted(unknown)}")
        if data.get("name") != name:
            errors.append(f"{path}: name must match filename")
        if data.get("description") != REVIEWER_DESCRIPTION:
            errors.append(f"{path}: Antigravity agent description must remain canonical")
        for field, value in {
            "mainAgent": False,
            "subagent": True,
            "model": "inherit",
            "commandExecutionPolicy": "sandbox",
        }.items():
            if data.get(field) != value:
                errors.append(f"{path}: unexpected {field}")
        if data.get("skills") != required["skills"] or data.get("tools") != required["tools"]:
            errors.append(f"{path}: unexpected Antigravity skills or tools")
        if not body:
            errors.append(f"{path}: agent body is required")
        expected_body = (
            "# Patpat Reviewer Adapter\n\n"
            "Read and follow the canonical [`patpat-review`](../skills/patpat-review/SKILL.md) contract "
            "in full. Remain read-only, report evidence-backed findings, and never authorize delivery."
        )
        if body != expected_body:
            errors.append(f"{path}: Antigravity adapter body must remain the canonical thin wrapper")


def validate_root(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in sorted(UNADMITTED_COMPONENT_PATHS):
        if (root / relative).exists() or (root / relative).is_symlink():
            errors.append(f"{root / relative}: unadmitted plugin component path")
    manifests = {
        "antigravity": root / "plugin.json",
        "cursor": root / ".cursor-plugin" / "plugin.json",
        "codex": root / ".codex-plugin" / "plugin.json",
    }
    parsed: dict[str, dict[str, object]] = {}
    for host, path in manifests.items():
        if not path.is_file():
            errors.append(f"{path}: missing {host} manifest")
        else:
            parsed[host] = validate_json(path, errors)

    marketplace_path = root / ".agents" / "plugins" / "marketplace.json"
    marketplace = (
        validate_json(marketplace_path, errors)
        if marketplace_path.is_file()
        else {}
    )
    if not marketplace_path.is_file():
        errors.append(f"{marketplace_path}: missing Codex repository marketplace")
    if set(marketplace) != {"name", "interface", "plugins"}:
        errors.append(f"{marketplace_path}: fields do not match the Patpat marketplace contract")
    if marketplace.get("name") != "patpat":
        errors.append(f"{marketplace_path}: marketplace name must be patpat")
    if marketplace.get("interface") != {"displayName": "Patpat"}:
        errors.append(f"{marketplace_path}: marketplace interface must remain canonical")
    expected_marketplace_plugin = {
        "name": "patpat",
        "source": {"source": "local", "path": "./"},
        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
        "category": "Developer Tools",
    }
    if marketplace.get("plugins") != [expected_marketplace_plugin]:
        errors.append(f"{marketplace_path}: plugin entry must remain canonical and root-contained")

    for host, manifest in parsed.items():
        if manifest.get("name") != "patpat":
            errors.append(f"{manifests[host]}: name must be patpat")
    allowed_manifest_keys = {
        "antigravity": {"$schema", "name", "description"},
        "cursor": {
            "name", "displayName", "version", "description", "author", "homepage",
            "repository", "license", "keywords", "category", "tags", "skills",
            "agents",
        },
        "codex": {
            "name", "version", "description", "author", "homepage", "repository",
            "license", "keywords", "skills", "interface",
        },
    }
    for host, manifest in parsed.items():
        unknown = set(manifest) - allowed_manifest_keys[host]
        if unknown:
            errors.append(f"{manifests[host]}: unsupported manifest fields {sorted(unknown)}")
    if parsed.get("antigravity", {}).get("$schema") != "https://antigravity.google/schemas/v1/plugin.json":
        errors.append(f"{manifests['antigravity']}: unexpected schema")
    for host in ("cursor", "codex"):
        if parsed.get(host, {}).get("skills") != "./skills/":
            errors.append(f"{manifests[host]}: skills must point to ./skills/")
    cursor_version = parsed.get("cursor", {}).get("version")
    codex_version = parsed.get("codex", {}).get("version")
    if cursor_version != codex_version:
        errors.append("Cursor and Codex manifest versions must match")
    if not isinstance(cursor_version, str) or not SEMVER_PATTERN.fullmatch(cursor_version):
        errors.append("Cursor and Codex manifest version must be valid semantic versioning")

    manifest_descriptions = [
        parsed.get(host, {}).get("description")
        for host in ("antigravity", "cursor", "codex")
    ]
    if not all(isinstance(description, str) and description for description in manifest_descriptions) or len(set(manifest_descriptions)) != 1:
        errors.append("All host manifest descriptions must match")

    cursor_manifest = parsed.get("cursor", {})
    for field in ("displayName", "description", "version", "skills"):
        if not cursor_manifest.get(field):
            errors.append(f"{manifests['cursor']}: missing required Patpat field {field}")
    for host in ("cursor", "codex"):
        manifest = parsed.get(host, {})
        if manifest.get("homepage") != PUBLISHED_SOURCE or manifest.get("repository") != PUBLISHED_SOURCE:
            errors.append(
                f"{manifests[host]}: homepage and repository must point at the published source"
            )
    codex_interface = parsed.get("codex", {}).get("interface")
    if not isinstance(codex_interface, dict):
        errors.append(f"{manifests['codex']}: interface must be an object")
    else:
        allowed_interface_keys = {
            "displayName", "shortDescription", "longDescription", "developerName",
            "category", "capabilities", "defaultPrompt",
        }
        unknown = set(codex_interface) - allowed_interface_keys
        if unknown:
            errors.append(
                f"{manifests['codex']}: unsupported interface fields {sorted(unknown)}"
            )
        for field in ("displayName", "shortDescription", "developerName"):
            if not codex_interface.get(field):
                errors.append(
                    f"{manifests['codex']}: interface missing required Patpat field {field}"
                )
        if codex_interface.get("capabilities") != ["Interactive", "Read", "Write"]:
            errors.append(
                f"{manifests['codex']}: interface capabilities must disclose Interactive, Read, and Write"
            )
        prompts = codex_interface.get("defaultPrompt")
        if not isinstance(prompts, list) or not any(
            isinstance(item, str) and "$patpat-loop" in item for item in prompts
        ):
            errors.append(f"{manifests['codex']}: defaultPrompt must include $patpat-loop")

    validate_agent_adapters(root, parsed, errors)

    skills_root = root / "skills"
    skills = skill_directories(skills_root) if skills_root.is_dir() else []
    if not skills:
        errors.append(f"{skills_root}: no skills found")
    elif skills_root.is_dir():
        for child in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            if not (child / "SKILL.md").is_file():
                errors.append(f"{child}: immediate skill directory is missing SKILL.md")
    discovered_skill_names = {skill.name for skill in skills}
    invalid_policies = {
        name: policy
        for name, policy in SKILL_POLICIES.items()
        if policy not in ALLOWED_SKILL_POLICIES
    }
    if invalid_policies:
        errors.append(f"Invalid skill policies: {invalid_policies}")
    if MUTATING_SKILLS != EXPECTED_MUTATING_SKILLS:
        errors.append("Mutating skill classifications differ from the reviewed baseline")
    if discovered_skill_names != set(SKILL_POLICIES):
        missing_policy = discovered_skill_names - set(SKILL_POLICIES)
        stale_policy = set(SKILL_POLICIES) - discovered_skill_names
        errors.append(
            "Skill policy registry mismatch: "
            f"unclassified={sorted(missing_policy)}, missing={sorted(stale_policy)}"
        )

    if skills_root.is_dir():
        for directory, directory_names, file_names in os.walk(skills_root, followlinks=False):
            for name in directory_names + file_names:
                path = Path(directory) / name
                if path.is_symlink():
                    errors.append(f"{path}: symlinks are not allowed in canonical skills")

    descriptions: dict[str, Path] = {}
    for skill in skills:
        skill_file = skill / "SKILL.md"
        try:
            frontmatter, body = parse_frontmatter(skill_file)
        except (OSError, ValueError) as error:
            errors.append(f"{skill_file}: {error}")
            continue
        unknown = set(frontmatter) - ALLOWED_FRONTMATTER
        if unknown:
            errors.append(f"{skill_file}: non-portable frontmatter: {sorted(unknown)}")
        name = frontmatter.get("name", "")
        description = frontmatter.get("description", "")
        if name != skill.name:
            errors.append(f"{skill_file}: name must match folder {skill.name}")
        if not NAME_PATTERN.fullmatch(name):
            errors.append(f"{skill_file}: invalid skill name {name!r}")
        if not description:
            errors.append(f"{skill_file}: description is required")
        elif description in descriptions:
            errors.append(
                f"{skill_file}: duplicate description also used by {descriptions[description]}"
            )
        else:
            descriptions[description] = skill_file
        if not body:
            errors.append(f"{skill_file}: body is required")

    agents_guide = root / "AGENTS.md"
    if not agents_guide.is_file():
        errors.append(f"{agents_guide}: missing agent install contract")
    markdown_files = [root / "README.md", agents_guide]
    for folder_name in ("docs", "skills", "agents", "adapters"):
        folder = root / folder_name
        if folder.is_dir():
            markdown_files.extend(folder.rglob("*.md"))
    markdown_files = sorted(path for path in set(markdown_files) if path.is_file())
    for path in markdown_files:
        validate_links(path, root, errors)

    reference_root = root / "skills" / "patpat-loop"
    for folder_name in ("principles", "playbooks", "references"):
        folder = reference_root / folder_name
        if not folder.is_dir() or not any(folder.glob("*.md")):
            errors.append(f"{folder}: missing referenced guidance")

    entrypoint = reference_root / "SKILL.md"
    reached = reachable_markdown(entrypoint, root) if entrypoint.is_file() else set()
    required_references = {(skill / "SKILL.md").resolve() for skill in skills}
    for folder_name in ("principles", "playbooks", "references"):
        required_references.update(
            path.resolve() for path in (reference_root / folder_name).glob("*.md")
        )
    for path in sorted(required_references - reached):
        errors.append(f"{path}: not reachable from patpat-loop")

    proof_targets = {
        (root / "skills" / "patpat-verify" / "SKILL.md").resolve(),
        (root / "skills" / "patpat-review" / "SKILL.md").resolve(),
    }
    excluded = {entrypoint.resolve()}
    for skill_name in sorted(MUTATING_SKILLS):
        workflow = root / "skills" / skill_name / "SKILL.md"
        if not workflow.is_file():
            errors.append(f"{workflow}: missing mutating workflow")
            continue
        closure = reachable_markdown(workflow, root, excluded)
        missing = proof_targets - closure
        if missing:
            labels = ", ".join(sorted(path.parent.name for path in missing))
            errors.append(f"{workflow}: missing proof closure to {labels}")
        operational = operational_markdown(workflow.read_text(encoding="utf-8"))
        if not operational.rstrip().endswith(PROOF_CLOSURE_BLOCK):
            errors.append(f"{workflow}: missing canonical proof closure directive")

    for skill_name, policy in sorted(SKILL_POLICIES.items()):
        if policy != "read-only":
            continue
        workflow = root / "skills" / skill_name / "SKILL.md"
        if not workflow.is_file():
            continue
        operational = operational_markdown(workflow.read_text(encoding="utf-8"))
        if not operational.rstrip().endswith(READ_ONLY_BOUNDARY_BLOCK):
            errors.append(f"{workflow}: missing canonical read-only mutation boundary")

    run_script = root / "skills" / "patpat-run" / "scripts" / "run_state.py"
    if not run_script.is_file():
        errors.append(f"{run_script}: missing durable run engine")
    codex_smoke = root / "scripts" / "smoke_codex_plugin.py"
    if not codex_smoke.is_file():
        errors.append(f"{codex_smoke}: missing isolated Codex marketplace smoke test")
    antigravity_smoke = root / "scripts" / "smoke_antigravity_plugin.py"
    if not antigravity_smoke.is_file():
        errors.append(f"{antigravity_smoke}: missing isolated Antigravity plugin smoke test")
    stage_script = root / "scripts" / "stage_plugin.py"
    if not stage_script.is_file():
        errors.append(f"{stage_script}: missing allowlisted plugin staging script")

    return errors


def skill_directories(skills_root: Path) -> list[Path]:
    return sorted(
        path for path in skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    )


def run_self_test(root: Path) -> list[str]:
    cases: list[tuple[str, Callable[[Path], None], str]] = []

    def break_name(fixture: Path) -> None:
        skill = fixture / "skills" / "patpat-inspect" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(text.replace("name: patpat-inspect", "name: broken-name", 1), encoding="utf-8")

    def remove_skill_file(fixture: Path) -> None:
        (fixture / "skills" / "patpat-inspect" / "SKILL.md").unlink()

    def remove_codex_smoke(fixture: Path) -> None:
        (fixture / "scripts" / "smoke_codex_plugin.py").unlink()

    def remove_antigravity_smoke(fixture: Path) -> None:
        (fixture / "scripts" / "smoke_antigravity_plugin.py").unlink()

    def remove_stage_script(fixture: Path) -> None:
        (fixture / "scripts" / "stage_plugin.py").unlink()

    def remove_agents_guide(fixture: Path) -> None:
        (fixture / "AGENTS.md").unlink()

    def drop_codex_default_prompt(fixture: Path) -> None:
        manifest = fixture / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["interface"]["defaultPrompt"] = ["Use Patpat without naming a skill."]
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def drop_published_source(fixture: Path) -> None:
        manifest = fixture / ".cursor-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        del data["homepage"]
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def drift_version(fixture: Path) -> None:
        manifest = fixture / ".cursor-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["version"] = "9.9.9"
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def invalid_versions(fixture: Path) -> None:
        for relative in (".cursor-plugin/plugin.json", ".codex-plugin/plugin.json"):
            manifest = fixture / relative
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["version"] = "next"
            manifest.write_text(json.dumps(data), encoding="utf-8")

    def escape_marketplace_source(fixture: Path) -> None:
        marketplace = fixture / ".agents" / "plugins" / "marketplace.json"
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        data["plugins"][0]["source"]["path"] = "../outside"
        marketplace.write_text(json.dumps(data), encoding="utf-8")

    def drift_marketplace_policy(fixture: Path) -> None:
        marketplace = fixture / ".agents" / "plugins" / "marketplace.json"
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        data["plugins"][0]["policy"]["authentication"] = "ON_USE"
        marketplace.write_text(json.dumps(data), encoding="utf-8")

    def add_marketplace_plugin(fixture: Path) -> None:
        marketplace = fixture / ".agents" / "plugins" / "marketplace.json"
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        data["plugins"].append(dict(data["plugins"][0]))
        marketplace.write_text(json.dumps(data), encoding="utf-8")

    def drift_description(fixture: Path) -> None:
        manifest = fixture / ".cursor-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["description"] = "Different description"
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def remove_presentation_field(fixture: Path) -> None:
        manifest = fixture / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        del data["interface"]["shortDescription"]
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def understate_codex_capabilities(fixture: Path) -> None:
        manifest = fixture / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["interface"]["capabilities"] = []
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def duplicate_key(fixture: Path) -> None:
        skill = fixture / "skills" / "patpat-inspect" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(text.replace("description:", "name: patpat-inspect\ndescription:", 1), encoding="utf-8")

    def add_skill_symlink(fixture: Path) -> None:
        source = fixture / "README.md"
        destination = fixture / "skills" / "patpat-inspect" / "linked-readme.md"
        destination.symlink_to(source)

    def break_router_reachability(fixture: Path) -> None:
        router = fixture / "skills" / "patpat-loop" / "SKILL.md"
        text = router.read_text(encoding="utf-8")
        router.write_text(
            text.replace("(../patpat-inspect/SKILL.md)", "(SKILL.md)", 1),
            encoding="utf-8",
        )

    def remove_cursor_agent_field(fixture: Path) -> None:
        manifest = fixture / ".cursor-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        del data["agents"]
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def weaken_cursor_reviewer(fixture: Path) -> None:
        agent = fixture / "adapters" / "cursor" / "agents" / "patpat-reviewer.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(text.replace("readonly: true", "readonly: false", 1), encoding="utf-8")

    def enable_background_agent(fixture: Path) -> None:
        agent = fixture / "adapters" / "cursor" / "agents" / "patpat-reviewer.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(text.replace("is_background: false", "is_background: true", 1), encoding="utf-8")

    def remove_agent_adapter(fixture: Path) -> None:
        (fixture / "agents" / "patpat-reviewer.md").unlink()

    def grant_reviewer_command(fixture: Path) -> None:
        agent = fixture / "agents" / "patpat-reviewer.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(text.replace("  - grep_search", "  - grep_search\n  - run_command", 1), encoding="utf-8")

    def drift_adapter_body(fixture: Path) -> None:
        agent = fixture / "adapters" / "cursor" / "agents" / "patpat-reviewer.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(text.replace("Remain read-only", "Edit any file", 1), encoding="utf-8")

    def drift_adapter_description(fixture: Path) -> None:
        agent = fixture / "adapters" / "cursor" / "agents" / "patpat-reviewer.md"
        text = agent.read_text(encoding="utf-8")
        agent.write_text(
            text.replace(REVIEWER_DESCRIPTION, "Use proactively for every task.", 1),
            encoding="utf-8",
        )

    def add_cursor_hooks(fixture: Path) -> None:
        manifest = fixture / ".cursor-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["hooks"] = "./missing-hooks.json"
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def add_conventional_command(fixture: Path) -> None:
        directory = fixture / "commands"
        directory.mkdir()
        (directory / "broad.md").write_text(
            "Edit every file and publish results.\n",
            encoding="utf-8",
        )

    def comment_out_proof_closure(fixture: Path) -> None:
        skill = fixture / "skills" / "patpat-change" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(
            text.replace(PROOF_CLOSURE_BLOCK, f"<!--\n{PROOF_CLOSURE_BLOCK}\n-->", 1),
            encoding="utf-8",
        )

    def remove_read_only_boundary(fixture: Path) -> None:
        skill = fixture / "skills" / "patpat-inspect" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(text.replace(READ_ONLY_BOUNDARY_BLOCK, "Edit broadly.", 1), encoding="utf-8")

    def add_nested_agent(fixture: Path) -> None:
        directory = fixture / "adapters" / "cursor" / "agents" / "nested"
        directory.mkdir()
        (directory / "broad-worker.md").write_text("---\nname: broad-worker\ndescription: Broad worker.\n---\nEdit everything.\n", encoding="utf-8")

    def remove_skill_policy_target(fixture: Path) -> None:
        source = fixture / "skills" / "patpat-impact"
        destination = fixture / "skills" / "patpat-impact-copy"
        shutil.copytree(source, destination)
        skill = destination / "SKILL.md"
        skill.write_text(skill.read_text(encoding="utf-8").replace("name: patpat-impact", "name: patpat-impact-copy", 1), encoding="utf-8")

    def add_codex_agents(fixture: Path) -> None:
        manifest = fixture / ".codex-plugin" / "plugin.json"
        data = json.loads(manifest.read_text(encoding="utf-8"))
        data["agents"] = "./agents/"
        manifest.write_text(json.dumps(data), encoding="utf-8")

    def break_proof_closure(fixture: Path) -> None:
        skill = fixture / "skills" / "patpat-change" / "SKILL.md"
        text = skill.read_text(encoding="utf-8")
        skill.write_text(
            text.replace(PROOF_CLOSURE_BLOCK, "Never use verification or review.", 1),
            encoding="utf-8",
        )

    cases.extend(
        [
            ("skill-name mismatch", break_name, "name must match folder patpat-inspect"),
            ("missing SKILL.md", remove_skill_file, "immediate skill directory is missing SKILL.md"),
            ("missing Codex smoke", remove_codex_smoke, "missing isolated Codex marketplace smoke test"),
            ("missing Antigravity smoke", remove_antigravity_smoke, "missing isolated Antigravity plugin smoke test"),
            ("missing stage script", remove_stage_script, "missing allowlisted plugin staging script"),
            ("missing agent install contract", remove_agents_guide, "missing agent install contract"),
            ("Codex defaultPrompt drift", drop_codex_default_prompt, "defaultPrompt must include $patpat-loop"),
            ("missing published source", drop_published_source, "homepage and repository must point at the published source"),
            ("manifest version drift", drift_version, "manifest versions must match"),
            ("invalid manifest versions", invalid_versions, "valid semantic versioning"),
            ("marketplace path escape", escape_marketplace_source, "root-contained"),
            ("marketplace policy drift", drift_marketplace_policy, "root-contained"),
            ("extra marketplace plugin", add_marketplace_plugin, "root-contained"),
            ("manifest description drift", drift_description, "manifest descriptions must match"),
            ("missing presentation field", remove_presentation_field, "shortDescription"),
            ("understated Codex capabilities", understate_codex_capabilities, "must disclose Interactive"),
            ("duplicate frontmatter", duplicate_key, "duplicate frontmatter key"),
            ("skill symlink", add_skill_symlink, "symlinks are not allowed"),
            ("router reachability", break_router_reachability, "not reachable from patpat-loop"),
            ("missing Cursor agents field", remove_cursor_agent_field, "Cursor manifest agents"),
            ("writable Cursor reviewer", weaken_cursor_reviewer, "readonly policy"),
            ("background Cursor agent", enable_background_agent, "must not run in background"),
            ("missing Antigravity agent adapter", remove_agent_adapter, "expected agent adapters"),
            ("Antigravity reviewer command access", grant_reviewer_command, "unexpected Antigravity skills or tools"),
            ("adapter body drift", drift_adapter_body, "canonical thin wrapper"),
            ("adapter description drift", drift_adapter_description, "description must remain canonical"),
            ("nested agent adapter", add_nested_agent, "expected agent adapters"),
            ("unsupported Codex agents", add_codex_agents, "must not claim packaged agents"),
            ("unsupported Cursor hooks", add_cursor_hooks, "unsupported manifest fields"),
            ("auto-discovered command", add_conventional_command, "unadmitted plugin component path"),
            ("commented proof closure", comment_out_proof_closure, "canonical proof closure directive"),
            ("read-only boundary drift", remove_read_only_boundary, "canonical read-only mutation boundary"),
            ("mutating proof closure", break_proof_closure, "missing proof closure"),
            ("unclassified skill", remove_skill_policy_target, "Skill policy registry mismatch"),
        ]
    )

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="patpat-validator-") as temp_directory:
        temp_root = Path(temp_directory)
        for index, (name, mutate, expected) in enumerate(cases):
            fixture = temp_root / f"fixture-{index}"
            shutil.copytree(root, fixture)
            mutate(fixture)
            fixture_errors = validate_root(fixture)
            if not any(expected in error for error in fixture_errors):
                failures.append(f"self-test: validator accepted deliberate {name}")
    run_script = root / "skills" / "patpat-run" / "scripts" / "run_state.py"
    result = subprocess.run(
        [sys.executable, str(run_script), "--self-test"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        failures.append(f"self-test: durable run engine failed: {result.stdout}{result.stderr}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    errors = validate_root(root)
    if not errors and args.self_test:
        errors.extend(run_self_test(root))

    if errors:
        print(f"Validation failed with {len(errors)} error(s):")
        for error in errors:
            print(f"- {error}")
        return 1

    suffix = " and self-test passed" if args.self_test else " passed"
    print(f"Patpat validation{suffix}: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
