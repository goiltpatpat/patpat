# Earn Parallelism

![A proven path passes through a verification gate before helper drones work in three isolated bays and Patpat integrates their components with a reviewer.](./images/earned-parallelism.jpg)

Parallel generation multiplies output. It does not multiply trust. Patpat starts with one reliable end-to-end path and adds concurrency only where ownership and integration proof are explicit.

## Start serial

Run the task through inspection, implementation, verification, and review with one owner. Record the failure modes. Encode recurring failures as constraints or checks. For every current writable program, keep the worker limit at 1 until one plan-specific pilot unit has fresh verification and review at its current head and the integration owner has inspected its actual changed paths. Earlier representative evidence admits consideration of parallelism but does not replace this pilot. This path-inspection gate is currently an integration-owner contract, not a receipt persisted or enforced by `program_state.py`. Scale only after the path is repeatably trustworthy.

## Isolate before running concurrently

Writable workers need separate worktrees or host-enforced sandboxes. Each worker receives:

- one bounded brief;
- explicit file ownership;
- a proof surface;
- a rough unit timebox and a partial-evidence return at expiry;
- a return contract;
- no merge authority.

If isolation is unavailable, run the work serially. Locks do not turn a shared mutable worktree into independent evidence.

## Choose the right topology

Record one bounded schema-v2 coordinator-attestation receipt that binds the program id, validated plan digest, integration owner, each writable gate claim, one unique isolation identity per unit, and supporting evidence for each check. Each evidence entry is one or more `{path, sha256, size}` file bindings; create them with `skills/patpat-run/scripts/team_shape.py --bind-evidence /absolute/path/to/safe-artifact`. The validator rechecks those bounded files when opening dispatch and before assignments, worker mutations, and delivery readiness; status exposes whether they remain fresh. The receipt still does not prove whether its claims are true or a host enforces isolation. If evidence is unavailable or stale, keep writable work serial. A schema-v1 receipt causes serial fallback for writable team selection and cannot open writable dispatch; read-only selection remains eligible under its own checks. Pass the receipt's absolute path and exact program bindings to `skills/patpat-run/scripts/team_shape.py`:

```sh
python3 skills/patpat-run/scripts/team_shape.py \
  --bind-evidence /absolute/evidence/verifier.md
```

Then assemble the printed `{path, sha256, size}` bindings into the receipt. For team selection, pass that same receipt and its exact program bindings to the script:

```sh
python3 skills/patpat-run/scripts/team_shape.py \
  --work-kind writable --decomposable true --stable-verifier true \
  --worker-capacity 2 --worker-budget 2 --writable-gates-passed true \
  --uncertainty low --consequence low --independent-oracle false \
  --parallel-gate-receipt /absolute/path/parallel-gate.json \
  --program-id release-train --plan-digest "$PLAN_DIGEST" \
  --integration-owner coordinator --unit contract --unit consumer
```

Set `PLAN_DIGEST` to the validated plan digest. The `supporting_evidence` map has one non-empty array for each of `representative_single_owner_run`, `stable_verifier`, `independent_slices`, `isolated_workspaces`, `isolated_resources`, and `whole_system_verification`. Each array contains binder output such as `{"path": "/absolute/evidence/verifier.md", "sha256": "<sha256>", "size": 123}`. A missing, changed, or malformed schema-v2 artifact is rejected rather than falling back to serial. If a bound file changes later, delivery readiness and admission also fail until the evidence is refreshed and dispatch reopened. The hashes make coordinator evidence inspectable; they do not prove the claims, authorship, or host-enforced isolation. Use the same receipt to open the program dispatch gate. Assign each unit with its receipt-bound isolation identity and a compare-and-swap generation before accepting worker output. Its non-authoritative recommendation selects the smallest viable topology: `iterative` for a tight test/refine loop, `distributed` for independent slices, or `adversarial` for high-uncertainty candidates that an independent oracle can falsify. Use `arena` for adversarial candidates, `swarm` for distributed coverage, and `autopilot` for a checked queue whose items each close their own proof loop.

Workers return typed cards with scope, proof, receipts, objections, reusable parts, verdict, and next frontier. Preserve those artifacts; discard transcript-shaped context.

Open dispatch for the pilot with `set-gate dispatch open --worker-limit 1`. After the pilot gate passes, raise the limit to the returned `worker_limit`. The durable state store enforces the cap over assigned units in `pending` or `running` state; blocked and completed units release their slots. Supply `--deadline <future-UTC-timestamp> --integration-reserve-minutes <n>` together to stop new assignments and reactivations at the derived cutoff while current assignments finish and record proof. If no budget is saved, dispatch without a deadline is unbounded; reopening preserves its saved budget unless `--clear-budget` is passed. Closing dispatch invalidates every issued assignment, including completed units: it advances each generation, clears its assignment, unit inbox, verification, and review, and resets it to pending. Reopening requires fresh assignment calls and fresh proof. This limit covers recorded assignments and does not measure or cap host processes. The plan checks declared ownership overlap but does not inspect future diffs, so the integration owner still compares each candidate's changed paths with its declared files before recording the head.

Do not use parallelism to hide an unclear contract. Resolve shared shapes and integration boundaries before fan-out.

## Integrate under one owner

The integration owner checks current heads, reconciles overlaps, runs integration proof, and obtains independent review. Worker success is input to integration, not proof of the combined result.

Writable fan-out remains gated until representative behavioral evaluations prove that isolation, aggregation, and serial fallback behave correctly on the active host.

Next: [Extend and evaluate](./08-extend-and-evaluate.md).
