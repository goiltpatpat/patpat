# Program Coordination

Use this reference only for a checked multi-unit plan or writable fan-out. A single durable run stays on the `run_state.py` path in the parent skill.

## Program state and fencing

Initialize [`../scripts/program_state.py`](../scripts/program_state.py) from the validated plan. Reject unordered units with exact, ancestor, or conservatively overlapping declared ownership. The validator does not compare a candidate diff with its unit's declared files; the integration owner must inspect changed paths before recording each head. Keep dispatch closed until the integration owner supplies an absolute content-bound parallel-gate receipt that binds the plan digest, every unit's unique isolation identity, and all earned-parallelism checks. Pass the `team_shape.py` result as `--worker-limit <n>` when opening dispatch; the default is one. The durable store caps assigned units in `pending` or `running` state, and `blocked` or `completed` units release their slot. Optionally pass `--deadline <future-UTC-timestamp> --integration-reserve-minutes <n>` together; at the derived cutoff, new assignments and reactivations stop while current assignments can finish and record proof. If no budget is saved, dispatch without these values is unbounded. When reopening dispatch, the existing budget is preserved; pass `--clear-budget` to remove it. These limits govern recorded coordination state and do not observe or cap host processes.

Assign each dependency-ready frontier unit with an explicit actor, receipt-bound isolation identity, and expected generation. Pass the returned generation on every worker-controlled head, state, verdict, and unit-inbox mutation; never infer the current generation for a caller. Change a unit head only with its expected current head (`none` for the first head), and require that head to contain every declared dependency head in its Git ancestry. Treat each verdict slot as write-once until head change or reassignment. Reassignment increments the fencing token and rejects stale worker output. Closing dispatch invalidates every issued assignment, including completed units: it advances each generation, clears its assignment, unit inbox, verification, and review, and resets it to pending. Reopening requires fresh assignment calls and fresh proof.

Record unit events through the inbox with that unit's current head. Require the bound integration owner for program-wide events and acknowledgement; peek first and acknowledge a sequence only after processing the handoff. A changed dispatch receipt clears the inbox so a new authority epoch cannot inherit unattributed events. Bind verification and independent review to commits present in the repository. Require a fresh passing verification before review, and reject the verifier, assigned worker, or integration owner as reviewer. Recheck dependency ancestry before verdicts, completion, and delivery. Open the whole-program delivery gate only when every unit has fresh evidence and one unit depends on and contains every other unit. Check a delivered head against its live checkout with `check-delivery`; [delivery proof](delivery-proof.md) defines slice and whole-program delivery. Any unit head change clears that unit's proof and inbox; a changed dependency head also revokes downstream assignments and evidence before work can resume.

The program store coordinates state only; its local identities are self-asserted labels, not authentication. It does not stop an old process from writing an external surface, spawn workers, observe providers, or grant commit, push, merge, publish, or deploy authority.

When changing `require_current_assignment`, run [`../scripts/verify_assignment_fence.py`](../scripts/verify_assignment_fence.py) and the program-state self-test. The bounded guard checker explores finite gate, evidence, assignment, generation, actor, and isolation combinations and verifies that it catches a deliberately weakened generation check. The optional [TLA+ assignment model](assignment-generation-model.md) checks bounded reassign, revoke, and write traces and requires counterexamples from both a generation-guard mutant and a rejected-write mutant. The model does not prove actor authentication; neither model proves file-lock behavior, external effects, or unbounded correctness. The program-state self-test separately exercises stale mutations against the local store.

## Parallel admission receipt

Before fan-out, write a schema-v2 earned-parallelism receipt as bounded JSON. For every check, attach one or more `{path, sha256, size}` bindings under `supporting_evidence`; create each binding with `team_shape.py --bind-evidence /absolute/path/to/safe-artifact`. The validator checks the current bytes of bounded, unique regular files and the receipt's program, plan, owner, and unit bindings. The program store retains those evidence bindings, reports `dispatch_evidence_fresh`, and rejects new assignments, worker mutations, and delivery admission while any referenced file is missing or changed. A schema-v1 receipt remains readable, but writable selection falls back to serial and the receipt cannot open writable dispatch.

These files make the coordinator's basis inspectable; their hashes do not prove the claims, authorship, or host-enforced isolation. Use serial work when the conditions cannot be confirmed. The recommendation and receipt never grant authority. Send typed handoff cards and evidence pointers, never full worker transcripts. Mutation commands print bounded receipts by default; request `--full` only for deliberate ledger inspection. Use `status --brief` or `status --unit <id>`, and page the inbox with `--after` plus `--limit`.

## Team selection

Pass the same receipt and exact program bindings used by the program store:

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
