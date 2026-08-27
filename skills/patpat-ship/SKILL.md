---
name: patpat-ship
description: Assess and execute an explicitly requested delivery step after direct verification. Use for commit, pull request, publish, release, merge, deployment, or overnight land requests; do not trigger for ordinary implementation completion.
---

# Patpat Ship

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), the [operating protocol](../patpat-loop/references/operating-protocol.md), and the [authorized delivery playbook](../patpat-loop/playbooks/authorized-delivery.md). Require current evidence from [`patpat-verify`](../patpat-verify/SKILL.md) and an independent pass through [`patpat-review`](../patpat-review/SKILL.md).

Treat delivery as a separate authorization boundary. The current user request must name the action. `/patpat land this PR` or `going to bed, commit and open the PR` is enough for that named ordinary action after checks pass.

Inspect version-control state, staged diff, generated files, secrets, and unrelated work. When authorized, perform only the requested delivery step and re-check the delivered artifact or remote state directly. Green checks do not authorize auto-merge.

Obtain fresh confirmation immediately before production deployment, package or release publication, merge onto a protected default, destructive migration, force push, secret rotation, or risky auth, billing, and permission changes. Explain blast radius, rollback, and verification before requesting approval.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
