---
name: patpat-loop
description: Route non-trivial repository work through an evidence-driven engineering loop. Use when a task spans multiple steps, changes code or contracts, requires diagnosis, or needs rigorous proof before completion.
---

# Patpat Loop

Own the task from scope to evidence. Prefer one reliable end-to-end path over broad generation.

## Route the work

Do not apply Patpat outside software engineering or repository operations. Classify repository work with this table and read the linked workflow before acting:

| Intent | Workflow | Playbook |
| --- | --- | --- |
| Read-only question, audit, repository understanding, or diagnosis-only defect | [`patpat-inspect`](../patpat-inspect/SKILL.md) | [Investigation](playbooks/investigation.md) |
| Multi-phase work, several contracts, or no safe narrow route | [`patpat-plan`](../patpat-plan/SKILL.md) | [Bespoke workflow](playbooks/bespoke-workflow.md) |
| Blast-radius or downstream-regression analysis | [`patpat-impact`](../patpat-impact/SKILL.md) | [Blast radius](playbooks/blast-radius.md) |
| Contract, architecture, migration, security-sensitive, or cross-cutting design | [`patpat-architect`](../patpat-architect/SKILL.md) | [Architecture change](playbooks/architecture-change.md) |
| Defective or unexplained behavior with implementation requested | [`patpat-debug`](../patpat-debug/SKILL.md) | [Defect](playbooks/defect.md) |
| Latency, CPU, memory, throughput, resource regression, or target-driven numeric optimization | [`patpat-perf`](../patpat-perf/SKILL.md) | [Performance](playbooks/performance.md) |
| Bounded feature or behavior-preserving refactor | [`patpat-change`](../patpat-change/SKILL.md) | [Bounded change](playbooks/bounded-change.md) |
| Proof of an existing claim or artifact | [`patpat-verify`](../patpat-verify/SKILL.md) | Use the workflow directly |
| Independent challenge of an implementation, diff, or proof claim | [`patpat-review`](../patpat-review/SKILL.md) | [Independent review](playbooks/independent-review.md) |
| Durable multi-phase execution, checkpoint, resume, arbitrary branch takeover, or handoff pickup | [`patpat-run`](../patpat-run/SKILL.md) | [Multi-phase run](playbooks/multi-phase-run.md) |
| Install, update, remove, or validate Patpat on an agent host | [`patpat-setup`](../patpat-setup/SKILL.md) | Use the workflow directly |
| Explicit delivery-readiness, commit, pull-request, publish, release, or deployment request | [`patpat-ship`](../patpat-ship/SKILL.md) | Use the workflow directly |
| Create or revise a reusable agent skill | [`patpat-skill`](../patpat-skill/SKILL.md) | [Skill change](playbooks/skill-change.md) |
| Test whether a skill triggers and behaves correctly | [`patpat-eval`](../patpat-eval/SKILL.md) | [Behavioral evaluation](playbooks/behavioral-eval.md) |
| Create or maintain a project-specific verification skill | [`patpat-verifier`](../patpat-verifier/SKILL.md) | [Project verifier](playbooks/project-verifier.md) |
| Encode a recurring failure or correction into a durable constraint | [`patpat-learn`](../patpat-learn/SKILL.md) | [Learning](playbooks/learning.md) |
| Design or scaffold an external automation for a concrete integration | [`patpat-automation`](../patpat-automation/SKILL.md) | [Automation design](playbooks/automation-design.md) |

If a software or repository task has no matching narrow route, use `patpat-plan` to design a bounded workflow from evidence. Do not persist a new reusable workflow unless repeated use proves it is needed.

Resolve overlaps by the earliest unsettled decision. Use `patpat-architect` first when a migration's target contract, compatibility, or rollback design is unsettled; use `patpat-plan` when those decisions are settled and the remaining problem is sequencing verifiable phases. Use `patpat-impact` to assess downstream risk without designing the replacement.

## Run the graph

Read [the execution graph](references/execution-graph.md), the matched workflow, its playbook when listed, and only the principles those files link.

Use this state sequence for every mutating task:

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY -> REVIEW -> LEARN? -> REPORT
```

Keep each transition explicit. Define the proof contract before editing. A proof contract names the claim, authoritative surface, action, expected observation, and cleanup.

When evidence fails, classify the failure as an implementation defect, verifier defect, or environment blocker. Gather new evidence and return to the earliest invalid state. Never repeat the same attempt without a meaningful change.

Enter `LEARN?` only when the active task exposed a recurring failure mode worth encoding. Skip it for one-off facts and routine completion.

## Preserve control

- Inspect repository rules, relevant code, current state, and minimum continuity files before changing anything.
- Make the smallest safe change that satisfies the proof contract.
- Preserve authentication, authorization, validation, redaction, feature gates, rollback paths, and destructive-operation checks.
- Require explicit user authority for external writes. Obtain fresh confirmation immediately before destructive actions, risky permission changes, production mutations, publishing, or deployment.
- Do not commit, push, publish, deploy, or open a pull request unless the user explicitly requests that action.

## Earn parallelism

Default to one owner. Parallelize only when all conditions in [earned parallelism](principles/earned-parallelism.md) pass. This release ships no native writable engineer adapter; use [`patpat-engineer`](../patpat-engineer/SKILL.md) only when the active host can enforce isolated ownership. Challenge integrated work through `patpat-review`, and verify artifacts instead of trusting agent summaries.

## Report evidence

End implementation work with these fields:

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

Use `verified` only when the claimed behavior was observed on its authoritative surface. Tests and builds support the claim but do not replace runtime or artifact evidence when such evidence is practical.
