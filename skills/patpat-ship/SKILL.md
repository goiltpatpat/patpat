---
name: patpat-ship
description: Commit and open a ready pull request after verified mutating work, and merge, publish, or deploy only with land language or overnight intent. Use at the end of implementation and for explicit ship, land, merge, publish, or deploy requests.
---

# Patpat Ship

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and the [operating protocol](../patpat-loop/references/operating-protocol.md).

After verify and review pass, apply [default delivery](../patpat-loop/playbooks/default-delivery.md): commit the in-scope diff and open a ready pull request unless the user opted out or the path was read-only.

Apply [authorized delivery](../patpat-loop/playbooks/authorized-delivery.md) to merge, publish, or deploy. Overnight, going to bed, don't stop, land this, merge this, or ship it merges a green verified PR. Do not land a real CI failure. Retry a flake once.

Inspect version-control state, unrelated dirty files, and secrets before any git write. Workers never ship. Re-check the remote revision after the action.

Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification before continuing.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
