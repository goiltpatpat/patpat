# Bounded Change Playbook

Read [repository truth](../principles/repository-truth.md), [shape before logic](../principles/shape-before-logic.md), [smallest safe change](../principles/smallest-safe-change.md), [preserve safety](../principles/preserve-safety.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Name the behavior, affected contract, and proof contract.
2. Inspect repository rules, current state, nearby implementation, callers, and focused tests.
   If a target may have changed since inspection, re-read its current contents before a write that could replace them. Reconcile the intended edit with intervening changes using an unambiguous target; do not guess from repeated text. Preserve both sets of changes when safe. Stop and report when the current contents cannot be read or the changes cannot be reconciled safely. A re-read alone is not an atomic write guarantee.
3. Identify the smallest safe change and its blast radius.
4. Implement one coherent patch without unrelated refactoring.
5. Run targeted checks, then exercise the authoritative artifact or surface.
6. Audit the final diff for safety, regressions, generated noise, and unrequested scope.
7. Update durable documentation only when project truth changed.
8. Report changed files, evidence, and remaining risk.
