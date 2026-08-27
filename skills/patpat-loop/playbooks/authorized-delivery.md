# Authorized Delivery Playbook

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the exact delivery action in the current user request: commit, push, pull request, merge, publish, or deploy. If none is named, stop after implementation evidence.
2. Inspect `git status`, the staged and unstaged diff, unrelated dirty files, secrets, and generated noise.
3. Require current [`patpat-verify`](../../patpat-verify/SKILL.md) evidence for the claim being delivered.
4. Require an independent [`patpat-review`](../../patpat-review/SKILL.md) pass.
5. Perform only the named action. Overnight or "don't stop" language continues through these checks without extra confirmation of that named ordinary action.
6. Pause for production deploy, package publish, merge onto a protected default, force-push, secret rotation, or risky auth, billing, and permission changes. Explain blast radius, rollback, and verification, then wait.
7. Re-check the delivered revision or remote state directly. Green CI does not authorize auto-merge.
