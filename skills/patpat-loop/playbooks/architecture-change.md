# Architecture Change Playbook

Read [repository truth](../principles/repository-truth.md), [shape before logic](../principles/shape-before-logic.md), [smallest safe change](../principles/smallest-safe-change.md), [preserve safety](../principles/preserve-safety.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Name the current contract, target contract, users, callers, and safety boundaries.
2. Inspect current architecture, data flow, ownership, failure modes, and migration constraints.
3. Redesign as if the requirement had been present from the start, then compare that shape with the smallest viable bolt-on. Choose the redesign when it removes dual paths, compatibility shims, or invalid states; keep a time-boxed dual path only for an external compatibility constraint.
4. Inventory callers of any replaced internal API. Plan to migrate them and delete the legacy surface in the same wave.
5. Choose one design and state rejected alternatives with evidence, including compatibility, reversibility, verification cost, and reader load.
6. Sequence the work into independently verifiable units with rollback points.
7. If implementation was explicitly requested, hand the authorized unit to `patpat-change`; otherwise stop after the design and verification plan.
8. Update the authoritative architecture or migration documentation when durable truth changed.
