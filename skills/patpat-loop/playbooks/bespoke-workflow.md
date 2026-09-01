# Bespoke Workflow Playbook

Read [repository truth](../principles/repository-truth.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), and [preserve safety](../principles/preserve-safety.md).

1. Define one falsifiable completion predicate and the authoritative surfaces that prove it.
2. Inspect the contracts, dependencies, current state, and irreversible boundaries.
3. Split work into the fewest units that can independently return to a verified state.
4. Give each unit an input, owner, allowed mutations, proof contract, rollback, and stop condition.
5. Order units by dependency and risk; expose uncertainty before expensive implementation.
6. Identify approval gates and work that must remain serial.
7. Hand the first unit to the narrowest existing workflow or initialize `patpat-run`. Units that enter `patpat-run` record keep/revert checkpoints on the human decision trail; INCONCLUSIVE is not a pass.
8. Keep this design read-only and report unresolved facts explicitly.
