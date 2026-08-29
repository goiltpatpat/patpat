---
name: patpat-run
description: Drive, checkpoint, validate, resume, or safely take over multi-phase engineering work through a deterministic local state machine. Use for long work, arbitrary branch or handoff pickup, and tasks that must survive context loss without granting delivery authority.
---

# Patpat Run

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [sequence verifiable units](../patpat-loop/principles/sequence-verifiable-units.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and apply the [multi-phase run playbook](../patpat-loop/playbooks/multi-phase-run.md).

Use [`scripts/run_state.py`](scripts/run_state.py) for durable graph state. Require a Git worktree with at least one commit and store state under Git metadata. Print the absolute store path at each checkpoint. Do not commit run state or create a tracked handoff unless the user explicitly requests it.

For a checked multi-unit plan, initialize [`scripts/program_state.py`](scripts/program_state.py) from the validated plan. Reject unordered units with exact, ancestor, or conservatively overlapping glob ownership. Keep dispatch closed until the integration owner supplies an absolute content-bound parallel-gate receipt that binds the plan digest, every unit's unique isolation identity, and all earned-parallelism checks. Open dispatch with `set-gate dispatch open --receipt /absolute/path --integration-owner <identity>`. Record worker events through the inbox; peek first and acknowledge a sequence only after the integration owner has processed the handoff. Bind verification and independent review to commits present in the repository, and open delivery only when every dependency has fresh evidence. A changed dependency head invalidates downstream evidence. The program store coordinates state only; it does not spawn workers, observe providers, or grant commit, push, merge, publish, or deploy authority.

Before fan-out, write the earned-parallelism receipt as bounded JSON and pass its absolute path to [`scripts/team_shape.py`](scripts/team_shape.py) with `--parallel-gate-receipt`, `--program-id`, `--plan-digest`, `--integration-owner`, every `--unit`, observed capacity, and an explicit worker budget. Writable selection fails closed unless those expected values match the receipt; receipt-internal claims do not bind themselves to the active job. A boolean claim alone cannot admit writable fan-out. Accept serial fallback; the recommendation and receipt never grant authority. Send typed handoff cards and evidence pointers, never full worker transcripts. Mutation commands print bounded receipts by default; request `--full` only for deliberate ledger inspection. Use `status --brief` or `status --unit <id>`, and page the inbox with `--after` plus `--limit`.

Record declared authority and prohibitions at initialization, but never treat that record as fresh delivery approval. Require a structured proof contract before `ACT`, a content-bound `file:<absolute-path>` evidence receipt before `REVIEW`, and independent review evidence before `LEARN` or `REPORT`. Use the host's native absolute-path form; both POSIX and Windows paths are valid. Invalidate proof when committed, staged, unstaged, untracked, assume-unchanged, or embedded-repository state changes. After three consecutive failures with the same blocker, graph node, and snapshot, stop the run as `BLOCKED`.

Never record secrets, tokens, raw private logs, or sensitive payloads in run state or receipts. Point only to a safe, inspectable evidence file. Treat deletion or content change as stale evidence.

If a process interruption leaves a lock, inspect it first. Use `unlock` for a run or `recover-lock` for a program only when the engine proves a same-host owner is dead. Let the engine reject live, malformed, or cross-host locks; never delete them by assumption.

Route completion through `patpat-ship`. Explicit Patpat activation authorizes default commit-and-PR after proof unless a higher-priority rule blocks it. Overnight stops merge-ready. Merge only with explicit land or merge language and green checks.

On resume, validate the store, compare live repository state, inspect intentional and pre-existing changes, and continue from the earliest valid graph node. Never trust a checkpoint merely because it parses.

When inheriting an arbitrary branch, transcript, or handoff without a valid Patpat store, apply the [session takeover playbook](../patpat-loop/playbooks/session-takeover.md) before initializing a new run.

When the request is a queue of independent PRs or a linear verified stack, apply the [autopilot playbook](../patpat-loop/playbooks/autopilot.md). Owners build and prove. The root verifies. Landing still requires a named delivery action.

For a multi-PR queue or stack, write a bounded host-neutral JSON plan and validate it with [`scripts/validate_plan.py`](scripts/validate_plan.py) before fan-out or implementation. Give every unit an id, dependencies, disjoint ownership unless dependency order serializes an overlap, build command or `N/A: <reason>`, observable proof, targeted/live/performance checks or explicit `N/A: <reason>`, `exact-head` evidence binding, and `independent-pass-before-delivery` review gate. Record claimed delivery authority once for the plan, then prove that authority again at execution time; a valid plan and an open dispatch gate never grant permission. Do not encode fixed model or lane counts.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
