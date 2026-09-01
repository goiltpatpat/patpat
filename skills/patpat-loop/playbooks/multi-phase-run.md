# Multi-Phase Run Playbook

Read [sequence verifiable units](../principles/sequence-verifiable-units.md), [proof over proxy](../principles/proof-over-proxy.md), and [earned parallelism](../principles/earned-parallelism.md).

1. Initialize a run with objective, base revision, named authorities, prohibitions, and known working-tree boundaries.
2. For a multi-PR queue or stack, validate the per-unit dependency and proof contract with `patpat-run/scripts/validate_plan.py` before fan-out or implementation. Record the ordinary proof contract before entering `ACT`.
3. Transition only through the graph enforced by `run_state.py`.
4. Record evidence through an existing absolute file path; bind the receipt to its content digest. Append one human decision-trail row per unit checkpoint to `<git patpat/runs>/<run-id>/decisions.tsv`; INCONCLUSIVE is not a pass.
5. Before a pause, validate the state, checkpoint the earliest resumable node, record the exact blocker and next proof action, and leave external authority unchanged.
6. On resume, validate state and invalidate claims that do not match the live revision.
7. Stop at `BLOCKED` after three failures from the same unchanged blocker.
8. Overnight or "don't stop" continues this graph until the completion predicate, then applies [default delivery](default-delivery.md) when Patpat delivery authority exists and drives the pull request to merge-ready. It does not authorize merge. Merge only through [authorized delivery](authorized-delivery.md) after explicit `land` or `merge` language. Do not deploy from this step.
