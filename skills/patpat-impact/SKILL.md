---
name: patpat-impact
description: Trace and prove the blast radius of an existing or proposed repository change. Use for downstream-regression questions, risky diffs, contract consumers, or claims that a small change is safe; remain read-only.
---

# Patpat Impact

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [boundary discipline](../patpat-loop/principles/boundary-discipline.md), and [proof over proxy](../patpat-loop/principles/proof-over-proxy.md). Apply the [blast-radius playbook](../patpat-loop/playbooks/blast-radius.md).

Trace callers, data flow, lifecycle boundaries, persistence, wire formats, generated artifacts, and operational consumers as relevant. Name one or two critical invariants and prove each through an executable check or real surface when practical. Mark an invariant `unproven` when evidence is unavailable.

Remain read-only. Report affected boundaries, evidence, severity, the smallest safe containment, and what not to change. Do not turn blast-radius analysis into architecture design or implementation.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
