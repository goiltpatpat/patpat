# Architecture Change Playbook

Read [repository truth](../principles/repository-truth.md), [shape before logic](../principles/shape-before-logic.md), [smallest safe change](../principles/smallest-safe-change.md), [preserve safety](../principles/preserve-safety.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Name the current contract, target contract, users, callers, and safety boundaries.
2. Inspect current architecture, data flow, ownership, failure modes, and migration constraints.
3. For a material architecture decision or a change that crosses a meaningful boundary, write a compact design sketch from caller usage through that boundary. Include the core data or type shape, boundary signatures, failure modes, rejected alternatives, and the proof that will preserve the chosen shape. Keep smaller local changes on the bounded-change path.
4. Redesign as if the requirement had been present from the start, then compare that shape with the smallest viable bolt-on. When helpful, compare current vs target as a compact structural representation per [earned representation](../references/earned-representation.md). Choose the redesign when it removes dual paths, compatibility shims, or invalid states; keep a time-boxed dual path only for an external compatibility constraint.
5. Inventory callers of any replaced internal API. Plan to migrate them and delete the legacy surface in the same wave.
6. If a design fork remains after repository evidence, compare 2–3 candidates. Use [arena](arena.md) only when earned-parallelism isolation is available; otherwise compare serially and record the missing parallelism evidence.
7. Choose one design and state rejected alternatives with evidence, including compatibility, reversibility, verification cost, and reader load.
8. Sequence the work into independently verifiable units with rollback points. If implementation of the material boundary needs a parameter, state, escape hatch, or compatibility path absent from the chosen sketch, return to the design step before adding a workaround.
9. If implementation was explicitly requested, hand the authorized unit to `patpat-change`; otherwise stop after the design and verification plan.
10. Update the authoritative architecture or migration documentation when durable truth changed.
