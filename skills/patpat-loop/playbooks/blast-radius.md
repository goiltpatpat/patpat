# Blast Radius Playbook

Read [repository truth](../principles/repository-truth.md), [boundary discipline](../principles/boundary-discipline.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Name the changed symbol, behavior, data shape, or contract.
2. Trace direct callers and consumers, then cross wire, storage, lifecycle, generated, and operational boundaries as relevant.
3. Separate confirmed dependencies from name matches and hypotheses.
4. Identify one or two critical safety or compatibility invariants.
5. Prove each invariant through an executable check or authoritative surface when practical; otherwise mark it `unproven`.
6. Rank affected boundaries by severity and likelihood.
7. Recommend the smallest containment and the checks required after implementation.
8. Remain read-only and state what should not change.
