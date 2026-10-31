---
name: patpat-setup
description: Inspect the active agent host and install or validate Patpat through its supported native plugin manager or an explicit Agent Skills directory. Use for Patpat installation, discovery, update, removal, or host compatibility questions.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"DESTRUCTIVE","target_entity":"AgentHost","requires_state":["workspace-root-open"],"produces_state":["host-environment-configured"],"verification_cmd":"python3 scripts/validate.py"}'
---

# Patpat Setup

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Inspect the host, available CLI, source location, requested scope, and existing installation before changing anything. Keep compatibility questions read-only. Native install, update, and removal require current user authority for the exact host and user scope. Prefer the host-native plugin manager for Cursor, Codex, or Antigravity. Use `scripts/install_skills.py` from a canonical source checkout only when the user selects an explicit compatible skills directory.

Read the [agent install contract](https://github.com/goiltpatpat/patpat/blob/main/AGENTS.md) and [host installation guide](https://github.com/goiltpatpat/patpat/blob/main/docs/guide/installing.md). Select one route. Do not combine native and copied installations in the same host scope.

The published source is `https://github.com/goiltpatpat/patpat`. The Codex plugin id is `patpat@patpat`.

Preview copy-based portable installation with `--dry-run`. Refuse guessed home directories and silent user-level installation. Native plugin managers own their installed state. The portable installer currently supports new installs only and refuses overwrite; never use or describe it as an updater or uninstaller.

In a canonical source checkout, stage a working tree that contains Memory Bank or other ignored files with `scripts/stage_plugin.py` before native Codex or Antigravity install. A clean clone of the published repository may be installed directly. Never add or install a dirty checkout.

For hosts that implement Agent Plugins 1.0, create a separate portable package with `scripts/stage_agent_plugin.py` from the canonical source checkout. The generated package contains the portable root manifest, license, and a projection of the canonical skill tree; it does not include host adapters or lifecycle hooks. The projection removes Codex-only invocation metadata and adds an advisory explicit-request note for manual-only skills; Agent Skills 1.0 does not define a portable host-enforced invocation gate; treat the note as advisory and use the native adapter when invocation policy must be enforced. Its root `plugin.json` follows that standard and is not an Antigravity package; keep the source tree for Antigravity installs.

For Codex, require the repository [marketplace manifest](https://github.com/goiltpatpat/patpat/blob/main/.agents/plugins/marketplace.json) and [Codex plugin manifest](https://github.com/goiltpatpat/patpat/blob/main/.codex-plugin/plugin.json). Prefer `codex plugin marketplace add goiltpatpat/patpat` then `codex plugin add patpat@patpat`. For a dirty local tree, stage it with `scripts/stage_plugin.py` and add that distribution instead. Inspect `codex plugin list --json`, then start a new task before testing `$patpat-loop` discovery.

For Antigravity, validate the clean clone or staged path before installation, install only that explicit path, inspect the installed plugin list, and test skill invocation in a fresh session.

For Cursor, Patpat has a native adapter, but its marketplace listing and live invocation are unverified. Use the explicit project skills directory after proving the host reads it, then reload Cursor. Do not claim `/add-plugin patpat` or native invocation until Cursor reloads the plugin and invokes `patpat-loop` in a real project.

For another agent, first prove that it supports the Agent Skills folder contract. Ask for or discover its exact project-scoped skill directory. If no supported discovery contract exists, stop with installation instructions instead of copying files into a guessed location.

After install, invoke with the host form from the installation guide. Cursor uses `/patpat`. Codex uses `$patpat`. Portable hosts use `Use patpat to ...`.

Report the detected host, selected scope, exact destination or marketplace, pre-existing conflicts, command receipts, discovered skill count, invocation result, and removal path. Classify package validation separately from prompt-time discovery.

## Adaptive role routing (Smart Defaults + Easy Override)

Patpat adapts model reasoning power to task sensitivity using three capability tiers without rigid ceremonial constraints:

- **Strategic Architect & Lead (Deep Reasoning Tier)**:
  - Target capability: Platform flagship or frontier reasoning models (e.g., Claude Thinking/Sonnet, OpenAI o-series/o3, Gemini Pro/Thinking, or host flagship aliases).
  - Scope: Multi-phase planning, architectural refactoring, contract mutations, public API changes, statechart transitions, and high-risk invariants.
  - Posture: Deep causal tracing, zero-shot topology planning, and strict proof-contract formulation.
- **Fast Bounded Worker (Agile Execution Tier)**:
  - Target capability: Low-latency, high-throughput execution models (e.g., Claude Haiku, GPT mini, Gemini Flash, or host fast worker aliases).
  - Scope: Bounded bug fixes, local single-file refactors, test execution, AST symbol extraction, and syntax checks.
  - Posture: Tight iteration cycles, minimal token consumption, and targeted diffs.
- **Adversarial Reviewer (Independent Cross-Family Tier)**:
  - Target capability: Cross-model family pairing (e.g., pairing an Anthropic worker with an OpenAI reviewer, or a Google worker with an Anthropic reviewer).
  - Scope: Independent code reviews, blind adjudications, proof challenges, and pragmatic comment/anti-slop enforcement.
  - Posture: Read-only, skeptical, verifying real surface evidence over narrative claims.

## Universal host rules & configuration paths

Store host-specific operational rules and guidelines in each platform's canonical directory:

| Host Platform | Project-Scoped Rules | User / Global Rules | Supported Formats |
| :--- | :--- | :--- | :--- |
| **Cursor** | `.cursor/rules/` | `~/.cursor/rules/` | `.mdc`, `.md` |
| **Claude Code** | `CLAUDE.md`, `.claude/rules/` | `~/.claude/rules/` | `.md` |
| **OpenAI Codex** | `.codex/` | `~/.codex/` | `.md` |
| **Google Antigravity** | `.gemini/antigravity/skills/` | `~/.gemini/antigravity/builtin/skills/` | `.md`, `SKILL.md` |
| **Agent Plugins 1.0** | `.agents/skills/` | `~/.agents/skills/` | `SKILL.md` |

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
