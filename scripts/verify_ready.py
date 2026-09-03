#!/usr/bin/env python3
"""Verify host readiness, /patpat discovery, hook status, and core route presence."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

CORE_ROUTES = (
    "inspect",
    "debug",
    "change",
    "architect",
    "verify",
    "review",
    "ship",
    "run",
)

CORE_SKILLS: dict[str, str] = {
    "inspect": "patpat-inspect",
    "debug": "patpat-debug",
    "change": "patpat-change",
    "architect": "patpat-architect",
    "verify": "patpat-verify",
    "review": "patpat-review",
    "ship": "patpat-ship",
    "run": "patpat-run",
}


def detect_host() -> dict[str, Any]:
    """Detect active agent host and available CLI."""
    if (
        os.environ.get("ANTIGRAVITY_APP_DIR")
        or os.environ.get("GEMINI_CLI")
        or Path.home().joinpath(".gemini/antigravity-cli").exists()
        or shutil.which("agy")
    ):
        return {"host": "antigravity", "cli": shutil.which("agy"), "details": "Antigravity host"}
    if os.environ.get("CODEX_ENV") or shutil.which("codex"):
        return {"host": "codex", "cli": shutil.which("codex"), "details": "Codex host"}
    if os.environ.get("GROK_ENV") or shutil.which("grok"):
        return {"host": "grok", "cli": shutil.which("grok"), "details": "Grok CLI host"}
    if (
        os.environ.get("CURSOR_VERSION")
        or os.environ.get("CURSOR_PROJECT_DIR")
        or Path(".cursor").is_dir()
    ):
        return {"host": "cursor", "cli": shutil.which("cursor"), "details": "Cursor host"}
    return {"host": "portable", "cli": None, "details": "Generic Agent Skills host"}


def check_patpat_discovery(root: Path, target: Path | None = None) -> dict[str, Any]:
    """Check whether /patpat is discoverable and points to patpat-loop."""
    search_dirs: list[Path] = []
    if target and target.is_dir():
        search_dirs.append(target)
    search_dirs.append(root / "skills")

    for base in search_dirs:
        patpat_skill = base / "patpat" / "SKILL.md"
        patpat_loop = base / "patpat-loop" / "SKILL.md"
        if patpat_skill.is_file() and patpat_loop.is_file():
            content = patpat_skill.read_text(encoding="utf-8")
            if "patpat-loop" in content:
                return {
                    "discovered": True,
                    "entrypoint": str(patpat_skill),
                    "target": "patpat-loop",
                }
    return {
        "discovered": False,
        "entrypoint": None,
        "target": None,
    }


def check_hook_status(root: Path) -> dict[str, Any]:
    """Inspect hook configuration, script, and runtime status."""
    hooks_config = root / "hooks" / "hooks.json"
    hook_script = root / "hooks" / "scripts" / "patpat_loop_state.py"

    has_config = hooks_config.is_file()
    has_script = hook_script.is_file()

    is_active = bool(
        os.environ.get("PLUGIN_DATA")
        or os.environ.get("GROK_PLUGIN_DATA")
        or os.environ.get("CLAUDE_PLUGIN_DATA")
    )

    if is_active and has_script:
        status = "active"
    elif has_config and has_script:
        status = "configured"
    else:
        status = "none"

    return {
        "status": status,
        "config_present": has_config,
        "script_present": has_script,
        "session_active": is_active,
    }


def check_core_routes(root: Path, target: Path | None = None) -> dict[str, Any]:
    """Verify presence of the 8 core routes without requiring all 22 skills."""
    search_dir = target if (target and target.is_dir()) else (root / "skills")
    present: list[str] = []
    missing: list[str] = []
    for route, skill_name in CORE_SKILLS.items():
        skill_file = search_dir / skill_name / "SKILL.md"
        if skill_file.is_file():
            present.append(route)
        else:
            missing.append(route)
    return {
        "total": len(CORE_ROUTES),
        "present_count": len(present),
        "present": present,
        "missing": missing,
        "all_present": len(missing) == 0,
    }


def verify_ready(root: Path, target: Path | None = None, as_json: bool = False) -> int:
    """Run verification and print receipt."""
    host_info = detect_host()
    discovery = check_patpat_discovery(root, target)
    hooks = check_hook_status(root)
    routes = check_core_routes(root, target)

    is_ready = discovery["discovered"] and routes["all_present"]

    payload = {
        "ready": is_ready,
        "host": host_info["host"],
        "host_cli": host_info["cli"],
        "patpat_discovered": discovery["discovered"],
        "patpat_entrypoint": discovery["entrypoint"],
        "hook_status": hooks["status"],
        "core_routes": {
            "present": f"{routes['present_count']}/{routes['total']}",
            "routes": routes["present"],
            "missing": routes["missing"],
        },
    }

    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        cli_info = f" ({payload['host_cli']})" if payload["host_cli"] else ""
        print(f"Host: {payload['host']}{cli_info}")
        print(f"/patpat discovered: {'yes' if payload['patpat_discovered'] else 'no'}")
        print(f"Hook status: {payload['hook_status']}")
        print(
            f"Core routes: {payload['core_routes']['present']} present ({', '.join(payload['core_routes']['routes'])})"
        )
        if payload["core_routes"]["missing"]:
            print(f"Missing core routes: {', '.join(payload['core_routes']['missing'])}")
        print(f"Ready: {'yes' if payload['ready'] else 'no'}")

    return 0 if is_ready else 1


def run_self_test(root: Path) -> int:
    """Self-test for verify-ready checks."""
    host = detect_host()
    if not host.get("host"):
        raise AssertionError("host detection returned empty host")

    discovery = check_patpat_discovery(root)
    if not discovery["discovered"]:
        raise AssertionError("/patpat was not discovered in source repo")

    hooks = check_hook_status(root)
    if hooks["status"] not in {"active", "configured", "none"}:
        raise AssertionError(f"unexpected hook status: {hooks['status']}")

    routes = check_core_routes(root)
    if not routes["all_present"]:
        raise AssertionError(f"core routes missing in source repo: {routes['missing']}")
    if routes["present_count"] != 8:
        raise AssertionError(f"expected exactly 8 core routes, got {routes['present_count']}")

    with tempfile.TemporaryDirectory(prefix="patpat-verify-ready-") as temp_dir:
        temp_path = Path(temp_dir)
        temp_skills = temp_path / "skills"
        temp_skills.mkdir()

        # Copy only the 8 core skills + patpat + patpat-loop (10 skills, NOT 22)
        for skill_name in list(CORE_SKILLS.values()) + ["patpat", "patpat-loop"]:
            src = root / "skills" / skill_name
            if src.is_dir():
                shutil.copytree(src, temp_skills / skill_name)

        # Confirm 10 skills passes verify-ready (proves 22-skill count is NOT required)
        trimmed_routes = check_core_routes(temp_path)
        if not trimmed_routes["all_present"]:
            raise AssertionError("core routes check failed on trimmed 8-route set")
        trimmed_discovery = check_patpat_discovery(temp_path)
        if not trimmed_discovery["discovered"]:
            raise AssertionError("discovery failed on trimmed set")

        # Test failure case: remove a core route
        shutil.rmtree(temp_skills / "patpat-ship")
        broken_routes = check_core_routes(temp_path)
        if broken_routes["all_present"]:
            raise AssertionError("broken core routes check erroneously passed")
        if "ship" not in broken_routes["missing"]:
            raise AssertionError("ship route missing was not detected")

    print("Patpat verify-ready self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify host readiness, /patpat discovery, hook status, and core route presence."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target", type=Path, help="Target skills directory if checking installed state.")
    parser.add_argument("--json", action="store_true", help="Output JSON receipt.")
    parser.add_argument("--verify-ready", action="store_true", help="Alias flag for compatibility.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test(args.root)

    return verify_ready(args.root, target=args.target, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
