#!/usr/bin/env python3
"""Structural verify-ready checks. Not prompt discovery, hook execution, or live host proof."""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
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
CLI_NAMES = ("agy", "codex", "grok", "cursor")


def available_clis() -> list[str]:
    found: list[str] = []
    for name in CLI_NAMES:
        if shutil.which(name):
            found.append(name)
    return found


def detect_active_host() -> dict[str, Any]:
    """Host label from env or receipt files only. PATH CLIs are not an attested host."""
    if (
        os.environ.get("ANTIGRAVITY_APP_DIR")
        or os.environ.get("GEMINI_CLI")
        or Path.home().joinpath(".gemini/antigravity-cli").exists()
    ):
        return {"host": "antigravity", "attested": True}
    if os.environ.get("CODEX_ENV"):
        return {"host": "codex", "attested": True}
    if os.environ.get("GROK_ENV"):
        return {"host": "grok", "attested": True}
    if os.environ.get("CURSOR_VERSION") or os.environ.get("CURSOR_PROJECT_DIR"):
        return {"host": "cursor", "attested": True}
    return {"host": None, "attested": False}


def bind_target(root: Path, target: Path | None) -> tuple[Path, Path] | str:
    """Return (skills_dir, hook_root), or an error when --target cannot be used."""
    if target is None:
        return root / "skills", root
    if not target.is_dir():
        return "target does not exist"
    return target, target


def check_patpat_discovery(skills_dir: Path) -> dict[str, Any]:
    """Check whether structural /patpat files exist. Does not prove prompt discovery."""
    patpat_skill = skills_dir / "patpat" / "SKILL.md"
    patpat_loop = skills_dir / "patpat-loop" / "SKILL.md"
    if patpat_skill.is_file() and patpat_loop.is_file():
        content = patpat_skill.read_text(encoding="utf-8")
        if "patpat-loop" in content:
            return {
                "present": True,
                "entrypoint": str(patpat_skill),
                "router": "patpat-loop",
            }
    return {
        "present": False,
        "entrypoint": None,
        "router": None,
    }


def check_hook_status(hook_root: Path) -> dict[str, Any]:
    """Inspect hook files. Does not prove hook execution."""
    hooks_config = hook_root / "hooks" / "hooks.json"
    hook_script = hook_root / "hooks" / "scripts" / "patpat_loop_state.py"
    has_config = hooks_config.is_file()
    has_script = hook_script.is_file()
    status = "configured" if has_config and has_script else "none"
    return {
        "status": status,
        "config_present": has_config,
        "script_present": has_script,
    }


def check_core_routes(skills_dir: Path) -> dict[str, Any]:
    """Verify presence of the 8 core routes without requiring all 22 skills."""
    present: list[str] = []
    missing: list[str] = []
    for route, skill_name in CORE_SKILLS.items():
        skill_file = skills_dir / skill_name / "SKILL.md"
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
    """Run structural verification and print a receipt."""
    host_info = detect_active_host()
    clis = available_clis()
    bound = bind_target(root, target)
    payload: dict[str, Any] = {
        "ready": False,
        "readiness_kind": "structural",
        "active_host": host_info["host"],
        "available_clis": clis,
        "patpat_present": False,
        "patpat_entrypoint": None,
        "hook_status": "none",
        "core_routes": {"present": "0/8", "routes": [], "missing": list(CORE_ROUTES)},
        "claims": {
            "prompt_discovery": "not_attested",
            "hook_execution": "not_attested",
            "active_host": "env-receipt" if host_info["attested"] else "not_attested",
        },
    }
    if isinstance(bound, str):
        payload["error"] = bound
        return emit(payload, as_json, ready=False)

    skills_dir, hook_root = bound
    discovery = check_patpat_discovery(skills_dir)
    hooks = check_hook_status(hook_root)
    routes = check_core_routes(skills_dir)
    is_ready = discovery["present"] and routes["all_present"]
    payload.update(
        {
            "ready": is_ready,
            "patpat_present": discovery["present"],
            "patpat_entrypoint": discovery["entrypoint"],
            "hook_status": hooks["status"],
            "core_routes": {
                "present": f"{routes['present_count']}/{routes['total']}",
                "routes": routes["present"],
                "missing": routes["missing"],
            },
        }
    )
    if target is not None and not discovery["present"]:
        payload["error"] = "target has no /patpat"
        payload["ready"] = False
        is_ready = False
    return emit(payload, as_json, ready=is_ready)


def emit(payload: dict[str, Any], as_json: bool, *, ready: bool) -> int:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        host = payload["active_host"] or "unattested"
        clis = ",".join(payload["available_clis"]) if payload["available_clis"] else "none"
        print(f"Readiness: structural")
        print(f"Active host: {host} ({payload['claims']['active_host']})")
        print(f"Available CLIs: {clis}")
        print(f"/patpat files present: {'yes' if payload['patpat_present'] else 'no'}")
        print(f"Hook files: {payload['hook_status']}")
        print(
            f"Core routes: {payload['core_routes']['present']} present ({', '.join(payload['core_routes']['routes'])})"
        )
        if payload["core_routes"]["missing"]:
            print(f"Missing core routes: {', '.join(payload['core_routes']['missing'])}")
        if payload.get("error"):
            print(f"Error: {payload['error']}")
        print(f"Ready: {'yes' if ready else 'no'}")
    return 0 if ready else 1


def capture_verify(root: Path, target: Path | None) -> tuple[int, dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = verify_ready(root, target=target, as_json=True)
    return code, json.loads(buf.getvalue())


def run_self_test(root: Path) -> int:
    """Self-test for structural verify-ready checks."""
    host = detect_active_host()
    if "host" not in host:
        raise AssertionError("active host detection missing host key")
    if shutil.which("agy") and not (
        os.environ.get("ANTIGRAVITY_APP_DIR")
        or os.environ.get("GEMINI_CLI")
        or Path.home().joinpath(".gemini/antigravity-cli").exists()
    ):
        if host["host"] == "antigravity":
            raise AssertionError("agy on PATH must not label active_host antigravity")

    skills_dir = root / "skills"
    discovery = check_patpat_discovery(skills_dir)
    if not discovery["present"]:
        raise AssertionError("/patpat files were not present in source repo")

    hooks = check_hook_status(root)
    if hooks["status"] not in {"configured", "none"}:
        raise AssertionError(f"unexpected hook status: {hooks['status']}")

    routes = check_core_routes(skills_dir)
    if not routes["all_present"]:
        raise AssertionError(f"core routes missing in source repo: {routes['missing']}")
    if routes["present_count"] != 8:
        raise AssertionError(f"expected exactly 8 core routes, got {routes['present_count']}")

    missing_code, missing_payload = capture_verify(root, Path("/no/such/path"))
    if missing_code == 0 or missing_payload.get("ready") is True:
        raise AssertionError("nonexistent --target must fail closed")
    source_entrypoint = str(skills_dir / "patpat" / "SKILL.md")
    if missing_payload.get("patpat_entrypoint") == source_entrypoint:
        raise AssertionError("nonexistent --target must not fall back to the source repo")

    with tempfile.TemporaryDirectory(prefix="patpat-verify-ready-") as temp_dir:
        temp_path = Path(temp_dir)
        temp_skills = temp_path / "skills"
        temp_skills.mkdir()

        for skill_name in list(CORE_SKILLS.values()) + ["patpat", "patpat-loop"]:
            src = root / "skills" / skill_name
            if src.is_dir():
                shutil.copytree(src, temp_skills / skill_name)

        trimmed_routes = check_core_routes(temp_skills)
        if not trimmed_routes["all_present"]:
            raise AssertionError("core routes check failed on trimmed 8-route set")
        trimmed_discovery = check_patpat_discovery(temp_skills)
        if not trimmed_discovery["present"]:
            raise AssertionError("discovery failed on trimmed set")

        shutil.rmtree(temp_skills / "patpat-ship")
        broken_routes = check_core_routes(temp_skills)
        if broken_routes["all_present"]:
            raise AssertionError("broken core routes check erroneously passed")
        if "ship" not in broken_routes["missing"]:
            raise AssertionError("ship route missing was not detected")

        wrong = temp_path / "empty-target"
        wrong.mkdir()
        wrong_code, wrong_payload = capture_verify(root, wrong)
        if wrong_code == 0 or wrong_payload.get("ready") is True:
            raise AssertionError("wrong --target must fail closed")
        if wrong_payload.get("patpat_entrypoint") == source_entrypoint:
            raise AssertionError("wrong --target must not fall back to the source repo")

    print("Patpat verify-ready self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Structural verify-ready checks for /patpat files and core routes."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--target", type=Path, help="Inspect this skills directory only. Fail closed if missing or it has no /patpat.")
    parser.add_argument("--json", action="store_true", help="Output JSON receipt.")
    parser.add_argument("--verify-ready", action="store_true", help="Alias flag for compatibility.")
    parser.add_argument("--self-test", action="store_true", help="Run self-test.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test(args.root.resolve())

    return verify_ready(args.root.resolve(), target=args.target, as_json=args.json)


if __name__ == "__main__":
    raise SystemExit(main())
