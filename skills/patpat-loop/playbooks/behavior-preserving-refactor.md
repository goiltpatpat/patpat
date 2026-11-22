# Behavior-Preserving Refactor Playbook

Read repository truth, shape before logic, [sequence verifiable units](../principles/sequence-verifiable-units.md), and smallest safe change.

1. Name the structure to change and the behavior that must remain invariant.
2. Capture characterization, contract, or equivalence evidence and record the baseline executed test or assertion count before editing.
3. Trace callers and generated or serialized forms that depend on the current shape; after renames or moves, spot-check strings, config, and prose references that symbol tools miss.
4. Change structure in the smallest verifiable unit without adding behavior. For wide mechanical refactors (high call-site blast radius), switch to **expand → batched green migrate → contract** (add the new surface, migrate callers in verified green batches, then delete the legacy surface in the same wave). When adding characterization or seam tests, use vertical **tracer-bullet seams** (1-line catches/misses; 1 seam → 1 red test → 1 minimal green step), independent literal/spec expectations (no tautological tests), and SDK-style boundary mocks over generic fetchers.
5. Re-run the same evidence after each unit, confirm the executed test count did not silently drop, and inspect the final diff to verify the new structure lowers reader load.
6. Split any discovered behavior change into a separately authorized task.
