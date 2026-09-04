# Default Delivery Playbook

Invoke this at the end of mutating work after verify and review pass only when delivery intent exists. Delivery intent is explicit commit, PR, or ship language (`open a PR`, `commit`, `ship it`, named ship route), overnight or continuation (`overnight`, `going to bed`, `don't stop`), or explicit land or merge. A bare existing pull request is not delivery intent. Update it only when other delivery intent is present. Explicit `/patpat` activation alone does not invoke this playbook. Patpat's authority and pause gates still apply.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

Skip this playbook when a higher-priority system or repository rule forbids automatic delivery, delivery intent is absent, Patpat activation is present without delivery intent, the path was read-only, the prototype is throwaway, the user said `don't commit` / `don't open a PR` / `local only`, or there is no in-scope diff. Default commit-and-PR requires delivery intent.

1. Inspect `git status`, the full diff, unrelated dirty files, secrets, and generated noise. Commit only the in-scope change. Leave unrelated work untouched.
2. Require current [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md) for that diff. If either is missing or failed, stop.
3. Commit on a task branch. Prefer a small ordered commit. Do not commit Memory Bank, secrets, run-state, or unrelated dirty files.
4. Resolve whether the branch already has a pull request. Use a non-force, non-lease-breaking push. If a pull request exists, update and re-check it; do not open a duplicate. Keep an existing draft in draft unless delivery intent includes a direct ready-PR request, explicit land or merge language, or overnight or continuation, and current-head verify plus review pass. Only then mark that draft ready and re-check it. If no pull request exists and the configured remote is an authorized target, open one ready pull request, never a draft. Report the URL or the exact reason delivery stopped.
5. Do not start PR-drive babysit from this step. Keep building unless the user asked to watch the PR.
6. Merge only through [authorized delivery](authorized-delivery.md) when the user explicitly named `land` or `merge`. Overnight, going to bed, or don't-stop language drives the pull request to merge-ready and stops without merging. If CI is red, classify flake vs real fail; retry a flake once; do not land a real fail.
7. Pause for production deploy, package publish, force-push, secret rotation, protected-default merge without land language, and risky auth, billing, or permission changes.
