---
name: patpat-perf
description: Diagnose a resource regression or drive sustained numeric optimization against a measurable target. Use for latency, CPU, memory, throughput, startup, or other performance implementation when comparable before-and-after measurement is practical.
---

# Patpat Performance

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [fix root causes](../patpat-loop/principles/fix-root-causes.md), and [smallest safe change](../patpat-loop/principles/smallest-safe-change.md). Apply the [performance playbook](../patpat-loop/playbooks/performance.md).

Measure the reported surface before reading toward a preferred cause. Keep workload, environment, warm-up, sample policy, and units comparable. Locate the dominant cost, change one causal variable, and preserve correctness and safety invariants.

When the objective requires sustained improvement toward a numeric target rather than one regression fix, apply the [metric hillclimb playbook](../patpat-loop/playbooks/metric-hillclimb.md) through `patpat-run`.

Report the baseline, post-change result, measurement noise, artifact locations, and remaining tradeoffs. Do not claim improvement from a single incomparable or proxy measurement.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
