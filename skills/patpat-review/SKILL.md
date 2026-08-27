---
name: patpat-review
description: Independently challenge an implementation, diff, or verification claim without editing. Use after meaningful changes, for explicit code review, or when high-risk evidence needs a separate skeptical pass.
---

# Patpat Review

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and [preserve safety](../patpat-loop/principles/preserve-safety.md). Apply the [independent review playbook](../patpat-loop/playbooks/independent-review.md).

Remain read-only. Inspect the objective, proof contract, exact diff or artifact, raw verification receipts, and affected contracts. When an independent reviewer is available and authorized, give it the evidence without the implementer's intended conclusion.

Report findings first, ordered by `blocker`, `high`, `medium`, then `low`. Tie every finding to a file, symbol, behavior, or receipt and explain the concrete impact. Exclude speculative style preferences. For each accepted issue, recommend the smallest safe correction and required re-verification.

State `no findings` only after checking correctness, regressions, contracts, safety, performance implications, side effects, generated noise, and evidence mismatch. Review does not replace verification and never authorizes merge or delivery.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
