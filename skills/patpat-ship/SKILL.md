---
name: patpat-ship
description: Commit and open or update a ready pull request after verified work when Patpat was explicitly activated, and merge only with explicit land or merge language. Use at the end of an active Patpat implementation and for explicit ship, land, merge, publish, or deploy requests.
---

# Patpat Ship

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and the [operating protocol](../patpat-loop/references/operating-protocol.md).

After verify and review pass, require delivery authority from one of these sources: the current request explicitly activated Patpat, a trusted active-session receipt proves earlier explicit activation, or the user explicitly requested the named commit, push, or pull-request action. Also require that no higher-priority repository rule forbids delivery. Then apply [default delivery](../patpat-loop/playbooks/default-delivery.md): commit the in-scope diff, use a non-force push, and open or update one ready pull request unless the user opted out or the path was read-only.

Apply [authorized delivery](../patpat-loop/playbooks/authorized-delivery.md) to merge, publish, or deploy. Only explicit `land` or `merge` language authorizes merge. Overnight, going to bed, or don't stop drives a verified pull request to merge-ready and stops. Do not land a real CI failure. Retry a flake once.

For `watch CI`, `babysit`, `get it green`, or unattended merge-ready work, use [PR babysit](../patpat-loop/playbooks/pr-babysit.md). Have the host adapter capture one immutable observation, then evaluate it with [`scripts/pr_watch.py`](scripts/pr_watch.py). Rebind on `stale`, reobserve on `pending`, stop and diagnose on `blocked`, and stop merge-ready on `ready`. The evaluator never grants delivery authority and never mutates the provider.

Inspect version-control state, unrelated dirty files, and secrets before any git write. Workers never ship. Re-check the remote revision after the action.

Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification before continuing.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
