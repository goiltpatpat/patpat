---
name: patpat-setup
description: Inspect the active agent host and install or validate Patpat through its supported native plugin manager or an explicit Agent Skills directory. Use for Patpat installation, discovery, update, removal, or host compatibility questions.
disable-model-invocation: true
---

# Patpat Setup

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Inspect the host, available CLI, source location, requested scope, and existing installation before changing anything. Keep compatibility questions read-only. Native install, update, and removal require current user authority for the exact host and user scope. Prefer the host-native plugin manager for Cursor, Codex, or Antigravity. Use `scripts/install_skills.py` from a canonical source checkout only when the user selects an explicit compatible skills directory.

Read the [agent install contract](https://github.com/goiltpatpat/patpat/blob/main/AGENTS.md) and [host installation guide](https://github.com/goiltpatpat/patpat/blob/main/docs/guide/installing.md). Select one route. Do not combine native and copied installations in the same host scope.

The published source is `https://github.com/goiltpatpat/patpat`. The Codex plugin id is `patpat@patpat`.

Preview copy-based portable installation with `--dry-run`. Refuse guessed home directories and silent user-level installation. Native plugin managers own their installed state. The portable installer currently supports new installs only and refuses overwrite; never use or describe it as an updater or uninstaller.

In a canonical source checkout, stage a working tree that contains Memory Bank or other ignored files with `scripts/stage_plugin.py` before native Codex or Antigravity install. A clean clone of the published repository may be installed directly. Never add or install a dirty checkout.

For hosts that implement Agent Plugins 1.0, create a separate portable package with `scripts/stage_agent_plugin.py` from the canonical source checkout. The generated package contains the portable root manifest, license, and skill tree; it does not include host adapters or lifecycle hooks. Its root `plugin.json` follows that standard and is not an Antigravity package; keep the source tree for Antigravity installs.

For Codex, require the repository [marketplace manifest](https://github.com/goiltpatpat/patpat/blob/main/.agents/plugins/marketplace.json) and [Codex plugin manifest](https://github.com/goiltpatpat/patpat/blob/main/.codex-plugin/plugin.json). Prefer `codex plugin marketplace add goiltpatpat/patpat` then `codex plugin add patpat@patpat`. For a dirty local tree, stage it with `scripts/stage_plugin.py` and add that distribution instead. Inspect `codex plugin list --json`, then start a new task before testing `$patpat-loop` discovery.

For Antigravity, validate the clean clone or staged path before installation, install only that explicit path, inspect the installed plugin list, and test skill invocation in a fresh session.

For Cursor, Patpat has a native adapter, but its marketplace listing and live invocation are unverified. Use the explicit project skills directory after proving the host reads it, then reload Cursor. Do not claim `/add-plugin patpat` or native invocation until Cursor reloads the plugin and invokes `patpat-loop` in a real project.

For another agent, first prove that it supports the Agent Skills folder contract. Ask for or discover its exact project-scoped skill directory. If no supported discovery contract exists, stop with installation instructions instead of copying files into a guessed location.

After install, invoke with the host form from the installation guide. Cursor uses `/patpat`. Codex uses `$patpat`. Portable hosts use `Use patpat to ...`.

Report the detected host, selected scope, exact destination or marketplace, pre-existing conflicts, command receipts, discovered skill count, invocation result, and removal path. Classify package validation separately from prompt-time discovery.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
