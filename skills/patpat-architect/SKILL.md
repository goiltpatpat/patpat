---
name: patpat-architect
description: Design a repository-native change before implementation. Use for architecture, migrations, public contracts, security-sensitive boundaries, cross-cutting work, or decisions with meaningful compatibility risk.
---

# Patpat Architect

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), and [preserve safety](../patpat-loop/principles/preserve-safety.md). Apply the [architecture change playbook](../patpat-loop/playbooks/architecture-change.md).

Ground the design in current repository evidence. Name the contract, its callers, the changed behavior, migration impact, compatibility risk, rollback path, and proof contract.

Prefer a design that reduces degrees of freedom and reuses repository structure. Seek independent review before implementing auth, billing, permissions, destructive migrations, production infrastructure, or public contract changes. Stop for explicit approval when required.

Keep architecture work read-only by default. Do not edit implementation files. When the user also requested implementation, finish the design gate and hand the authorized unit to `patpat-change` under `patpat-loop` instead of implementing inside this workflow.

When an observable experiment can settle a design fork, apply the [prototype playbook](../patpat-loop/playbooks/prototype.md). Keep prototypes in an isolated scratch area outside production paths and treat them as disposable evidence, not implementation.

Produce a concise sequence in this form:

```text
1. <step> -> verify: <targeted check or observation>
2. <step> -> verify: <targeted check or observation>
```

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
