# Bounded Change Playbook

Read repository truth, shape before logic, smallest safe change, preserve safety, and [proof over proxy](../principles/proof-over-proxy.md).

1. Name the behavior, affected contract, and proof contract.
2. Inspect repository rules, current state, nearby implementation, callers, and focused tests.
   If a target may have changed since inspection, re-read its current contents before a write that could replace them. Reconcile the intended edit with intervening changes using an unambiguous target; do not guess from repeated text. Preserve both sets of changes when safe. Stop and report when the current contents cannot be read or the changes cannot be reconciled safely. A re-read alone is not an atomic write guarantee.
3. Identify the smallest safe change and its blast radius using the **Minimal Solution Ladder** (take the first rung that fully satisfies the contract):
   1. *Exist?* Skip unasked options, flags, or configurability; a vague request gets the smallest working core.
   2. *In repo?* Reuse existing helpers, components, or patterns the way surrounding code does.
   3. *Stdlib / platform?* Use built-in language/platform features unless the repo has its own canonical primitive.
   4. *Installed dep?* Reuse an installed dependency; never add a dependency for a few lines.
   5. *One clear line?* Use one readable line (a cryptic one-liner that needs decoding is not short).
   6. *Minimum complete code.*
   Be lazy about the solution, never about completeness: update every affected caller, test, fixture, and export, pick the edge-case-correct option on ties, and never cut trust-boundary validation, data-loss error handling, security, or accessibility. Mark any deliberate bounded shortcut in code as `shortcut: <limit>, <when to upgrade>`.
4. Implement one coherent patch without unrelated refactoring. When tests accompany behavior changes, use **TDD tracer-bullet seams**: pre-agree seams (1-line catches/misses), iterate vertically (1 seam → 1 red test → 1 minimal green implementation; skip horizontal all-tests-first batching), derive expected values from independent literals or specs (no tautological tests), and prefer SDK-style boundary mocks over generic fetchers. For wide mechanical refactors (high call-site blast radius), switch to **expand → batched green migrate → contract**.
5. Run targeted checks, then exercise the authoritative artifact or surface.
6. Audit the final diff for safety, regressions, generated noise, and unrequested scope.
7. Update durable documentation only when project truth changed.
8. Report changed files, evidence, and remaining risk.
