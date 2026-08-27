---
name: patpat-ship
description: Assess and execute an explicitly requested delivery step after direct verification. Use for commit, pull request, publish, release, or deployment requests; do not trigger for ordinary implementation completion.
---

# Patpat Ship

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and [earned parallelism](../patpat-loop/principles/earned-parallelism.md). Require current evidence from [`patpat-verify`](../patpat-verify/SKILL.md) and an independent pass through [`patpat-review`](../patpat-review/SKILL.md).

Treat delivery as a separate authorization boundary. Confirm the user explicitly requested the exact action. Require current `patpat-verify` evidence. Inspect version-control state, staged diff, generated files, secrets, and unrelated work. Obtain an independent review for high-risk boundaries.

Do not commit, push, open a pull request, publish, release, merge, or deploy by implication. An explicit request authorizes the named ordinary commit, push, or pull-request action after checks pass. Obtain fresh confirmation immediately before production deployment, package or release publication, merge, destructive migration, force push, secret rotation, or risky auth, billing, and permission changes. Explain blast radius, rollback, and verification before requesting approval.

When authorized, perform only the requested delivery step. Re-check the delivered artifact or remote state directly. Report the exact revision, target, checks, and remaining risk. Green checks do not authorize auto-merge.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
