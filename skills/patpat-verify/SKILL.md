---
name: patpat-verify
description: Prove an implementation or repository claim against its authoritative artifact or user surface. Use after code changes, during acceptance checks, or whenever tests and builds are insufficient evidence of real behavior.
---

# Patpat Verify

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md) and [preserve safety](../patpat-loop/principles/preserve-safety.md).

## Build the proof

1. Name the exact claim.
2. Identify the authoritative artifact or user surface.
3. Capture a baseline or reproduce the prior state when relevant.
4. Run the smallest targeted automated check.
5. Exercise the changed behavior through the real interface when practical.
6. Observe visible output and material side effects.
7. Inspect the final diff and version-control state for unrelated changes.
8. Record the command or action, observed result, cleanup, and limitation.

Do not accept an implementing agent's report as evidence. Inspect the artifact and results directly. For high-risk boundaries, obtain an independent review without leaking the intended conclusion.

Classify the outcome using exactly one label:

- `verified`: The claimed behavior was observed on the authoritative surface and relevant checks passed.
- `partially verified`: Some required evidence passed, but a named surface or condition could not be checked.
- `implemented but not verified`: The change exists, but no meaningful behavioral proof ran.
- `not implemented`: No implementation change was made.

If a check fails, classify the failure before retrying. Change the hypothesis, implementation, verifier, or environment; never loop the same attempt.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
