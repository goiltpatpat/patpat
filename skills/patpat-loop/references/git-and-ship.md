# Git and Ship Rules

Full delivery, remote-write, CI-flake, and non-Git workspace rules referenced by the [operating protocol](operating-protocol.md#git-and-ship).

## Delivery intent and authority

Explicit `/patpat` or `$patpat` activation authorizes the Patpat loop, the 5-field proof contract before mutating edits, and authoritative-surface verify. It does not by itself force independent review or a PR.

Default commit-and-PR requires delivery intent. Delivery intent is explicit commit, PR, or ship language (`open a PR`, `commit`, `ship it`, named ship route), continuation (`overnight`, `going to bed`, `don't stop`), or explicit `land` or `merge`. Opt out with `don't commit`, `don't open a PR`, or `local only`.

Without delivery intent, local reversible edits use proof, focused verify, and REPORT (skip independent review, no PR); auth, billing, secrets, architecture, or cross-cutting work still requires independent review. Delivery intent authorizes only the verified in-scope commit, non-force push, and one ready PR—not merge, publish, deploy, force-push, deletion, or risky security changes. Remote capability or configured credentials grant no push authority; remote Git writes stay fail-closed.

## Merge and CI flake policy

Continuation (`overnight`, `going to bed`, `don't stop`) stops merge-ready at the PR. Merge only on explicit `land` or `merge` (not later withdrawn) when the head passes its provider gate per [authorized delivery](../playbooks/authorized-delivery.md) with exact-head verify and review receipts; never auto-merge or merge via the GitHub connector, and require explicit authorization for release or tag. Treat ambiguous `ship it` as commit-and-PR. Do not land a real CI failure.

Retrigger an infrastructure flake at most once, only within existing delivery authority for that pull request, and never by pushing an empty commit or rerunning a job that deploys, publishes, or writes externally. A repeated failure earns no further retrigger; inspect its job logs and reclassify.

## Pause gates and non-production deploys

Always pause for force-push to shared branches, production deploy, package publish, data deletion, secret rotation, and risky auth, billing, or permission changes; explain blast radius, safer alternative, rollback, and verification before continuing.

A non-production deploy that Patpat starts, such as a preview, staging, or shared test link, runs only when the user names it, after fresh verify and independent review, and with a stated rollback; a non-production deploy a provider runs automatically from an authorized push follows that push's delivery gates.

## Non-Git workspaces and ownership

If the workspace is not a Git repository, state before the first edit that changes have no Git rollback, then either ask before `git init` or copy only in-scope non-secret target files (never `.env*`, private keys, certs, or credentials) to a scratch snapshot named in `Cleanup`. In non-Git workspaces, Git-only checks and workflows (`git status`/`git diff` verification commands, Git worktree isolation, Git delivery/PR routes, `patpat-run`, and `verify_review.py --root` HEAD binding) stay unavailable; use task-native authoritative verification, snapshot/SHA-256 diffing, and serial single-owner edits unless a host-enforced filesystem+process sandbox isolates workers.

Read-only work never ships. Workers never ship. The parent ships.
