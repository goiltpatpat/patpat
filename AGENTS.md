# Agent install contract

This file is the machine-readable install surface. Engineering workflows live in `skills/`. Do not invent a home directory, updater, uninstaller, or Cursor marketplace command.

Canonical skill tree: [`skills/`](skills/). Host adapters are thin manifests over that tree. Read [`docs/guide/installing.md`](docs/guide/installing.md) for host commands and [`skills/patpat-setup/SKILL.md`](skills/patpat-setup/SKILL.md) when that skill is already loadable.

## Detect, then choose one route

1. Identify the host, available CLI, requested scope, and source.
2. Select one route. Do not combine native plugin installation with copied skills in the same host scope.
3. Stage a working tree that contains Memory Bank or local artifacts before any native Codex or Antigravity install. The stager excludes local Memory Bank and `docs/diagrams/` but does not apply every `.gitignore` rule; inspect the staged package for other machine-local files inside allowed paths.
4. For hosts that support Agent Plugins 1.0, build a separate portable artifact with `python3 scripts/stage_agent_plugin.py --target /absolute/path/to/patpat-agent-plugin`. The artifact contains only the standard root manifest, license, and a portable projection of canonical `skills/`; Codex-only invocation metadata is removed, with an advisory explicit-request note for manual-only skills. Agent Skills 1.0 does not define a portable host-enforced invocation gate; treat that note as advisory and use the native adapter when invocation policy must be enforced. Keep the source root manifest and host adapters for native installs. Git-backed staging omits ignored local files inside skills; when staging without Git metadata, inspect the output before installing.

Published source: `https://github.com/goiltpatpat/patpat`. Plugin id: `patpat@patpat`.

| Host | Install |
| --- | --- |
| Grok CLI from GitHub | `grok plugin install goiltpatpat/patpat --trust` |
| Codex from GitHub | `codex plugin marketplace add goiltpatpat/patpat` then `codex plugin add patpat@patpat` |
| Codex from a dirty local tree | `python3 scripts/stage_plugin.py --target /absolute/path/to/patpat-dist` then marketplace-add that staged path |
| Antigravity from a clean clone | `agy plugin validate /absolute/path/to/patpat` then `agy plugin install /absolute/path/to/patpat` |
| Antigravity from a dirty local tree | stage first, then validate and install the staged path |
| Agent Plugins 1.0 hosts | `python3 scripts/stage_agent_plugin.py --target /absolute/path/to/patpat-agent-plugin`, validate the artifact, then use the host's documented plugin install path |
| Cursor | Cursor supports Agent Plugins and native Cursor plugins. Generate the portable artifact for a local test; Patpat's fresh-session invocation and marketplace listing remain unverified. Use a proven project skills directory if the plugin route is unavailable. |
| Other Agent Skills hosts | Prove the project skill directory, then `python3 scripts/install_skills.py --target /absolute/proven/skills-dir --dry-run` |

## After install

Start a fresh task or session. Package list output does not prove prompt-time discovery.

Explicit `/patpat`, `/patpat-loop`, `$patpat`, or `$patpat-loop` activation authorizes the Patpat loop, proof, and verify. Default commit-and-PR requires delivery intent; see the operating protocol and default-delivery playbook. Higher-priority repository rules and `local only` still win. Merge requires explicit `land` or `merge` language.

| Host | Invoke |
| --- | --- |
| Grok CLI | `/patpat` or `/patpat-loop` after a new session |
| Cursor | `/patpat` or `/patpat-loop` |
| Codex | `$patpat` or `$patpat-loop` |
| Portable / generic | `Use patpat to ...` |
| Antigravity | host UI or `Use patpat to ...` |

Report host, scope, exact destination or marketplace, conflicts, command receipts, discovered skill count, invocation result, and removal path. Classify package validation separately from prompt-time discovery.
