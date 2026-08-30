# Run Durable Work

![Patpat follows a teal route of sealed evidence checkpoints while one coral branch stops safely and a helper drone resumes from the last valid state.](./images/durable-runs.jpg)

Long work needs explicit state, not a longer prompt. `patpat-run` models phases and evidence as a deterministic local graph that can stop, resume, and reject stale proof.

## Use a graph when continuity matters

Choose a durable run when the task spans sessions, has dependent phases, needs checkpoints, or may be handed to another agent. Keep a bounded task in the normal loop; state machinery is overhead when one verified patch will finish the job.

## Define the finish condition

A duration is not a finish condition. State an observable predicate:

```text
/patpat keep working until every migration fixture passes against a clean database and the rollback restores the original schema. Pause safely on the third identical blocker.
```

The run can check that condition after each phase. It must not relax the condition to manufacture completion.

## Advance only with current evidence

The graph refuses:

- implementation without a proof contract;
- review without current content-bound evidence;
- completion without independent review;
- endless retries after the same blocker repeats three times.

Each checkpoint records enough state for a cold-start takeover to inspect the repository and continue from reality.

## Pause without pretending to finish

Use the safe-pause playbook when authority, environment access, or user input is genuinely required. Preserve the branch, graph state, current evidence, blocker, and next executable action. Do not open a pull request merely to make a pause look complete.

## Validate multi-PR plans

Before multi-PR execution, validate the checked plan:

```bash
python3 skills/patpat-run/scripts/validate_plan.py --self-test
```

Plan validity proves dependency, ownership, evidence, and review structure. It never grants commit, merge, deploy, or publication authority.

For a validated multi-unit plan, `skills/patpat-run/scripts/program_state.py` persists the dependency frontier, worker inbox, exact-head verification ledger, assignment generations, and explicit dispatch and delivery gates under Git metadata. It does not spawn agents or call a provider. Assign only dependency-ready frontier units. Every worker mutation carries the current assignment generation; reassignment increments the token and rejects late output from the old assignment. Head updates compare the caller's expected current head, and each dependent head must contain every declared dependency head in its Git ancestry. Verdict slots are write-once per head and assignment. Closing dispatch revokes active assignments, so reopening requires fresh assignment calls. Unit inbox events require the current head; program-wide events and acknowledgement require the bound integration owner. These are coordination fences with self-asserted local identities, not worker authentication or an external process lease. Any unit head change clears that unit's prior proof and inbox; an upstream head change also revokes downstream assignments and evidence before the frontier can advance. Patpat rechecks ancestry at verdict, completion, and delivery boundaries. Unordered units cannot claim exact, ancestor, or conservatively overlapping glob ownership.

Schema-v1 stores require explicit `migrate-v1 --invalidate-legacy-evidence`. Migration preserves the plan and recorded heads but clears legacy verdicts and inbox events, closes both gates, and requires fresh assignments. Patpat never treats an old actor label as trusted identity.

Keep dispatch closed until the integration owner supplies one bounded parallel-gate receipt. Bind that receipt to the program id, validated plan digest, integration owner, every unit's unique isolation identity, and all earned-parallelism checks. Use the same receipt for team selection and `set-gate dispatch open`; a boolean claim alone cannot open writable fan-out.

State mutations return bounded receipts by default so long ledgers do not flood agent context. Plan, state, receipt, and inbox inputs are bounded and reject linked files where they cross a trust boundary. Use `status --brief`, `status --unit <id>`, and bounded inbox pages for normal coordination; request full state only for a deliberate audit. Lock acquisition has a bounded timeout. Inspect abandoned locks before recovery. Only a dead same-host owner is recoverable automatically.

`delivery_admitted` remains a compatibility field for evidence plus gate state; it never means delivery authority. Check `delivery_authority_granted`, which is always false, and reacquire current delivery authority through `patpat-ship`.

Next: [Earn parallelism](./07-earned-parallelism.md).
