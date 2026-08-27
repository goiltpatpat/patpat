# Regression-First Playbook

Read [fix root causes](../principles/fix-root-causes.md), [proof over proxy](../principles/proof-over-proxy.md), and [smallest safe change](../principles/smallest-safe-change.md).

Apply this playbook when the user requests test-first work or a cheap deterministic regression target already exists.

1. Reproduce the defect on the authoritative surface.
2. Add or select the narrowest test that fails for the intended causal reason.
3. Confirm the failure is not setup noise, an unrelated assertion, or a false positive.
4. Implement the root-cause patch without weakening the test.
5. Confirm the focused test passes, then rerun the original reproduction.
6. Keep broad harness work out of the patch; when a stable local test is impractical, use the closest executable check and state why.
