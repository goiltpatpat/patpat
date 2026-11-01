---
name: patpat-run
description: Drive, checkpoint, validate, resume, or safely take over multi-phase engineering work through a deterministic local state machine. Use for long work, arbitrary branch or handoff pickup, and tasks that must survive context loss without granting delivery authority.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"GitRepository","requires_state":["execution-plan-settled"],"produces_state":["program-run-coordinated"],"verification_cmd":"python3 skills/patpat-run/scripts/check_assignment_model.py --self-test"}'
---

# Patpat Run

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [sequence verifiable units](../patpat-loop/principles/sequence-verifiable-units.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and apply the [multi-phase run playbook](../patpat-loop/playbooks/multi-phase-run.md).

Use [`scripts/run_state.py`](scripts/run_state.py) for durable graph state. Require a Git worktree with at least one commit and store state under Git metadata. Print the absolute store path at each checkpoint. Do not commit run state or create a tracked handoff unless the user explicitly requests it. Keep an append-only [human decision trail](references/decision-trail.md) at `<git patpat/runs>/<run-id>/decisions.tsv` next to `state.json`; same privacy as run state.

For a checked multi-unit plan or writable fan-out, read [program coordination](references/program-coordination.md) before using `program_state.py` or `team_shape.py`. Single durable runs do not load that reference.

Record declared authority and prohibitions at initialization, but never treat that record as fresh delivery approval. Require a structured proof contract before `ACT`, a content-bound `file:<absolute-path>` evidence receipt before `REVIEW`, and independent review evidence before `LEARN` or `REPORT`. Use the host's native absolute-path form; both POSIX and Windows paths are valid. On resume, a prior receipt counts only when `check-gate` passes for the gate it serves, which proves it fresh for the current candidate, contract, evidence epoch, and snapshot or identical proven tree; `validate` alone does not check every receipt at every node. The run snapshot covers Git-visible repository state, not ignored files or the process and dependency environment; bind any task-relevant non-secret inputs separately or rerun the check.

A failed or partial verification, or changes-required review, does not clear the streak; a `verified` verification, `pass` review receipt, or materially revised proof contract does. Re-recording an identical contract does not; the comparison covers the five canonical fields as text, so it cannot judge whether a reworded contract is materially different. After a `failed`, `partial`, or `changes-required` receipt, record any persistent blocker with `record --kind failure`, a stable blocker key, and the matching `--failure-class` (`implementation`, `verifier`, or `environment`). Decision and experiment notes and graph transitions do not reset the streak. A failure count increments only when the immediately preceding failure has the same blocker key, failure class, and graph node. A changed snapshot alone does not reset the count; each failure still records its own snapshot. Otherwise the new count is one.

After two consecutive failures at the same proof step with the same stable blocker, record the execution graph's five-field `Diagnostic Delta` with `record --kind decision --summary '<delta>'` before another attempt, even when an intervening fix changed the snapshot. The next attempt must change a named variable from that delta. After three consecutive failures with the same blocker key, failure class, and graph node, stop the run as `BLOCKED`.

`run_state.py` does not record or enforce user approval for learning. Treat `LEARN` as proposal-pending; do not edit or transition to `VERIFY` until explicit approval is received. If approval is pending, keep the run at `LEARN`; if declined, report without making the proposed edit.

Never record secrets, tokens, raw private logs, or sensitive payloads in run state or receipts. Point only to a safe, inspectable evidence file. Treat deletion or content change as stale evidence.

If a process interruption leaves a lock, inspect it first. Use `unlock` for a run or `recover-lock` for a program only when the engine proves a same-host owner is dead. Let the engine reject live, malformed, or cross-host locks; never delete them by assumption.

Route completion through `patpat-ship` when delivery intent exists. [Delivery proof](references/delivery-proof.md) defines the `commit`, `ship`, and `merge` gates. They read state and Git, so they can pass at `REPORT`; a new head or late merge request starts a new scoped run. Explicit Patpat activation alone does not authorize default commit-and-PR; see the operating protocol and default-delivery playbook. Durable-run mechanical gates remain separate. Overnight stops merge-ready. Merge only with explicit land or merge language and a passing provider gate.

On resume, validate the store, compare live repository state, inspect intentional and pre-existing changes, and continue from the earliest valid graph node. Never trust a checkpoint merely because it parses.

When inheriting an arbitrary branch, transcript, or handoff without a valid Patpat store, apply the [session takeover playbook](../patpat-loop/playbooks/session-takeover.md) before initializing a new run.

When taking over, lock the time window, do not reconstruct from transcripts alone, and verify surfaced PRs, branches, and tickets with live git and gh.

Program stores created before assignment fencing are schema v1. Do not trust or silently upgrade their actor labels or evidence. Run `migrate-v1 --invalidate-legacy-evidence` explicitly; migration preserves the plan and heads, clears legacy evidence and inbox, closes gates, and requires fresh dispatch plus assignments. Schema-v2 stores require `migrate-v2 --invalidate-legacy-evidence`; schema-v3 stores require `migrate-v3 --invalidate-legacy-evidence`. Each migration preserves the plan and heads, clears verification and review evidence, removes the old dispatch binding and inbox, resets units to pending, revokes assignments, and closes both gates. Assignment generations advance when a prior assignment snapshot exists. The v3 migration also creates the execution-policy record with no configured budget. Require fresh schema-v2 parallel-gate receipt evidence and rerun unit proof before delivery. Before migrating a real store, stop writers, create and verify a protected copy of the exact `state.json` outside the live store, and obtain explicit user authorization for that store and migration. If post-migration status is wrong, stop writers and restore the verified copy with the pre-migration Patpat version that reads that schema before resuming; current code deliberately refuses older program-state schemas.

Use `patpat-inspect` and [PR Drive](../patpat-loop/playbooks/pr-drive.md) for read-only PR status or topology; an explicit GitHub-native stack discovery uses its [PR Handoff](../patpat-loop/playbooks/pr-handoff.md) step. Apply the [autopilot playbook](../patpat-loop/playbooks/autopilot.md) only when asked to implement or coordinate an independent PR queue or linear verified stack. Owners build and prove. The root verifies. Landing still requires a named delivery action.

For an implementation or coordination request spanning multiple PRs, write a bounded host-neutral JSON plan and validate it with [`scripts/validate_plan.py`](scripts/validate_plan.py) before fan-out or implementation. Give every unit an id, dependencies, disjoint ownership unless dependency order serializes an overlap, build command or `N/A: <reason>`, observable proof, targeted/live/performance checks or explicit `N/A: <reason>`, `exact-head` evidence binding, and `independent-pass-before-delivery` review gate. Record claimed delivery authority once for the plan, then prove that authority again at execution time; a valid plan and an open dispatch gate never grant permission. Do not encode fixed model or lane counts.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
