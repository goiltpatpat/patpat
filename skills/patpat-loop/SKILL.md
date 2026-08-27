---
name: patpat-loop
description: Route non-trivial repository work through an evidence-driven engineering loop. Use for /patpat, /patpat-loop, $patpat, $patpat-loop, or requests to work in this style.
disable-model-invocation: true
mode: true
reminder: New task with rigor, a playbook match, or ship intent -> apply /patpat. Casual turn or user opts out -> don't.
---

# Patpat Loop

`/patpat` and `/patpat-loop` are the same entry point. Codex uses `$patpat` or `$patpat-loop`.

Patpat is one system. The [operating protocol](references/operating-protocol.md) is the spine: judgment, safety, git, and evidence. The playbooks and principles are the machinery, informed by pstack jobs, renamed and bounded so they cannot override that spine.

This mode stays on across later turns after invocation. Trusted host hooks persist it across resume and compaction. Without a hook receipt, apply it for the rest of this session and report `current-turn-only` if a later session has no receipt. Say `disable /patpat` to opt out. Casual turns stay out of the way unless a playbook matches or the work needs rigor.

## Start

Open a todo list. The first items are:

1. Read the [operating protocol](references/operating-protocol.md) in full.
2. Read the principle index below.
3. Match a playbook, open it, and copy its steps into the todo list before any task-specific work. A skipped step stays listed with `skip: <reason>`.

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

| Intent | Workflow | Playbook |
| --- | --- | --- |
| Read-only question, audit, repository understanding, or diagnosis-only defect | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Investigation](playbooks/investigation.md) |
| Why the code reached this shape | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Rationale forensics](playbooks/rationale-forensics.md) |
| Multi-phase work, several contracts, or no safe narrow route | [`patpat-plan`](../patpat-plan/SKILL.md) | [Bespoke workflow](playbooks/bespoke-workflow.md) |
| Blast-radius or downstream-regression analysis | [`patpat-impact`](../patpat-impact/SKILL.md) | [Blast radius](playbooks/blast-radius.md) |
| Contract, architecture, migration, security-sensitive, or cross-cutting design | [`patpat-architect`](../patpat-architect/SKILL.md) | [Architecture change](playbooks/architecture-change.md) |
| Defective or unexplained behavior with implementation requested | [`patpat-debug`](../patpat-debug/SKILL.md) | [Defect](playbooks/defect.md) |
| Cheap deterministic regression target exists | [`patpat-debug`](../patpat-debug/SKILL.md) | [Regression first](playbooks/regression-first.md) |
| Latency, CPU, memory, throughput, or one-off resource regression | [`patpat-perf`](../patpat-perf/SKILL.md) | [Performance](playbooks/performance.md) |
| Sustained improvement of one metric | [`patpat-perf`](../patpat-perf/SKILL.md) | [Metric hillclimb](playbooks/metric-hillclimb.md) |
| Live leak, idle spin, or glitch | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Runtime forensics](playbooks/runtime-forensics.md) |
| Captured profile, trace, or heap snapshot | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Trace forensics](playbooks/trace-forensics.md) |
| Bounded feature | [`patpat-change`](../patpat-change/SKILL.md) | [Bounded change](playbooks/bounded-change.md) |
| Behavior-preserving refactor | [`patpat-change`](../patpat-change/SKILL.md) | [Behavior-preserving refactor](playbooks/behavior-preserving-refactor.md) |
| Throwaway sketch to settle a design fork | [`patpat-change`](../patpat-change/SKILL.md) | [Prototype](playbooks/prototype.md) |
| Pixel-level UI parity | [`patpat-verify`](../patpat-verify/SKILL.md) | [Visual equivalence](playbooks/visual-equivalence.md) |
| Proof of an existing claim or artifact | [`patpat-verify`](../patpat-verify/SKILL.md) | Use the workflow directly |
| Independent challenge of an implementation, diff, or proof claim | [`patpat-review`](../patpat-review/SKILL.md) | [Independent review](playbooks/independent-review.md) |
| Competing attempts at the same brief | [`patpat-arena`](../patpat-arena/SKILL.md) | [Arena](playbooks/arena.md) |
| Parallel slices, races, or coverage | [`patpat-swarm`](../patpat-swarm/SKILL.md) | [Swarm](playbooks/swarm.md) |
| Queue of independent PRs or a linear verified stack | [`patpat-run`](../patpat-run/SKILL.md) | [Autopilot](playbooks/autopilot.md) |
| Named issue-source triage and reproduce loop | [`patpat-automation`](../patpat-automation/SKILL.md) | [Issue loop](playbooks/issue-loop.md) |
| Durable multi-phase execution, overnight run, or "don't stop" | [`patpat-run`](../patpat-run/SKILL.md) | [Multi-phase run](playbooks/multi-phase-run.md) |
| Resume, pause, or take over in-flight work | [`patpat-run`](../patpat-run/SKILL.md) | [Session takeover](playbooks/session-takeover.md) |
| PR status, conflicts, review threads, or get-it-green | [`patpat-inspect`](../patpat-inspect/SKILL.md) or [`patpat-change`](../patpat-change/SKILL.md) | [PR drive](playbooks/pr-drive.md) |
| Install, update, remove, or validate Patpat on an agent host | [`patpat-setup`](../patpat-setup/SKILL.md) | Use the workflow directly |
| Named commit, pull request, publish, release, merge, deployment, or overnight land | [`patpat-ship`](../patpat-ship/SKILL.md) | [Authorized delivery](playbooks/authorized-delivery.md) |
| Create or revise a reusable agent skill | [`patpat-skill`](../patpat-skill/SKILL.md) | [Skill change](playbooks/skill-change.md) |
| Test whether a skill triggers and behaves correctly | [`patpat-eval`](../patpat-eval/SKILL.md) | [Behavioral evaluation](playbooks/behavioral-eval.md) |
| Create or maintain a project-specific verification skill | [`patpat-verifier`](../patpat-verifier/SKILL.md) | [Project verifier](playbooks/project-verifier.md) |
| Encode a recurring failure or correction into a durable constraint | [`patpat-learn`](../patpat-learn/SKILL.md) | [Learning](playbooks/learning.md) |
| Design or scaffold an external automation for a concrete integration | [`patpat-automation`](../patpat-automation/SKILL.md) | [Automation design](playbooks/automation-design.md) |

[`/patpat`](../patpat/SKILL.md) is the slash alias for this skill.

If no narrow route fits, use `patpat-plan`. Do not persist a new reusable workflow unless repeated use proves it is needed.

Resolve overlaps by the earliest unsettled decision. Architect first when the target contract is unsettled. Plan when the remaining problem is sequencing. Impact assesses downstream risk without designing the replacement. A prototype settles an empirical fork instead of asking the human to choose.

Overnight, "don't stop", or "going to bed" continues the matched playbook through verify and review. It is delivery authority only when the request also names commit, PR, merge, publish, or deploy.

## Run the graph

Read [the execution graph](references/execution-graph.md), the matched workflow, its playbook, and only the principles those files link.

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY -> REVIEW -> LEARN? -> REPORT
NAMED DELIVERY? -> SHIP the named action only
```

A proof contract names the claim, authoritative surface, action, expected observation, and cleanup. Define it before editing.

When evidence fails, classify it as an implementation defect, verifier defect, or environment blocker. Return to the earliest invalid state. After three failures from the same unchanged blocker, stop and name the evidence required to continue.

Enter `LEARN?` only for a recurring failure worth encoding.

## Preserve control

- Ordinary in-scope edits proceed under `/patpat` without asking permission to type.
- Delivery is a separate gate. Commit, push, pull request, merge, publish, and deploy only when the current request names that action.
- Pause for production deploy, force-push, data deletion, secret rotation, and risky auth, billing, or permission changes.

## Earn parallelism

Default to one owner. Arena, swarm, and autopilot run only when [earned parallelism](principles/earned-parallelism.md) passes, and they fall back to serial work when isolation is missing. Use [`patpat-engineer`](../patpat-engineer/SKILL.md) for isolated slices. The parent verifies the integrated result. Do not trust worker summaries. Delivery still requires a named action.

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
