---
name: patpat-verify
description: Prove an implementation or repository claim against its authoritative artifact or user surface. Use after code changes, during acceptance checks, or whenever tests and builds are insufficient evidence of real behavior.
---

# Patpat Verify

For a bounded local proof, use this skill and its relevant references. Read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full for uncertainty, security, auth, billing, secrets, architecture, cross-cutting work, or delivery intent. Do not load the router or reread unchanged instructions already loaded in this session.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md) and [preserve safety](../patpat-loop/principles/preserve-safety.md).

## Build the proof

1. Reconcile the requested outcomes with the proof contract using proof over proxy; name missing requirements before running checks.
2. Identify the authoritative artifact or user surface.
3. Capture a baseline or reproduce the prior state when relevant.
4. Run the smallest targeted automated check.
5. For behavioral claims, exercise the changed logic through the authoritative interface under representative conditions when safe and practical. For static claims, use the strongest deterministic check on the authoritative artifact.
6. Observe visible output and material side effects directly.
7. Inspect the final diff and version-control state for unrelated changes.
8. Record the command or action, observed result, cleanup, and limitation for each material claim; do not mark the whole request verified with uncovered outcomes.

## Claim-adaptive verification and proxy rejection

Match verification depth to the claim and risk:

- **Behavioral claims**: Vary material inputs, relevant error branches, or state transitions when safe and practical. Static contract checks may support the result but do not alone prove runtime behavior.
- **Static claims**: Use deterministic structure, schema, type, or content checks when that is the authoritative surface. Do not manufacture runtime theater for a non-runtime claim.
- **Proxy evidence**: Fixtures and mocks may isolate a contract, but they do not replace the real system when the claim concerns that system. Reject narrative summaries, hardcoded fixture answers, and clean compilation as sole behavioral proof.
- **Fresh binding**: Bind evidence to the exact candidate revision or a reproducible working-tree snapshot, plus material inputs, environment, and oracle. Require the committed head for commit-, push-, PR-, or delivery-bound claims. Reject stale, cached, or transferred logs.

Do not accept an implementing agent's report as evidence. Inspect the artifact and results directly. For high-risk boundaries, obtain an independent review without leaking the intended conclusion.

Classify the outcome using exactly one label:

- `verified`: The claimed behavior was observed on the authoritative surface and relevant checks passed.
- `partially verified`: Some required evidence passed, but a named surface or condition could not be checked.
- `implemented but not verified`: The change exists, but no meaningful behavioral proof ran.
- `not implemented`: No implementation change was made.

If a check fails, classify the failure before retrying. Change the hypothesis, implementation, verifier, or environment; never loop the same attempt.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
