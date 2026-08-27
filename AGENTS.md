# Agent install contract

This file is the machine-readable install surface. Engineering workflows live in `skills/`. Do not invent a home directory, updater, uninstaller, or Cursor marketplace command.

Canonical skill tree: [`skills/`](skills/). Host adapters are thin manifests over that tree. Read [`docs/guide/installing.md`](docs/guide/installing.md) for host commands and [`skills/patpat-setup/SKILL.md`](skills/patpat-setup/SKILL.md) when that skill is already loadable.

## Detect, then choose one route

1. Identify the host, available CLI, requested scope, and source.
2. Select one route. Do not combine native plugin installation with copied skills in the same host scope.
3. Stage a working tree that contains Memory Bank or other ignored files before any native Codex or Antigravity install.

Published source: `https://github.com/goiltpatpat/patpat`. Plugin id: `patpat@patpat`.

| Host | Install |
| --- | --- |
| Codex from GitHub | `codex plugin marketplace add goiltpatpat/patpat` then `codex plugin add patpat@patpat` |
| Codex from a dirty local tree | `python3 scripts/stage_plugin.py --target /absolute/path/to/patpat-dist` then marketplace-add that staged path |
| Antigravity from a clean clone | `agy plugin validate /absolute/path/to/patpat` then `agy plugin install /absolute/path/to/patpat` |
| Antigravity from a dirty local tree | stage first, then validate and install the staged path |
| Cursor | Native load is experimental. Use the portable route until a live project load is proven. |
| Other Agent Skills hosts | Prove the project skill directory, then `python3 scripts/install_skills.py --target /absolute/proven/skills-dir --dry-run` |

## After install

Start a fresh task or session. Package list output does not prove prompt-time discovery.

| Host | Invoke |
| --- | --- |
| Codex | `$patpat-loop` |
| Portable / generic | `Use patpat-loop to ...` |
| Antigravity | host UI or `Use patpat-loop to ...` |
| Cursor | host UI or `Use patpat-loop to ...` after reload; `/skill` is unverified |

Report host, scope, exact destination or marketplace, conflicts, command receipts, discovered skill count, invocation result, and removal path. Classify package validation separately from prompt-time discovery.
