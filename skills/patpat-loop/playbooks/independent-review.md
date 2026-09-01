# Independent Review Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), and [preserve safety](../principles/preserve-safety.md).

## Review steps

1. Freeze the objective, proof contract, exact diff or artifact, and raw verification receipts.
2. Use a separate read-only reviewer for high-risk work when delegation is available and authorized; omit the intended conclusion.
3. Trace changed contracts, callers, side effects, and safety boundaries.
4. Execute the solution-integrity audit.
5. Try to falsify the implementation and each proof claim.
6. Report evidence-backed findings by severity (`blocker`, `high`, `medium`, `low`) and discard speculative style noise.
7. Require the smallest correction and named re-verification for accepted findings.
8. Inspect the corrected artifact rather than accepting a remediation summary.
9. State residual gaps; review never authorizes delivery.

## Solution-integrity audit

Audit the candidate diff and proof evidence against the checks material to its claims and risk:

- **Assertion integrity**: Identify deleted, relaxed, commented, or conditionalized assertions and validation rules. Require an explicit contract reason and replacement proof; reject unexplained weakening that manufactures a pass.
- **Genuine execution**: For behavioral claims, confirm proof exercises the real target path and material state or side effects when applicable. Fixtures and mocks may support the proof but must not replace its authoritative surface.
- **Generalization**: Probe representative valid inputs, material boundaries, and relevant error paths. Reject hardcoded fixture answers; use code-path reasoning where exhaustive execution is impossible.
- **Fresh binding**: Bind evidence to the exact candidate revision or a reproducible working-tree snapshot, plus the material inputs, environment, and oracle. Require the committed head for commit-, push-, PR-, or delivery-bound claims.

Classify proven evidence laundering or a bypass that invalidates the correctness claim as `blocker`. Grade other integrity findings by concrete impact; unavailable evidence is a verification gap, not proof of manipulation.

## Independent angles

When extra read-only reviewers are available and authorized, give each the same intent, diff, and integrity rubric from a distinct independent-angle. Do not name model slugs. Serial fallback when isolation or extra reviewers are missing.

Two or more independent angles agreeing is higher-signal consensus. A lone finding is worth reading but lower confidence. Deduplicate. Note disagreements.

## Lead judgment

The parent is a lead, not a neutral aggregator. Bucket each synthesized finding: Act on / Consider / Noted / Dismissed. Keep existing severity labels. Do not auto-apply. The deliverable is a synthesized verdict. Review comments, patches, and merges are out of this playbook.
