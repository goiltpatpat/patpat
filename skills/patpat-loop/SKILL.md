---
name: patpat-loop
description: Run the explicit Patpat evidence-driven engineering loop. Use only when the user invokes /patpat, /patpat-loop, $patpat, or $patpat-loop, or directly asks to activate Patpat mode.
---

# Patpat Loop

`/patpat` and `/patpat-loop` are the same entry point. Codex uses `$patpat` or `$patpat-loop`.

Patpat is one system. The [operating protocol](references/operating-protocol.md) is the spine: judgment, safety, git, and evidence. The playbooks and principles are the machinery, informed by pstack jobs, renamed and bounded so they cannot override that spine.

This mode stays on across later turns after explicit invocation. Trusted host hooks may persist it across resume and compaction. Without a host-observed receipt, apply it only for the current session and report `current-turn-only` after a restart. Say `disable /patpat` to opt out. Do not infer activation from a task that merely resembles a playbook.

## Start

Open a todo list. The first items are:

1. Read the [operating protocol](references/operating-protocol.md) in full.
2. Read the principle index below.
3. Match a playbook, open it, and track a compact checklist keyed to its numbered steps before any task-specific work. A skipped step stays listed with `skip: <reason>`.

Do not apply Patpat outside software engineering or repository operations.

## Principle index

Read the linked file when the trigger fires. Cite a principle only when it changed a decision.

- [Repository truth](principles/repository-truth.md) before deciding. Inspect live evidence. Do not prefer assumptions.
- [Smallest safe change](principles/smallest-safe-change.md) when sizing a diff. Delete, reuse, then patch. Keep comments only for constraints the code cannot show.
- [Shape before logic](principles/shape-before-logic.md) before writing behavior. Name legal states first. Make illegal combinations unrepresentable.
- [Boundary discipline](principles/boundary-discipline.md) at CLI, config, network, and auth edges. Guard the boundary. Trust internal types.
- [Preserve safety](principles/preserve-safety.md) on any auth, permission, billing, secret, or destructive path. Simplicity must not weaken a gate.
- [Proof over proxy](principles/proof-over-proxy.md) before claiming done. Observe the authoritative surface.
- [Fix root causes](principles/fix-root-causes.md) on defects. Reproduce first. Do not silence a crash with a nil check.
- [Sequence verifiable units](principles/sequence-verifiable-units.md) on multi-step work. A verifiable unit is not a throwaway compatibility layer. Build a rerunnable tool after the first proven manual unit.
- [Idempotent effects](principles/idempotent-effects.md) on retries, installs, and lifecycle steps.
- [Encode lessons](principles/encode-lessons.md) only for recurring failures, at the earliest enforceable boundary.
- [Earned parallelism](principles/earned-parallelism.md) before any writable fan-out. Default to one owner.

## Route the work

Resolve common work without loading the full catalog:

| Intent | Workflow | Playbook |
| --- | --- | --- |
| Read-only question, audit, repository understanding, or diagnosis-only defect | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Investigation](playbooks/investigation.md) |
| Multi-phase work, several contracts, or no safe narrow route | [`patpat-plan`](../patpat-plan/SKILL.md) | [Bespoke workflow](playbooks/bespoke-workflow.md) |
| Contract, architecture, migration, security-sensitive, or cross-cutting design | [`patpat-architect`](../patpat-architect/SKILL.md) | [Architecture change](playbooks/architecture-change.md) |
| Defective or unexplained behavior with implementation requested | [`patpat-debug`](../patpat-debug/SKILL.md) | [Defect](playbooks/defect.md) |
| Bounded feature | [`patpat-change`](../patpat-change/SKILL.md) | [Bounded change](playbooks/bounded-change.md) |
| Proof of an existing claim or artifact | [`patpat-verify`](../patpat-verify/SKILL.md) | Use the workflow directly |
| Independent challenge of an implementation, diff, or proof claim | [`patpat-review`](../patpat-review/SKILL.md) | [Independent review](playbooks/independent-review.md) |
| Durable multi-phase execution, overnight run, or "don't stop" | [`patpat-run`](../patpat-run/SKILL.md) | [Multi-phase run](playbooks/multi-phase-run.md) |
| Install, update, remove, or validate Patpat on an agent host | [`patpat-setup`](../patpat-setup/SKILL.md) | Use the workflow directly |
| Named merge, publish, or deploy | [`patpat-ship`](../patpat-ship/SKILL.md) | [Authorized delivery](playbooks/authorized-delivery.md) |

If the intent is absent or ambiguous above, read the [route catalog](references/route-catalog.md). Do not load it for a clear common route.

[`/patpat`](../patpat/SKILL.md) is the slash alias for this skill.

If no narrow route fits, use `patpat-plan`. Do not persist a new reusable workflow unless repeated use proves it is needed.

Resolve overlaps by the earliest unsettled decision. Architect first when the target contract is unsettled. Plan when the remaining problem is sequencing. Impact assesses downstream risk without designing the replacement. A prototype settles an empirical fork instead of asking the human to choose.

Overnight, "don't stop", or "going to bed" continues the matched playbook through verify, review, and default commit-and-PR, then stops merge-ready. Merge only when the user explicitly names land or merge. Never deploy by implication.

## Run the graph

Read [the execution graph](references/execution-graph.md), the matched workflow, its playbook, and only the principles those files link.

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY -> REVIEW -> LEARN? -> REPORT
MUTATING? -> DEFAULT SHIP (commit + PR)
LAND? -> MERGE a green verified PR
```

A proof contract names the claim, authoritative surface, action, expected observation, and cleanup. Define it before editing.

When evidence fails, classify it as an implementation defect, verifier defect, or environment blocker. Return to the earliest invalid state. After three failures from the same unchanged blocker, stop and name the evidence required to continue.

Enter `LEARN?` only for a recurring failure worth encoding.

## Preserve control

- Ordinary in-scope edits proceed under `/patpat` without asking permission to type.
- Explicit `/patpat` or `$patpat` activation opts in to [commit and a ready PR](playbooks/default-delivery.md) after verify and review. Higher-priority repository rules and `don't commit` / `local only` still win.
- Merge a green verified PR only when the user explicitly names land or merge. Treat ambiguous `ship it` as commit-and-PR, not merge.
- Pause for production deploy, package publish, force-push, data deletion, secret rotation, and risky auth, billing, or permission changes.
- Workers never ship. The parent ships.

## Earn parallelism

Default to one owner. Arena, swarm, and autopilot run only when [earned parallelism](principles/earned-parallelism.md) passes, and they fall back to serial work when isolation is missing. Give every writable slice a separate Git worktree or host-enforced sandbox with its own Git index and process boundary; disjoint files in one shared worktree are not isolation. Use [`patpat-engineer`](../patpat-engineer/SKILL.md) for isolated slices. The parent verifies the integrated result. Do not trust worker summaries. The parent then runs default delivery when delivery authority exists.

## Report evidence

```text
Changed:
- <observable change and files>

Why:
- <evidence-backed reason>

Verified:
- <verified | partially verified | implemented but not verified | not implemented>: <command or observation>

Docs:
- <updated files or why no update was needed>

Risks:
- <remaining uncertainty, follow-up, or Low with scope>
```

Use `verified` only when the claimed behavior was observed on its authoritative surface.
