---
name: patpat-run
description: Drive, checkpoint, validate, resume, or safely take over multi-phase engineering work through a deterministic local state machine. Use for long work, arbitrary branch or handoff pickup, and tasks that must survive context loss without granting delivery authority.
---

# Patpat Run

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [sequence verifiable units](../patpat-loop/principles/sequence-verifiable-units.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and apply the [multi-phase run playbook](../patpat-loop/playbooks/multi-phase-run.md).

Use [`scripts/run_state.py`](scripts/run_state.py) for durable graph state. Require a Git worktree with at least one commit and store state under Git metadata. Print the absolute store path at each checkpoint. Do not commit run state or create a tracked handoff unless the user explicitly requests it.

Record declared authority and prohibitions at initialization, but never treat that record as fresh delivery approval. Require a structured proof contract before `ACT`, a content-bound `file:/absolute/path` evidence receipt before `REVIEW`, and independent review evidence before `LEARN` or `REPORT`. Invalidate proof when committed, staged, unstaged, untracked, assume-unchanged, or embedded-repository state changes. After three consecutive failures with the same blocker, graph node, and snapshot, stop the run as `BLOCKED`.

Never record secrets, tokens, raw private logs, or sensitive payloads in run state or receipts. Point only to a safe, inspectable evidence file. Treat deletion or content change as stale evidence.

If a process interruption leaves a lock, run `unlock` only after confirming the recorded process stopped. Let the engine reject live, malformed, or cross-host locks; never delete them by assumption.

Keep delivery outside the run engine. A run may record authority but must still route commit, push, publish, merge, or deployment through `patpat-ship` at the moment of action.

On resume, validate the store, compare live repository state, inspect intentional and pre-existing changes, and continue from the earliest valid graph node. Never trust a checkpoint merely because it parses.

When inheriting an arbitrary branch, transcript, or handoff without a valid Patpat store, apply the [session takeover playbook](../patpat-loop/playbooks/session-takeover.md) before initializing a new run.

When the request is a queue of independent PRs or a linear verified stack, apply the [autopilot playbook](../patpat-loop/playbooks/autopilot.md). Owners build and prove. The root verifies. Landing still requires a named delivery action.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
