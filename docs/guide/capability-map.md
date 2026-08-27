# Patpat Capability Map

This map tracks engineering behavior, not upstream file names or counts. Patpat's core is its operating protocol. Workflow jobs are informed by [pstack](https://github.com/cursor/plugins/tree/main/pstack) and its [Codex adaptation](https://github.com/Aqua-123/pstack-for-codex), then bounded so they cannot override that protocol.

## Covered

- Higher-order routing with progressive disclosure
- Repository inspection, rationale forensics, runtime forensics, and trace forensics
- Architecture, explicit domain shape, blast radius, prototypes, bounded features, and behavior-preserving refactors
- Regression-first defects, measured performance work, sustained metric hillclimbing, and visual equivalence
- Direct verification, project-specific verifier maintenance, independent review, and structural learning
- Durable execution, cold-start takeover, safe pause and resume, bounded blockers, and content-bound receipts
- Default commit-and-PR after proof; merge of a green verified PR on land or overnight
- Fail-closed automation design with idempotency, compensation, bounded retries, and a kill switch
- Native or portable setup across supported agent hosts

## Deliberately gated

- Writable fan-out requires earned-parallelism gates; otherwise work is serial.
- Issue-loop remains paused until a named provider, sandbox, canary, and enable request exist. No host scheduler ships enabled.
- Package publish, production deploy, force-push, and secret rotation still pause. Real CI failures do not land.

## Outside the core

Generic technical writing, language-specific style catalogs, persona skills, chat-history mining, simulator cleanup, and model-selection presets remain project or host extensions. Add them only when repeated evidence shows that a Patpat-owned constraint improves engineering outcomes.

## Upstream invariant mapping

Compare pstack jobs to Patpat artifacts. Missing filenames are not gaps when the invariant already lives in a router, skill, playbook, or principle.

| pstack job | Patpat home | Class |
| --- | --- | --- |
| `poteto-mode` routing + playbooks | `patpat-loop` + playbooks | adapted |
| `how` / `why` / `teach` investigation | `patpat-inspect` + investigation / rationale-forensics | adapted |
| `blast-radius` | `patpat-impact` | covered |
| `architect` | `patpat-architect` | adapted |
| feature / refactor / prototype | `patpat-change` + bounded-change / behavior-preserving-refactor / prototype | covered |
| bug fix / TDD | `patpat-debug` + defect / regression-first | adapted |
| perf / hillclimb / runtime / trace / visual parity | `patpat-perf` + `patpat-verify` + matching playbooks | covered |
| `interrogate` | `patpat-review` | adapted |
| `create-verification-skill` / `maintain-verification-skill` | `patpat-verifier` | covered |
| `figure-it-out` | `patpat-plan` + bespoke-workflow | adapted |
| `show-me-your-work` / autonomous run / pause / pickup | `patpat-run` + multi-phase-run / session-takeover | adapted |
| babysit / shipping / opening a PR | PR drive + authorized-delivery | adapted; land only when named |
| `reflect` | `patpat-learn` | adapted |
| `eval` / skill authoring | `patpat-eval` / `patpat-skill` | covered |
| `setup-pstack` / Codex marketplace packaging | `patpat-setup` + host manifests + `AGENTS.md` + `goiltpatpat/patpat` | adapted; no model-role presets |
| `automate-me` / Benny | issue-loop under `patpat-automation`; paused, provider-named, no Slack pack | adapted |
| `arena` / `swarm` | `patpat-arena` / `patpat-swarm`; serial fallback without isolation | adapted |
| orchestrate / autopilot | autopilot playbook under `patpat-run`; land only when named | adapted |
| sticky mode / hooks | `/patpat` mode + trusted `hooks/` receipts; fail closed without PLUGIN_DATA | adapted |
| pstack opening-a-pr / shipping / overnight land | default-delivery then authorized-delivery; merge green only | adapted |
| `unslop` / `bro` / `no-comments` / `technical-writing` / `typescript-best-practices` / `recall` chat mining / `worktree-cleanup` | not a Patpat workflow | outside the core |
| `never-block-on-the-human` | default commit-and-PR after proof; still pause for deploy, force-push, secrets | adapted |
| redesign-from-first-principles / migrate-then-delete / build-the-lever | architecture-change, sequence-verifiable-units | adapted |
| type-system-discipline / comment encoding | shape-before-logic, smallest-safe-change | adapted |
| Codex `agents/openai.yaml` explicit-only policy | omitted; Codex implicit discovery from skill descriptions is accepted | adapted |

Packaging is already host-native: Codex marketplace + `.codex-plugin/plugin.json`, Cursor `.cursor-plugin/plugin.json`, Antigravity root `plugin.json`, portable `scripts/install_skills.py`, and allowlisted sticky hooks. Do not copy pstack-for-codex Node/Bun validators, TOML agent profiles, or Benny.

## Maintenance rule

Compare new upstream behavior by invariant. Classify it as covered, adapted, deliberately gated, or outside the core. Add a skill, playbook, principle, agent, or automation only when a concrete decision or failure mode cannot be expressed cleanly through an existing Patpat artifact.
