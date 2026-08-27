# Multi-Phase Run Playbook

Read [sequence verifiable units](../principles/sequence-verifiable-units.md), [proof over proxy](../principles/proof-over-proxy.md), and [earned parallelism](../principles/earned-parallelism.md).

1. Initialize a run with objective, base revision, named authorities, prohibitions, and known working-tree boundaries.
2. Record the proof contract before entering `ACT`.
3. Transition only through the graph enforced by `run_state.py`.
4. Record evidence through an existing absolute file path; bind the receipt to its content digest.
5. Before a pause, validate the state, checkpoint the earliest resumable node, record the exact blocker and next proof action, and leave external authority unchanged.
6. On resume, validate state and invalidate claims that do not match the live revision.
7. Stop at `BLOCKED` after three failures from the same unchanged blocker.
8. Overnight or "don't stop" continues this graph until the completion predicate, then [default delivery](default-delivery.md), and stops merge-ready. Do not merge a green verified PR from this step. Merge only through [authorized delivery](authorized-delivery.md) after explicit land or merge language. Do not deploy from this step.
