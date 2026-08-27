#!/usr/bin/env python3
"""Behavioral eval for the patpat-inspect how-equivalent. No git writes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dry_run_loop  # noqa: E402


PLAYBOOK = ROOT / "skills" / "patpat-loop" / "playbooks" / "investigation.md"
SKILL = ROOT / "skills" / "patpat-inspect" / "SKILL.md"
CONTRACT = ROOT / "skills" / "patpat-inspect" / "references" / "how-report.md"
SOURCE = ROOT / "scripts" / "dry_run_loop.py"

SECTIONS = ("Overview", "Key Concepts", "How It Works", "Where Things Live", "Gotchas")
FORBIDDEN = (
    "fable",
    "setup-pstack",
    "make-bot-ui",
    "never-block-on-the-human",
    "never-block-on-human",
    "Graphite",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def how_routing_report() -> str:
    src = _text(SOURCE)
    route_line = next(
        i + 1 for i, line in enumerate(src.splitlines()) if line.startswith("def route(")
    )
    ship_line = next(
        i + 1 for i, line in enumerate(src.splitlines()) if line.startswith("def ship_plan(")
    )
    inspect_line = next(
        i + 1
        for i, line in enumerate(src.splitlines())
        if '"how does"' in line
    )
    return f"""### Overview
`route()` in `scripts/dry_run_loop.py` is the dry-run stand-in for `/patpat` routing. It maps a prompt to a playbook family and `ship_plan()` decides delivery. [confirmed]

### Key Concepts
- `route(prompt)` - playbook family selector (`scripts/dry_run_loop.py:{route_line}`). [confirmed]
- `ship_plan(...)` - commit/PR/merge/pause gate (`scripts/dry_run_loop.py:{ship_line}`). [confirmed]
- Inspect path - how/placement prompts return `inspect` and `no-ship`. [confirmed]

### How It Works
1. `route()` lowercases the prompt and matches earlier, more specific families before `debug` or `ship` (`scripts/dry_run_loop.py:{route_line}`). [confirmed]
2. How-does and placement phrases return `inspect` (`scripts/dry_run_loop.py:{inspect_line}`). [confirmed]
3. `ship_plan(path="read-only")` and `action="inspect"` return `no-ship`, so inspect never opens a PR. [confirmed]
4. A why-shaped neighbor still uses inspect, but via rationale-forensics and the why-report, not this how-report. [confirmed]

### Where Things Live
- `route` / `ship_plan` - owner `scripts/dry_run_loop.py`, layer test/router. [confirmed]
- How-equivalent instructions - owner `patpat-inspect` + investigation playbook, layer skill/playbook. [confirmed]
- Why-shaped questions - owner rationale-forensics under `patpat-inspect`, layer playbook (why-equivalent). [confirmed]

### Gotchas
- `fix`/`repro`/`timeout` still route to `debug`, not inspect.
- Inspect must not mutate or open a PR.
- Overnight merge is a ship/protocol concern, not this skill.
"""


def placement_report() -> str:
    return """### Overview
Investigation owns how/placement/ownership/layering/critique. Rationale-forensics owns why-shaped historical questions. [confirmed]

### Key Concepts
- Investigation playbook - how-equivalent (`skills/patpat-loop/playbooks/investigation.md`). [confirmed]
- Rationale-forensics playbook - why-shaped (`skills/patpat-loop/playbooks/rationale-forensics.md`). [confirmed]
- `patpat-inspect` - shared skill entry; it does not rewrite rationale-forensics. [confirmed]

### How It Works
`patpat-inspect` loads investigation for how/placement and rationale-forensics when the question is why-shaped. [confirmed]

### Where Things Live
- Investigation - owner `patpat-inspect`, layer playbook (how-equivalent). [confirmed]
- Rationale-forensics - owner `patpat-inspect`, layer playbook (why-equivalent). [confirmed]
- Router dry-run - owner `scripts/dry_run_loop.py`, layer test. [confirmed]

### Gotchas
No `/how` or `/why` slash skills. Placement prompts must stay read-only.
"""


def critique_report() -> str:
    return """### Overview
Explain first: `route()` is a dry-run selector, not the live `/patpat` host router. Then critique. [confirmed]

### Key Concepts
- `route()` - prompt classifier in `scripts/dry_run_loop.py`. [confirmed]
- Live routing - `skills/patpat-loop/SKILL.md` table. [confirmed]

### How It Works
`route()` approximates the playbook table so tests can lock inspect vs debug vs ship without running an agent. [confirmed]

### Where Things Live
- `route()` - owner test script, layer dry-run. [confirmed]
- Playbook table - owner `patpat-loop`, layer skill. [confirmed]

### Gotchas
Do not treat dry-run `route()` as the only production router.

### Critique
- Consider: keep `route()` as a test-layer approximation; do not promote it into a host slash skill.
- Noted: inspect vs debug keyword order is load-bearing.
- Dismissed: replacing `route()` with a model panel.
- Act on: none for this question; stay read-only.
"""


def run_self_test() -> None:
    playbook = _text(PLAYBOOK)
    skill = _text(SKILL)
    contract = _text(CONTRACT)
    for heading in SECTIONS:
        if f"## {heading}" not in contract and heading not in playbook:
            raise AssertionError(f"missing section {heading!r}")
        if heading not in playbook:
            raise AssertionError(f"playbook missing {heading!r}")
    if "Explain" not in playbook or "Critique" not in playbook:
        raise AssertionError("playbook missing Explain/Critique")
    if "Act on" not in playbook or "Dismissed" not in playbook:
        raise AssertionError("playbook missing critique verdicts")
    if "rationale-forensics" not in skill:
        raise AssertionError("inspect must keep why on rationale-forensics")
    blob = playbook + skill + contract
    for needle in FORBIDDEN:
        if needle.lower() in blob.lower():
            raise AssertionError(f"forbidden token {needle!r}")
    if re.search(r"(?m)^# /how\b", blob):
        raise AssertionError("introduced a /how skill")
    if (ROOT / "skills" / "how").exists():
        raise AssertionError("skills/how must not exist")

    assert dry_run_loop.route("How does auth reach this handler? Do not change files.") == "inspect"
    assert dry_run_loop.route("/patpat reproduce this timeout and fix the root cause") == "debug"
    assert dry_run_loop.route("which skill owns investigation vs rationale-forensics?") == "inspect"
    assert dry_run_loop.route("where should this live?") == "inspect"
    assert dry_run_loop.route("how does X work?") == "inspect"
    assert dry_run_loop.route("/patpat fix the timeout") == "debug"
    assert dry_run_loop.route("/patpat merge this") == "ship"
    assert dry_run_loop.route("why was ship_plan merge gated?") == "inspect"

    how = how_routing_report()
    place = placement_report()
    critique = critique_report()
    for heading in SECTIONS:
        marker = f"### {heading}"
        if marker not in how or marker not in place or marker not in critique:
            raise AssertionError(f"fixture missing {marker}")
    if "scripts/dry_run_loop.py" not in how:
        raise AssertionError("how fixture missing file citation")
    if "Act on" not in critique or "Dismissed" not in critique:
        raise AssertionError("critique fixture missing verdicts")
    print("Patpat inspect eval self-test passed.")
    print()
    print("== fixture: How does /patpat routing work? ==")
    print(how)
    print("== fixture: which skill owns investigation vs rationale-forensics? ==")
    print(place)
    print("== fixture: are we sure route() is the right layer? ==")
    print(critique)
    print("== eval triggers ==")
    print("- trigger how does X work? -> inspect")
    print("- trigger where should this live? -> inspect")
    print("- reject /patpat fix the timeout -> debug")
    print("- reject /patpat merge this -> ship")
    print("- neighbor why was ship_plan merge gated? -> inspect via rationale-forensics (D, not this how-report)")


def main() -> int:
    if "--self-test" in sys.argv or not sys.argv[1:]:
        run_self_test()
        return 0
    print("Usage: python3 scripts/eval_inspect.py --self-test")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
