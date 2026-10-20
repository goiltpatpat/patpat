---
name: patpat-ship
description: Commit and open or update a ready pull request after verified work when delivery intent exists, and merge only with explicit land or merge language. Use at the end of an active Patpat implementation and for explicit ship, land, merge, publish, or deploy requests.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"DESTRUCTIVE","target_entity":"PullRequest","requires_state":[],"produces_state":[],"verification_cmd":""}'
---

# Patpat Ship

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full. Do not load the router.

Read [preserve safety](../patpat-loop/principles/preserve-safety.md), [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and the [operating protocol](../patpat-loop/references/operating-protocol.md).

After verify and review pass, require delivery intent: explicit commit, PR, or ship language; overnight or continuation; or explicit land or merge. Explicit `/patpat` activation alone is not delivery authority. Also require that no higher-priority repository rule forbids delivery. Then apply [default delivery](../patpat-loop/playbooks/default-delivery.md): commit the in-scope diff, use a non-force push, and open or update one ready pull request unless the user opted out or the path was read-only.

Apply [authorized delivery](../patpat-loop/playbooks/authorized-delivery.md) to merge, publish, or deploy. Only explicit `land` or `merge` language authorizes merge. Overnight, going to bed, or don't stop drives a verified pull request to merge-ready and stops. Do not land a real CI failure. Retry a flake once.

For `watch CI`, `keep the PR moving`, `get it green`, or work toward merge-ready status, use [PR Readiness Handoff](../patpat-loop/playbooks/pr-handoff.md). On GitHub.com, `check` captures one bounded read-only observation with [`scripts/github_observe.py`](scripts/github_observe.py), then evaluates it with [`scripts/pr_watch.py`](scripts/pr_watch.py). `drive` uses [`scripts/watch_pr.py`](scripts/watch_pr.py) to repeat those same operations within an explicit deadline, attempt budget, and poll interval. For an explicitly supplied linear PR stack, use [`scripts/watch_pr_stack.py`](scripts/watch_pr_stack.py) with a frozen schema-v2 manifest and the same bounded budgets; each entry binds an expected base branch and full base commit SHA, and each later base SHA must equal the previous PR's head. For open PRs, the watcher compares GitHub's live `baseRef.target.oid`; for merged PRs, it compares the PR-associated `baseRefOid`. It advances only after GitHub reports the prior PR merged and never merges or restacks. Schema-v1 manifests must be rebound after confirming current topology. This checks the declared parent binding against the live branch while open and the PR-associated base snapshot after merge; it does not independently prove merge ancestry or discover stacks. Keep expected repository, pull request, head, base, base SHA, and required checks explicit. Source required checks from the repository's verified branch policy or CI contract. An empty required-check set remains blocked, including when the legacy `--allow-no-required-checks` flag is present, because the current observation does not bind provider policy evidence. A `stale` verdict stops the watch; rebind only after confirming the current head and base SHA. `blocked` stops with a diagnosis, and `ready` stops at merge-ready. No watcher grants delivery authority or mutates the provider.

Inspect version-control state, unrelated dirty files, and secrets before any git write. Workers never ship. Re-check the remote revision after the action.

Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification before continuing.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
