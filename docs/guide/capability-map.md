# Patpat Capability Map

This map tracks engineering behavior, not upstream file names or counts. It is informed by [pstack](https://github.com/cursor/plugins/tree/main/pstack) and its [Codex adaptation](https://github.com/Aqua-123/pstack-for-codex), then redesigned around Patpat's authority and verification contracts.

## Covered

- Higher-order routing with progressive disclosure
- Repository inspection, rationale forensics, runtime forensics, and trace forensics
- Architecture, explicit domain shape, blast radius, prototypes, bounded features, and behavior-preserving refactors
- Regression-first defects, measured performance work, sustained metric hillclimbing, and visual equivalence
- Direct verification, project-specific verifier maintenance, independent review, and structural learning
- Durable execution, cold-start takeover, safe pause and resume, bounded blockers, and content-bound receipts
- Delivery readiness with fresh action authority
- Fail-closed automation design with idempotency, compensation, bounded retries, and a kill switch
- Native or portable setup across supported agent hosts

## Deliberately gated

- Parallel writable agents require isolated ownership and repository-specific trust evidence.
- Arena, swarm, orchestration fleets, and autopilot remain disabled until one-agent reliability is proven on representative work.
- Runnable issue polling or Benny-like automation requires a named provider, credentials boundary, sandbox, authoritative proof surface, and successful canaries.
- Hooks and sticky cross-turn mode require host trust receipts and a lifecycle contract.
- Automatic merge, publish, deployment, scheduled tasks, and external messaging require explicit current authority.

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
| babysit / shipping / opening a PR | `patpat-ship` | adapted; Graphite merge-when-ready stays gated |
| `reflect` | `patpat-learn` | adapted |
| `eval` / skill authoring | `patpat-eval` / `patpat-skill` | covered |
| `setup-pstack` / Codex marketplace packaging | `patpat-setup` + host manifests + `AGENTS.md` + `goiltpatpat/patpat` | adapted; no model-role presets |
| `automate-me` / Benny | `patpat-automation` design only | gated until a named integration exists |
| `arena` / `swarm` / orchestrate / autopilot | earned-parallelism + `patpat-engineer` | gated |
| sticky mode / hooks | current-turn routing only | gated |
| `unslop` / `bro` / `no-comments` / `technical-writing` / `typescript-best-practices` / `recall` chat mining / `worktree-cleanup` | not a Patpat workflow | outside the core |
| `never-block-on-the-human` | rejected; Patpat requires fresh authority for external writes | adapted |
| redesign-from-first-principles / migrate-then-delete / build-the-lever | architecture-change, sequence-verifiable-units | adapted |
| type-system-discipline / comment encoding | shape-before-logic, smallest-safe-change | adapted |
| Codex `agents/openai.yaml` explicit-only policy | omitted; Codex implicit discovery from skill descriptions is accepted | adapted |

Packaging is already host-native: Codex marketplace + `.codex-plugin/plugin.json`, Cursor `.cursor-plugin/plugin.json`, Antigravity root `plugin.json`, and portable `scripts/install_skills.py`. Do not copy pstack-for-codex Node/Bun validators, TOML agent profiles, hooks, or Benny.

## Maintenance rule

Compare new upstream behavior by invariant. Classify it as covered, adapted, deliberately gated, or outside the core. Add a skill, playbook, principle, agent, or automation only when a concrete decision or failure mode cannot be expressed cleanly through an existing Patpat artifact.
