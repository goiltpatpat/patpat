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

[`/patpat`](../patpat/SKILL.md) and `/patpat-loop` are one entry point (Codex: `$patpat` / `$patpat-loop`). The [operating protocol](references/operating-protocol.md) owns core judgment, safety, git, and evidence rules; playbooks and principles specialize without overriding it.

Explicit invocation persists across turns in the session (report `current-turn-only` after restart without a host receipt); opt out with `disable /patpat`. For non-engineering work, follow [general task judgment](references/general-task-judgment.md) without entering engineering routing unless a repo boundary is affected.

## Start

Classify from signals: reversibility, uncertainty, blast radius, auth, security, billing, secrets, architecture, cross-cutting scope, duration, delivery intent, and parallelism. First activation alone must not force a full protocol read.

| Shape | Signals | Execution |
| --- | --- | --- |
| 0, fast-track | Single clear, reversible, non-behavioral artifact; no contract, runtime, security, permission, migration, or delivery effect | Cheapest useful observation; read matched playbook/principles only; bounded edit + narrowest static check. Do not open a mandatory todo list or require a numbered checklist. |
| 1, bounded | Localized behavior/defect, understood callers, no high-risk boundary | Matched `change`/`debug` route, 5-field proof contract, targeted behavioral verification. |
| 2, design-gated | Ambiguity, architecture, schema, migration, public contract, auth/security/billing/secret, cross-cutting behavior, or multi-step dependency | Resolve design via `patpat-architect` first; fuller protocol and checkpoints before edit (`patpat-run` when durable/resumable). |

Shape 2 triggers (even on small fixes): adding/removing/swapping/major-bumping a direct runtime dependency, SDK, or external service (excluding lockfile refreshes); editing auth, permission, secret, billing, persisted schema, public contract, CI, release, or deploy definitions.

These are internal routing shapes, not user-selectable modes. File count is weak evidence after callers and contracts are inspected: one security-sensitive file is design-gated, while several prose-only files may stay fast-track. Any Tier 2 signal overrides lower-tier hints. Delivery or external effects use their specialist route and fuller authority gates; externality alone does not imply `patpat-architect`. Every mutating shape defines the 5-field proof contract before editing and verifies on the authoritative surface. See [operating protocol](references/operating-protocol.md) for full ask-vs-inspect rules.

## Principle index

Read when triggered; cite only when a principle changes a concrete choice (`[Principle Name] -> [Decision]`):

- [Repository truth](principles/repository-truth.md): inspect live evidence first.
- [Smallest safe change](principles/smallest-safe-change.md): delete, reuse, then patch.
- [Shape before logic](principles/shape-before-logic.md): make illegal states unrepresentable.
- [Boundary discipline](principles/boundary-discipline.md): validate edges; trust internal types.
- [Preserve safety](principles/preserve-safety.md): keep auth, billing, secret, and destructive gates intact.
- [Proof over proxy](principles/proof-over-proxy.md): verify on the real authoritative surface.
- [Explain the number](principles/explain-the-number.md): identify the limiter; reject proxy metrics.
- [Fix root causes](principles/fix-root-causes.md): reproduce root causes; test shared premise after two failures.
- [Sequence verifiable units](principles/sequence-verifiable-units.md): script rerunnable levers after the first proven unit.
- [Idempotent effects](principles/idempotent-effects.md): make retries and lifecycle steps safely rerunnable.
- [Encode lessons](principles/encode-lessons.md): enforce recurring fixes at the earliest mechanical boundary.
- [Earned parallelism](principles/earned-parallelism.md): single owner default; isolate worktrees before writable fan-out.
- [Subtract before you add](principles/subtract-before-you-add.md): simplify or delete before adding abstractions.
- [Experience first](principles/experience-first.md): optimize contracts, errors, and ergonomics for consumers.
- [Minimize reader load](principles/minimize-reader-load.md): keep flow linear, names domain-accurate, indirection minimal.
- [Guard the context window](principles/guard-the-context-window.md): compact evidence at the source.
- [Attack the premise](principles/attack-the-premise.md): challenge upstream assumptions when complexity cascades.
- [Redesign from first principles](principles/redesign-from-first-principles.md): rebuild essential invariants cleanly when blocked.

## Route the work

Resolve each specialist's `metadata.patpat.ontology` against current evidence before running (Shape 0/1 local work without delivery intent satisfies the start check without reading the full [operating protocol](references/operating-protocol.md#skill-state-and-mutation-gate)). Read `disable-model-invocation: true` specialist `SKILL.md` files directly to compose them. On Claude Code, read [Claude Code host map](references/host-claude-code.md) once per session.

Route to the earliest unresolved decision:

| Intent | Route | Primary Skill | Playbook |
| --- | --- | --- | --- |
| Read-only question, audit, or diagnosis-only defect | `inspect` | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Investigation](playbooks/investigation.md) |
| Defective behavior with fix requested | `debug` | [`patpat-debug`](../patpat-debug/SKILL.md) | [Defect](playbooks/defect.md) |
| Bounded feature or localized edit | `change` | [`patpat-change`](../patpat-change/SKILL.md) | [Bounded change](playbooks/bounded-change.md) |
| Contract, architecture, migration, security, or cross-cutting design | `architect` | [`patpat-architect`](../patpat-architect/SKILL.md) | [Architecture change](playbooks/architecture-change.md) |
| Proof of an existing claim or artifact | `verify` | [`patpat-verify`](../patpat-verify/SKILL.md) | Use workflow directly |
| Independent challenge of diff or proof | `review` | [`patpat-review`](../patpat-review/SKILL.md) | [Independent review](playbooks/independent-review.md) |
| Named commit, PR update, publish, or deploy | `ship` | [`patpat-ship`](../patpat-ship/SKILL.md) | [Authorized delivery](playbooks/authorized-delivery.md) |
| Durable multi-phase execution, PR stack, or overnight run | `run` | [`patpat-run`](../patpat-run/SKILL.md) | [Multi-phase run](playbooks/multi-phase-run.md) |

Use [route catalog](references/route-catalog.md) for specialized workflows (`arena`, `swarm`, `automation`, `eval`, `formal verification`, `perf`, `learn`, game-building, diagrams); default ambiguous multi-step work to `patpat-architect` or `patpat-run`.

## Run the graph

Read the matched playbook and [execution graph](references/execution-graph.md) (for fuller/durable work or return edges). For Shape 1/2, mirror applicable playbook steps in order in the host task list.

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY
  FRAME: (1) Objective & invariants, (2) Rawest ground truth, (3) Authoritative surface, (4) Falsifiable criteria (Shape 0/1: fold into Claim & Expect).
VERIFY -> REPORT (local, reversible, non-shipping edits)
VERIFY -> REVIEW (before default ship, land/merge, durable-run LEARN/REPORT, or auth/billing/secrets/architecture/cross-cutting)
REVIEW -> changes required -> INSPECT / PROOF CONTRACT / ACT -> VERIFY
REVIEW -> LEARN? (recurring failures only) -> propose & wait -> approved edit -> VERIFY -> REVIEW -> REPORT
REVIEW -> REPORT (no lesson) | LEARN pending -> hold | LEARN declined -> REPORT without editing
REPORT -> patpat-ship (delivery intent + fresh verify & review)
LAND? -> MERGE (passing reviewed PR + explicit land/merge)
```

Define the 5-field proof contract (`Claim`, `Surface`, `Action`, `Expect`, `Cleanup`) per [proof over proxy](principles/proof-over-proxy.md). Run the broader suite for design-gated or shared-contract work (classify failures via step 4 of [`patpat-verify`](../patpat-verify/SKILL.md#build-the-proof)). On failure, follow [bounded retry and Diagnostic Delta](references/execution-graph.md#bounded-retry-and-diagnostic-delta) (stop after 3 consecutive failures from the same blocker).

## Preserve control

- Proceed with ordinary in-scope edits under `/patpat`; [default delivery](playbooks/default-delivery.md) runs only with delivery intent (repo rules and `local only` win). Full continuation, pause, and delivery gates live in [operating protocol](references/operating-protocol.md).
- Pause before production deploy, package publish, force-push, data deletion, secret rotation, and risky auth/billing/permission changes. Merge requires explicit `land`/`merge` and a passing provider gate.
- A non-production deploy that Patpat starts, such as a preview, staging, or shared test link, runs only when the user names it, after fresh verify and independent review, and with a stated rollback; a non-production deploy a provider runs automatically from an authorized push follows that push's delivery gates.
- Workers stay local; only the parent ships.

## Earn parallelism

Default to one owner returning compact findings. Follow [phase-boundary hygiene](references/execution-graph.md#phase-boundary-hygiene) and [earned parallelism](principles/earned-parallelism.md): keep design in one unbroken window, give every writable slice a separate Git worktree or host sandbox, and use [`patpat-engineer`](../patpat-engineer/SKILL.md) for isolated slices. Every spawned subagent/worker kickoff MUST open on line 1 with `Read <abs-path>/skills/patpat-engineer/references/worker-contract.md before anything else.` (resolved absolute path).

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
