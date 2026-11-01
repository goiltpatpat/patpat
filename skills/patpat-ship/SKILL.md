---
name: patpat-ship
description: Commit and open or update a ready pull request after verified work when delivery intent exists, and merge only with explicit land or merge language. Use at the end of an active Patpat implementation and for explicit ship, land, merge, publish, or deploy requests.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"DESTRUCTIVE","target_entity":"PullRequest","requires_state":["delivery-review-cleared"],"produces_state":["delivery-pr-ready"],"verification_cmd":"python3 <loaded-skill-directory>/scripts/verify_delivery.py --root <workspace-root>"}'
---

# Patpat Ship

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full. Do not load the router.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md) and [proof over proxy](../patpat-loop/principles/proof-over-proxy.md).

After verify and review pass, require delivery intent: explicit commit, PR, or ship language; overnight or continuation; or explicit land or merge. Explicit `/patpat` activation alone is not delivery authority. Also require that no higher-priority repository rule forbids delivery. Then apply [default delivery](../patpat-loop/playbooks/default-delivery.md): commit the in-scope diff, use a non-force push, and open or update one ready pull request unless the user opted out or the path was read-only.

Apply [authorized delivery](../patpat-loop/playbooks/authorized-delivery.md) to merge, publish, or deploy. Only explicit `land` or `merge` language authorizes merge. Overnight, going to bed, or don't stop drives a verified pull request to merge-ready and stops. Do not land a real CI failure. Retry a flake once.

For CI monitoring or PR readiness work, use [PR Readiness Handoff](../patpat-loop/playbooks/pr-handoff.md). It is the canonical source for GitHub observation, native stack discovery, watcher budgets, stale handling, and authority boundaries.

Consume durable state when it exists. [Delivery proof](../patpat-run/references/delivery-proof.md) defines what binds a commit, which gate each delivered head uses, and how slices and whole programs differ. A failed gate stops delivery; a passed gate grants no authority.

Inspect version-control state, unrelated dirty files, and secrets before any git write. Workers never ship. Re-check the remote revision after the action.

Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification before continuing.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
