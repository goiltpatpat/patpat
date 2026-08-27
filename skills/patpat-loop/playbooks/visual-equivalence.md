# Visual Equivalence Playbook

Read [proof over proxy](../principles/proof-over-proxy.md), [preserve safety](../principles/preserve-safety.md), and [boundary discipline](../principles/boundary-discipline.md).

1. Capture the immutable baseline before editing, including route, state, viewport, theme, data, fonts, motion state, and environment.
2. Define allowed differences and the machine-readable comparison method. Require a pixel or image diff for a pixel-equivalence claim; use structural signals only for an explicitly structural-layout claim. Do not weaken the baseline, mask regions, or change thresholds after seeing the candidate.
3. Reproduce the same state through the real interface and capture the candidate with the same conditions.
4. Compare pixels or stable structural signals, then inspect material mismatches rather than accepting one aggregate score.
5. Verify interaction, responsive behavior, and accessibility separately; visual equivalence cannot prove them.
6. Preserve baseline and candidate receipts, clean up verifier-owned artifacts, and report tool or environment limitations.
