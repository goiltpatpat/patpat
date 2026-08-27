# Metric Hillclimb Playbook

Read [proof over proxy](../principles/proof-over-proxy.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Freeze the metric definition, representative workload, environment, target, stop predicate, and cleanup before changing code.
2. Measure enough baseline samples to identify variance and the minimum meaningful improvement.
3. Record one falsifiable hypothesis and change one causal variable.
4. Re-run the same harness. Keep the change only when the improvement clears the noise floor without violating correctness or safety guardrails; otherwise revert the attempt.
5. Use `patpat-run record --kind experiment` to store the hypothesis, metric value and unit, content-bound measurement receipt, keep-or-revert verdict, snapshot, actor, and next decision. Preserve every experiment receipt until the run closes; stale historical evidence invalidates the run history.
6. Pivot after repeated evidence rejects one mechanism. Stop at the target, a measured plateau, exhausted safe hypotheses, or the run engine's blocker threshold.
7. Re-run the full representative verification surface against the final retained state and report rejected as well as accepted attempts.
