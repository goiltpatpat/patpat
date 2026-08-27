# Defect Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), [smallest safe change](../principles/smallest-safe-change.md), and [preserve safety](../principles/preserve-safety.md).

1. Reproduce the symptom on the same surface and capture the baseline.
2. Trace the failing path until evidence identifies the earliest incorrect state.
3. State the root-cause hypothesis and a falsifying observation.
4. Stop and recommend the smallest patch when the request is diagnosis-only.
5. Apply the smallest fix at the responsible boundary when implementation is authorized.
6. Re-run the original reproduction and a focused regression check.
7. Inspect side effects and the final diff.
8. Report root cause, changed files, before-and-after evidence, and residual uncertainty.

If reproduction is impossible, record why and label the result partially verified. Do not call a plausible patch fixed.
