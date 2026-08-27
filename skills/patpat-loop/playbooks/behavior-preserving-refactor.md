# Behavior-Preserving Refactor Playbook

Read [repository truth](../principles/repository-truth.md), [shape before logic](../principles/shape-before-logic.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Name the structure to change and the behavior that must remain invariant.
2. Capture characterization, contract, or equivalence evidence before editing.
3. Trace callers and generated or serialized forms that depend on the current shape.
4. Change structure in the smallest verifiable unit without adding behavior.
5. Re-run the same evidence after each unit and inspect the final diff.
6. Split any discovered behavior change into a separately authorized task.
