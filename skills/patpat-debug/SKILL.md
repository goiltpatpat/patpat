---
name: patpat-debug
description: Diagnose and fix a reproducible defect through root-cause evidence. Use for broken behavior, regressions, failing runtime paths, and unexplained mismatches when implementation is requested.
---

# Patpat Debug

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [fix root causes](../patpat-loop/principles/fix-root-causes.md), [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), and [preserve safety](../patpat-loop/principles/preserve-safety.md). Apply the [defect playbook](../patpat-loop/playbooks/defect.md). When the user requests test-first work or a cheap deterministic regression target exists, apply [regression first](../patpat-loop/playbooks/regression-first.md).

Reproduce before editing. If reproduction is blocked, gather the strongest available evidence and state the limitation. Trace the earliest incorrect state instead of patching the last visible symptom.

If the user limited the request to diagnosis, stop after proving or bounding the root cause. Recommend the smallest patch without editing.

Change one causal variable at a time and re-run the original reproduction after the patch. Never label an unobserved fix as verified.

When the defect is a mismatch against a reference image or migrated UI, apply the [visual equivalence playbook](../patpat-loop/playbooks/visual-equivalence.md) after reproducing the defect. Preserve the pre-edit reference and comparison harness.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
