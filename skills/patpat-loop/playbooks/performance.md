# Performance Playbook

Read [proof over proxy](../principles/proof-over-proxy.md), [fix root causes](../principles/fix-root-causes.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Define the user-visible metric, workload, environment, units, and acceptable target.
2. Capture a repeatable baseline and preserve the raw artifact.
3. Profile the authoritative surface and locate the dominant cost before editing.
4. Form competing causal hypotheses and run the cheapest discriminating probe.
5. Change one causal variable with the smallest safe patch.
6. Repeat the same workload and sampling policy; compare distribution and noise, not only one run.
7. Recheck correctness, resource tradeoffs, and the original user surface.
8. Run independent review and report baseline, result, artifacts, limitations, and rollback.
