# Default Delivery Playbook

Invoked at the end of mutating work after verify and review pass. This is the pstack opening-a-PR job, bounded by Patpat's pause gates.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

Skip this playbook when the path was read-only, the prototype is throwaway, the user said `don't commit` / `don't open a PR` / `local only`, or there is no in-scope diff.

1. Inspect `git status`, the full diff, unrelated dirty files, secrets, and generated noise. Commit only the in-scope change. Leave unrelated work untouched.
2. Require current [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md) for that diff. If either is missing or failed, stop.
3. Commit on a task branch. Prefer a small ordered commit. Do not commit Memory Bank, secrets, or run-state.
4. Push the branch with a non-force, non-lease-breaking push and open a ready pull request when a remote exists. Never open as draft. Report the URL.
5. Do not start PR-drive babysit from this step. Keep building unless the user asked to watch the PR.
6. Merge only through [authorized delivery](authorized-delivery.md) after explicit land or merge language. Overnight, going to bed, or don't stop stop merge-ready and do not merge. If CI is red, classify flake vs real fail; retry a flake once; do not land a real fail.
7. Pause for production deploy, package publish, force-push, secret rotation, protected-default merge without land language, and risky auth, billing, or permission changes.
