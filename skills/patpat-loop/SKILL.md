---
name: patpat-loop
description: Run the explicit Patpat evidence-driven work loop for the user's task. Use only when the user invokes /patpat, /patpat-loop, $patpat, or $patpat-loop, or directly asks to activate Patpat mode.
icon: shield
color: red
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Task","requires_state":["workspace-root-open"],"produces_state":["orchestrated-objective-resolved"],"verification_cmd":"git status --short"}'
---

# Patpat Loop

Before following this skill, apply the [skill state and mutation gate](references/operating-protocol.md#skill-state-and-mutation-gate).

[`/patpat`](../patpat/SKILL.md) and `/patpat-loop` are the same entry point (Codex: `$patpat` / `$patpat-loop`).

Patpat is one system: [operating protocol](references/operating-protocol.md) is the spine (judgment, safety, git, evidence); playbooks and principles specialize without overriding it.

Explicit invocation stays on across turns in the session (host hooks may persist across resume/compaction; without a host receipt, report `current-turn-only` after restart). Say `disable /patpat` to opt out; never infer activation from task similarity.

For non-engineering work, follow [general task judgment](references/general-task-judgment.md) with domain skills without entering engineering routing, Git delivery, or the durable graph unless an engineering or repo boundary is affected. Mixed work applies engineering gates to affected repo boundaries (repo media still needs media-specific verify plus repo gates).

## Start

Classify from signals: reversibility, uncertainty, blast radius, auth, security, billing, secrets, architecture, cross-cutting, duration, delivery intent, and parallelism. First activation alone must not force a full protocol read.

| Internal routing shape | Positive signals | Execution |
| --- | --- | --- |
| 0, fast-track | One clearly scoped, reversible, non-behavioral artifact; no contract, runtime, security, permission, migration, or delivery effect | Cheapest useful observation; read only matched playbook and principles; bounded edit + narrowest authoritative static check. Do not open a mandatory todo list or require a numbered checklist. |
| 1, bounded | Clear localized behavior or defect, small understood caller set, no high-risk boundary | Matched change or debug route, 5-field proof contract, targeted behavioral verification. |
| 2, design-gated | Ambiguity, architecture, schema, migration, public contract, auth/security/billing/secret, cross-cutting behavior, or unresolved multi-step dependency | Resolve design via `patpat-architect` first; fuller protocol and checkpoints before edit. Use `patpat-run` when durable, dependent, or resumable. |

Shape 2 triggers (even on small fixes): adding, removing, swapping, or major-bumping a direct runtime dependency, SDK, or external service/provider (excluding lockfile-only refreshes); changing auth, permission, secret, or billing paths; changing persisted schema or public contract; changing CI, release, or deploy definitions.

These are internal routing shapes, not user-selectable modes. File count is weak evidence after callers and contracts are inspected: one security-sensitive file is design-gated, while several prose-only files may stay fast-track. Any Tier 2 signal overrides lower-tier hints. Delivery or external effects use their specialist route and fuller authority gates; externality alone does not imply `patpat-architect`. Every mutating shape still defines the 5-field proof contract before editing and verifies on the authoritative surface.

Inspect, execute, or measure before asking; ask only for product preference, authority, destructive action, security, or human-only choices. Do not expose named user-selectable modes.

## Principle index

Read when triggered; cite only when a principle changed a concrete choice (`[Principle Name] -> [Decision]`):

- [Repository truth](principles/repository-truth.md): inspect live evidence over assumptions.
- [Smallest safe change](principles/smallest-safe-change.md): delete, reuse, then patch; comment only non-obvious constraints.
- [Shape before logic](principles/shape-before-logic.md): name legal states first; make illegal states unrepresentable.
- [Boundary discipline](principles/boundary-discipline.md): guard CLI, config, network, and auth edges; trust internal types.
- [Preserve safety](principles/preserve-safety.md): never weaken auth, permission, billing, secret, or destructive gates.
- [Proof over proxy](principles/proof-over-proxy.md): verify on the authoritative surface, including the real subject path.
- [Explain the number](principles/explain-the-number.md): name the metric limiter and rule out proxy artifacts.
- [Fix root causes](principles/fix-root-causes.md): reproduce/trace safely, never silence crashes with nil checks; after two failed fixes sharing one premise, write and test that premise first.
- [Sequence verifiable units](principles/sequence-verifiable-units.md): build a rerunnable tool after the first proven manual unit; no throwaway shims.
- [Idempotent effects](principles/idempotent-effects.md): make retries, installs, and lifecycle steps safe to re-run.
- [Encode lessons](principles/encode-lessons.md): encode only recurring failures, at the earliest enforceable boundary.
- [Earned parallelism](principles/earned-parallelism.md): default to one owner; require real isolation before writable fan-out.
- [Subtract before you add](principles/subtract-before-you-add.md): delete or simplify before adding files or abstractions.
- [Experience first](principles/experience-first.md): design contracts, errors, and CLI ergonomics for the consumer.
- [Minimize reader load](principles/minimize-reader-load.md): keep control flow linear, names domain-accurate, and indirection minimal.
- [Guard the context window](principles/guard-the-context-window.md): filter and compact evidence at the source; never dump raw logs.
- [Attack the premise](principles/attack-the-premise.md): question upstream assumptions when complexity cascades.
- [Redesign from first principles](principles/redesign-from-first-principles.md): rebuild essential invariants cleanly when constraints choke progress.

## Route the work

Before running a specialist, resolve its `metadata.patpat.ontology` against current evidence (required states, unique authorized producer, mutation/approval gates, post-condition verify). For Shape 0/1 local work without delivery intent, this summary and the Principle Index satisfy the start check without loading the full [operating protocol](references/operating-protocol.md#skill-state-and-mutation-gate). Metadata is routing evidence, not authority.

Compose specialists (`patpat-architect`, `patpat-change`, `patpat-engineer`, `patpat-verify`, `patpat-review`, `patpat-unslop`, `patpat-ship`) rather than inlining their logic; for `disable-model-invocation: true` skills, read their `SKILL.md` directly in an active session. On Claude Code, read [Claude Code host map](references/host-claude-code.md) once per session.

Select the route for the earliest unresolved decision found during inspection:

| Intent | Route | Primary Skill | Playbook Reference |
| --- | --- | --- | --- |
| Read-only question, audit, repo understanding, or diagnosis-only defect | `inspect` | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Investigation](playbooks/investigation.md) |
| Defective or unexplained behavior with implementation requested | `debug` | [`patpat-debug`](../patpat-debug/SKILL.md) | [Defect](playbooks/defect.md) |
| Bounded feature or localized modification | `change` | [`patpat-change`](../patpat-change/SKILL.md) | [Bounded change](playbooks/bounded-change.md) |
| Contract, architecture, migration, security-sensitive, or cross-cutting design | `architect` | [`patpat-architect`](../patpat-architect/SKILL.md) | [Architecture change](playbooks/architecture-change.md) |
| Proof of an existing claim or authoritative artifact | `verify` | [`patpat-verify`](../patpat-verify/SKILL.md) | Use the workflow directly |
| Independent challenge of an implementation, diff, or proof claim | `review` | [`patpat-review`](../patpat-review/SKILL.md) | [Independent review](playbooks/independent-review.md) |
| Named commit, PR update, publish, or authorized deploy | `ship` | [`patpat-ship`](../patpat-ship/SKILL.md) | [Authorized delivery](playbooks/authorized-delivery.md) |
| Durable multi-phase execution, PR queue/stack, or overnight run | `run` | [`patpat-run`](../patpat-run/SKILL.md) | [Multi-phase run](playbooks/multi-phase-run.md) |

Consult [route catalog](references/route-catalog.md) for specialized workflows (`arena`, `swarm`, `automation`, `eval`, `formal verification`, `perf`, `learn`, game-building, diagrams) or overlap; fallback to `patpat-architect` or `patpat-run`.

## Run the graph

Read the matched workflow/playbook (never recall an unread playbook) and [the execution graph](references/execution-graph.md) for fuller/durable work or return edges. Reuse unchanged instructions loaded this session, and re-classify each new task. For Shape 1 and Shape 2, copy the matched playbook's numbered steps into the host task list in order and count before task-specific items (shortening wording if capped, marking unrun steps `skip: <reason>`).

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY
  FRAME pre-flight: (1) Core Objective & invariants, (2) Rawest Ground Truth, (3) Authoritative Surface, (4) Falsifiable Acceptance Criteria (for Shape 0/1, fold into Claim & Expect of PROOF CONTRACT).
VERIFY -> REPORT (local, reversible, non-shipping edits)
VERIFY -> REVIEW (before default ship, land/merge, durable-run LEARN/REPORT, or auth/billing/secrets/architecture/cross-cutting)
REVIEW -> changes required -> INSPECT / PROOF CONTRACT / ACT -> VERIFY
REVIEW -> LEARN? (recurring failures only) -> propose & wait -> approved edit -> VERIFY -> REVIEW -> REPORT
REVIEW -> REPORT (no lesson) | LEARN pending -> hold | LEARN declined -> REPORT without editing
REPORT -> patpat-ship (only with delivery intent + fresh verify & review)
LAND? -> MERGE (passing reviewed PR only with explicit land/merge)
```

Define the 5-field proof contract (`Claim`, `Surface`, `Action`, `Expect`, `Cleanup`) using [proof over proxy](principles/proof-over-proxy.md). For design-gated, shared-contract, or non-trivial caller-set work, run the broader suite before claiming `verified` (if budget blocks it, name it and report `partially verified`; classify failures via step 4 of [`patpat-verify`](../patpat-verify/SKILL.md#build-the-proof)).

Classify failed evidence as `implementation defect`, `verifier defect`, or `environment blocker`, return to the earliest invalid state per [bounded retry and Diagnostic Delta contract](references/execution-graph.md#bounded-retry-and-diagnostic-delta), and stop after 3 consecutive failures from the same unresolved blocker (in durable runs, blocker key + failure class + graph node define the streak).

## Preserve control

- Ordinary in-scope edits proceed under `/patpat` without asking permission to type.
- Explicit `/patpat` or `$patpat` authorizes the loop, proof, and verify—not independent review or a PR. [Default delivery](playbooks/default-delivery.md) runs only with delivery intent; repo rules and `don't commit` / `local only` win.
- Continuation (`overnight`, `don't stop`, `going to bed`) runs through verify, review, and commit-and-PR, stopping merge-ready. Treat `ship it` as commit-and-PR; merge only on explicit `land`/`merge` with passing provider gate.
- Pause for production deploy, package publish, force-push, data deletion, secret rotation, and risky auth/billing/permission changes.
- A non-production deploy that Patpat starts, such as a preview, staging, or shared test link, runs only when the user names it, after fresh verify and independent review, and with a stated rollback; a non-production deploy a provider runs automatically from an authorized push follows that push's delivery gates.
- Workers never ship. The parent ships.

## Earn parallelism

Default to one owner; workers return compact findings, not transcripts. Arena, swarm, and autopilot require [earned parallelism](principles/earned-parallelism.md) (falling back to serial if isolation is missing): every writable slice needs a separate Git worktree or host sandbox with its own Git index and process boundary (disjoint files in one worktree are not isolation). Use [`patpat-engineer`](../patpat-engineer/SKILL.md) for isolated slices; the parent verifies the integrated result and runs default delivery when authorized.

## Report evidence

```text
Changed:
- <observable change and files>

Why:
- <evidence-backed reason with claim label: confirmed, inferred, or unknown>

Verified:
- <verified | partially verified | implemented but not verified | not implemented>: <command or observation>

Docs:
- <updated files or why none needed>

Risks:
- <remaining uncertainty, follow-up, or Low with scope>
```

Use `verified` only when the claimed behavior was observed on its authoritative surface.
