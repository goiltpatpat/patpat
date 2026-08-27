# Independent Review Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), and [preserve safety](../principles/preserve-safety.md).

1. Freeze the objective, proof contract, exact diff or artifact, and raw verification receipts.
2. Use a separate read-only reviewer for high-risk work when delegation is available and authorized; omit the intended conclusion.
3. Trace changed contracts, callers, side effects, and safety boundaries.
4. Try to falsify the implementation and each proof claim.
5. Report evidence-backed findings by severity and discard speculative style noise.
6. Require the smallest correction and named re-verification for accepted findings.
7. Inspect the corrected artifact rather than accepting a remediation summary.
8. State residual gaps; review never authorizes delivery.
