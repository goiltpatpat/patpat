# Regression-First Playbook

Read [fix root causes](../principles/fix-root-causes.md), [proof over proxy](../principles/proof-over-proxy.md), and [smallest safe change](../principles/smallest-safe-change.md).

Apply this playbook when the user requests test-first work or a cheap deterministic regression target already exists.

1. Reproduce the defect on the authoritative surface when safe and practical. Otherwise trace the contract or code path, or use an isolated non-harmful surrogate, and record the missing runtime proof.
2. Add or select the narrowest test that fails for the intended causal reason. Prefer the closest executable check over a bad new test.
3. Observe the failure before any production edit. Confirm it is not setup noise, an unrelated assertion, or a false positive.
4. Do not silently skip: if fail-before cannot be observed, record an explicit why-not and the closest executable check.
5. Implement the root-cause patch. Do not change tests to match a wrong implementation.
6. Confirm the focused test passes, then rerun the original reproduction when it remains safe and practical. Otherwise run the predeclared non-triggering check and keep the result partially verified.
7. Report fail-before and pass-after on the same check.
8. Keep broad harness work out of the patch; when a stable local test is impractical, use the closest executable check and state why.
