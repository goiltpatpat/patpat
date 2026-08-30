---
name: patpat-debug
description: Diagnose and fix a reproducible defect through root-cause evidence. Use for broken behavior, regressions, failing runtime paths, and unexplained mismatches when implementation is requested.
---

# Patpat Debug

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full. Do not load the router.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [fix root causes](../patpat-loop/principles/fix-root-causes.md), [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), and [preserve safety](../patpat-loop/principles/preserve-safety.md). Apply the [defect playbook](../patpat-loop/playbooks/defect.md). When the user requests test-first work or a cheap deterministic regression target exists, apply [regression first](../patpat-loop/playbooks/regression-first.md).

Reproduce before editing when safe and practical. Otherwise trace the contract or code path, or use an isolated non-harmful surrogate, and state that direct runtime proof is unavailable. Trace the earliest incorrect state instead of patching the last visible symptom.

If the user limited the request to diagnosis, stop after proving or bounding the root cause. Recommend the smallest patch without editing.

Change one causal variable at a time. Re-run the original reproduction when it remains safe and practical; otherwise run the predeclared non-triggering check and state the missing runtime proof. Never label an unobserved fix as verified.

When the defect is a mismatch against a reference image or migrated UI, apply the [visual equivalence playbook](../patpat-loop/playbooks/visual-equivalence.md) after reproducing the defect. Preserve the pre-edit reference and comparison harness.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
