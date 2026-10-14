---
name: patpat-run
description: Drive, checkpoint, validate, resume, or safely take over multi-phase engineering work through a deterministic local state machine. Use for long work, arbitrary branch or handoff pickup, and tasks that must survive context loss without granting delivery authority.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"GitRepository","requires_state":[],"produces_state":[],"verification_cmd":""}'
---

# Patpat Run

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [sequence verifiable units](../patpat-loop/principles/sequence-verifiable-units.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and apply the [multi-phase run playbook](../patpat-loop/playbooks/multi-phase-run.md).

Use [`scripts/run_state.py`](scripts/run_state.py) for durable graph state. Require a Git worktree with at least one commit and store state under Git metadata. Print the absolute store path at each checkpoint. Do not commit run state or create a tracked handoff unless the user explicitly requests it. Keep an append-only [human decision trail](references/decision-trail.md) at `<git patpat/runs>/<run-id>/decisions.tsv` next to `state.json`; same privacy as run state.

For a checked multi-unit plan, initialize [`scripts/program_state.py`](scripts/program_state.py) from the validated plan. Reject unordered units with exact, ancestor, or conservatively overlapping declared ownership. The validator does not compare a candidate diff with its unit's declared files; the integration owner must inspect changed paths before recording each head. Keep dispatch closed until the integration owner supplies an absolute content-bound parallel-gate receipt that binds the plan digest, every unit's unique isolation identity, and all earned-parallelism checks. Open dispatch with `set-gate dispatch open --receipt /absolute/path --integration-owner <identity>`, then assign only the number of units allowed by the `team_shape.py` worker limit; the state store does not enforce a concurrent-assignment cap. Assign each dependency-ready frontier unit with an explicit actor, receipt-bound isolation identity, and expected generation. Pass the returned generation on every worker-controlled head, state, verdict, and unit-inbox mutation; never infer the current generation for a caller. Change a unit head only with its expected current head (`none` for the first head), and require that head to contain every declared dependency head in its Git ancestry. Treat each verdict slot as write-once until head change or reassignment. Reassignment increments the fencing token and rejects stale worker output. Closing dispatch revokes every active assignment; reopening it requires fresh assignment calls. Record unit events through the inbox with that unit's current head. Require the bound integration owner for program-wide events and acknowledgement; peek first and acknowledge a sequence only after processing the handoff. A changed dispatch receipt clears the inbox so a new authority epoch cannot inherit unattributed events. Bind verification and independent review to commits present in the repository. Require a fresh passing verification before review, and reject the verifier, assigned worker, or integration owner as reviewer. Recheck dependency ancestry before verdicts, completion, and delivery. Open delivery only when every dependency has fresh evidence. Any unit head change clears that unit's proof and inbox; a changed dependency head also revokes downstream assignments and evidence before work can resume. The program store coordinates state only; its local identities are self-asserted labels, not authentication. It does not stop an old process from writing an external surface, spawn workers, observe providers, or grant commit, push, merge, publish, or deploy authority.

Before fan-out, write a schema-v2 earned-parallelism receipt as bounded JSON. For every check, attach one or more `{path, sha256, size}` bindings under `supporting_evidence`; create each binding with `team_shape.py --bind-evidence /absolute/path/to/safe-artifact`. The validator checks the current bytes of bounded, unique regular files and the receipt's program, plan, owner, and unit bindings. The program store retains those evidence bindings, reports `dispatch_evidence_fresh`, and rejects new assignments, worker mutations, and delivery admission while any referenced file is missing or changed. A schema-v1 receipt remains readable, but writable selection falls back to serial and the receipt cannot open writable dispatch. These files make the coordinator's basis inspectable; their hashes do not prove the claims, authorship, or host-enforced isolation. Use serial work when the conditions cannot be confirmed. The recommendation and receipt never grant authority. Send typed handoff cards and evidence pointers, never full worker transcripts. Mutation commands print bounded receipts by default; request `--full` only for deliberate ledger inspection. Use `status --brief` or `status --unit <id>`, and page the inbox with `--after` plus `--limit`.

For team selection, pass the same receipt and exact program bindings used by the program store:

```sh
python3 skills/patpat-run/scripts/team_shape.py \
  --work-kind writable --decomposable true --stable-verifier true \
  --worker-capacity 2 --worker-budget 2 --writable-gates-passed true \
  --uncertainty low --consequence low --independent-oracle false \
  --parallel-gate-receipt /absolute/path/parallel-gate.json \
  --program-id release-train --plan-digest "$PLAN_DIGEST" \
  --integration-owner coordinator --unit contract --unit consumer
```

The receipt's `supporting_evidence` object must contain every check key exactly once. Each value is a non-empty array of bindings printed by `--bind-evidence`:

```json
"supporting_evidence": {
  "representative_single_owner_run": [{"path": "/absolute/evidence/single-owner.md", "sha256": "<sha256>", "size": 123}],
  "stable_verifier": [{"path": "/absolute/evidence/verifier.md", "sha256": "<sha256>", "size": 123}],
  "independent_slices": [{"path": "/absolute/evidence/slices.md", "sha256": "<sha256>", "size": 123}],
  "isolated_workspaces": [{"path": "/absolute/evidence/workspaces.md", "sha256": "<sha256>", "size": 123}],
  "isolated_resources": [{"path": "/absolute/evidence/isolation.md", "sha256": "<sha256>", "size": 123}],
  "whole_system_verification": [{"path": "/absolute/evidence/system-proof.md", "sha256": "<sha256>", "size": 123}]
}
```

Set `PLAN_DIGEST` to the validated plan digest. Replace the illustrative paths and values with the binder output for the actual artifacts. A structurally valid but missing, changed, or malformed schema-v2 artifact is rejected; it does not trigger serial fallback. If a referenced artifact later changes, fresh checks, delivery readiness, and delivery admission fail until the receipt is refreshed and dispatch is reopened. A schema-v1 receipt causes serial fallback only for writable team selection; read-only selection remains eligible under its own checks.

Record declared authority and prohibitions at initialization, but never treat that record as fresh delivery approval. Require a structured proof contract before `ACT`, a content-bound `file:<absolute-path>` evidence receipt before `REVIEW`, and independent review evidence before `LEARN` or `REPORT`. Use the host's native absolute-path form; both POSIX and Windows paths are valid. On resume, a prior receipt counts only when `validate` accepts it as fresh for the current candidate, contract, evidence epoch, and snapshot. The run snapshot covers Git-visible repository state, not ignored files or the process and dependency environment; bind any task-relevant non-secret inputs separately or rerun the check. A failed or partial verification, or changes-required review, does not clear the streak; a `verified` verification, `pass` review receipt, or materially revised proof contract does. After a `failed`, `partial`, or `changes-required` receipt, record any persistent blocker with `record --kind failure`, a stable blocker key, and the matching `--failure-class` (`implementation`, `verifier`, or `environment`). Decision and experiment notes and graph transitions do not reset the streak. A failure count increments only when the immediately preceding failure has the same blocker, failure class, graph node, and snapshot; otherwise the new count is one. After three consecutive failures with the same key, stop the run as `BLOCKED`.

`run_state.py` does not record or enforce user approval for learning. Treat `LEARN` as proposal-pending; do not edit or transition to `VERIFY` until explicit approval is received. If approval is pending, keep the run at `LEARN`; if declined, report without making the proposed edit.

Never record secrets, tokens, raw private logs, or sensitive payloads in run state or receipts. Point only to a safe, inspectable evidence file. Treat deletion or content change as stale evidence.

If a process interruption leaves a lock, inspect it first. Use `unlock` for a run or `recover-lock` for a program only when the engine proves a same-host owner is dead. Let the engine reject live, malformed, or cross-host locks; never delete them by assumption.

Route completion through `patpat-ship` when delivery intent exists. Explicit Patpat activation alone does not authorize default commit-and-PR; see the operating protocol and default-delivery playbook. Durable-run mechanical gates remain separate. Overnight stops merge-ready. Merge only with explicit land or merge language and green checks.

On resume, validate the store, compare live repository state, inspect intentional and pre-existing changes, and continue from the earliest valid graph node. Never trust a checkpoint merely because it parses.

When inheriting an arbitrary branch, transcript, or handoff without a valid Patpat store, apply the [session takeover playbook](../patpat-loop/playbooks/session-takeover.md) before initializing a new run.

When taking over, lock the time window, do not reconstruct from transcripts alone, and verify surfaced PRs, branches, and tickets with live git and gh.

Program stores created before assignment fencing are schema v1. Do not trust or silently upgrade their actor labels or evidence. Run `migrate-v1 --invalidate-legacy-evidence` explicitly; migration preserves the plan and heads, clears legacy evidence and inbox, closes gates, and requires fresh dispatch plus assignments. Schema-v2 stores require `migrate-v2 --invalidate-legacy-evidence`; this preserves the plan and heads, clears every unit's verification and review evidence plus the old dispatch binding and inbox, resets units to pending, revokes assignments, and closes both gates. Assignment generations advance where an assignment was active. Require fresh schema-v2 evidence and rerun unit proof before delivery. Before migrating a real store, stop writers, create and verify a protected copy of the exact `state.json` outside the live store, and obtain explicit user authorization for that store and migration. If post-migration status is wrong, stop writers and restore the verified copy with the pre-migration Patpat version that reads that schema before resuming; current code deliberately refuses schema-v2 state.

When the request is a queue of independent PRs or a linear verified stack, apply the [autopilot playbook](../patpat-loop/playbooks/autopilot.md). Owners build and prove. The root verifies. Landing still requires a named delivery action.

For a multi-PR queue or stack, write a bounded host-neutral JSON plan and validate it with [`scripts/validate_plan.py`](scripts/validate_plan.py) before fan-out or implementation. Give every unit an id, dependencies, disjoint ownership unless dependency order serializes an overlap, build command or `N/A: <reason>`, observable proof, targeted/live/performance checks or explicit `N/A: <reason>`, `exact-head` evidence binding, and `independent-pass-before-delivery` review gate. Record claimed delivery authority once for the plan, then prove that authority again at execution time; a valid plan and an open dispatch gate never grant permission. Do not encode fixed model or lane counts.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
