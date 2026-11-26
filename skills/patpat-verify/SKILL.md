---
name: patpat-verify
description: Prove an implementation or repository claim against its authoritative artifact or user surface.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"Codebase","requires_state":["workspace-root-open"],"produces_state":["acceptance-verified"],"verification_cmd":"git diff --check"}'
---

# Patpat Verify

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

For a bounded local proof, use this skill and its references; read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full for uncertainty, security, auth, billing, secrets, architecture, cross-cutting work, or delivery intent without loading the router. Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md) and preserve safety.

## The Iron Law of Verification

```text
NO COMPLETION CLAIMS WITHOUT FRESH, CANDIDATE-BOUND EVIDENCE
```

Execute the authoritative check in the current turn. Inside a durable `patpat-run`, reuse prior evidence only when `patpat-run check-gate` passes for that gate (proving freshness for the current candidate, proof contract, evidence epoch, and snapshot/tree) and always report reused evidence as reused. Bind ignored files, external inputs, and process/dependency state separately or rerun.

### The 5-Step Gate Function

1. **IDENTIFY**: Name the authoritative command or check proving the claim.
2. **RUN**: Execute freshly on the authoritative surface, or validate a durable-run receipt against the current candidate and bindings.
3. **READ**: Inspect raw stdout, stderr, and exit code directly (or the reused receipt's bound evidence and validator output), masking any tokens/secrets.
4. **VERIFY**: Confirm observed output strictly satisfies the expected criteria.
5. **ONLY THEN**: Make the claim and attach raw evidence.

## Build the proof

1. Reconcile requested outcomes with the proof contract via [proof over proxy](../patpat-loop/principles/proof-over-proxy.md); name gaps before running checks.
2. Identify the authoritative artifact or user surface and capture a baseline/repro when relevant.
3. Run the smallest targeted automated check; isolate live servers, browsers, or databases per [runtime isolation](references/verification-standards.md#runtime-isolation).
4. When a broader suite runs, classify failures as `pre-existing` (same test and signature on pinned base SHA in a clean temporary worktree removed via `git worktree remove`, or—outside Git—against an unmodified pre-edit snapshot in a clean temp directory), `new`, or `unclassified` per [broader-suite failure classification](references/verification-standards.md#broader-suite-failure-classification). Any `new` or `unclassified` failure blocks `verified`.
5. Exercise changed behavioral logic through the authoritative interface under representative conditions (or run the strongest deterministic check for static claims) using a concrete observable oracle—never mock counts, copied constants, or self-referential expected values.
6. Observe visible output and material side effects directly, and inspect the final diff and VCS status (or pre/post snapshot diff and SHA-256 manifest in non-Git workspaces) for unrelated changes.
7. Record command/action, observed result, cleanup, and limitations per material claim; never mark uncovered outcomes `verified`.

## Claim-adaptive verification and outcomes

Apply claim-adaptive depth, mutation-resilience checks, proxy rejection, and committed-head fresh binding per [claim-adaptive verification](references/verification-standards.md#claim-adaptive-verification-and-fresh-binding). Inspect artifacts directly rather than trusting an implementing agent's summary.

Classify the outcome with exactly one label:

- `verified`: Claimed behavior observed on the authoritative surface and required checks passed.
- `partially verified`: Some required evidence passed, with a named unchecked surface or condition.
- `implemented but not verified`: Change exists without meaningful behavioral proof.
- `not implemented`: No implementation change made.

On failure, classify the failure and change hypothesis, implementation, verifier, or environment before retrying.

## Proof contract runner

Run [`scripts/eval_proof_contract.py`](scripts/eval_proof_contract.py) to execute 5-field proof contracts (`Claim`, `Surface`, `Action`, `Expect`, `Cleanup`) deterministically with guaranteed cleanup and `patpat-proof-receipt/v1` JSON output.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
