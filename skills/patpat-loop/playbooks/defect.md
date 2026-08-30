# Defect Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), [smallest safe change](../principles/smallest-safe-change.md), and [preserve safety](../principles/preserve-safety.md).

1. Reproduce the symptom on the same surface and capture the baseline when safe and practical. Otherwise trace the contract or code path, or use an isolated non-harmful surrogate, and record the missing runtime proof.
2. Trace the failing path until evidence identifies the earliest incorrect state.
3. State the root-cause hypothesis and a falsifying observation.
4. Stop and recommend the smallest patch when the request is diagnosis-only.
5. Apply the smallest fix at the responsible boundary when implementation is authorized. Change one causal variable at a time.
6. When a failed hypothesis materially changes the next decision, preserve one bounded, redacted negative-evidence entry before pivoting: the hypothesis, falsifying observation, objection, reusable constraint, and an inspectable receipt or path when available. Do not copy raw logs, secrets, or trivial retry history into durable state or reports.
7. Re-run the original reproduction when it remains safe and practical; otherwise run the predeclared non-triggering check. Run a focused regression check in either case.
8. Inspect side effects and the final diff.
9. Report root cause, changed files, before-and-after evidence, material failed hypotheses that affect the conclusion, and residual uncertainty.

If direct reproduction is unsafe or impossible, record why and label the result partially verified. Do not call a plausible patch fixed.
