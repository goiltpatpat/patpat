# Default Delivery Playbook

Invoke this at the end of mutating work after verify and review pass only when delivery intent exists. Delivery intent is explicit commit, PR, or ship language (`open a PR`, `commit`, `ship it`, named ship route), overnight or continuation (`overnight`, `going to bed`, `don't stop`), or explicit land or merge. A bare existing pull request is not delivery intent. Update it only when other delivery intent is present. Explicit `/patpat` activation alone does not invoke this playbook. Patpat's authority and pause gates still apply.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

Skip this playbook when a higher-priority system or repository rule forbids automatic delivery, delivery intent is absent, Patpat activation is present without delivery intent, the path was read-only, the prototype is throwaway, the user said `don't commit` / `don't open a PR` / `local only`, or there is no in-scope change relative to the base. Default commit-and-PR requires delivery intent.

1. Inspect `git status`, the full diff, unrelated dirty files, secrets, and generated noise. Commit only the in-scope change. Leave unrelated work untouched.
2. Require current [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md) for that diff. If either is missing or failed, stop. [Delivery proof](../../patpat-run/references/delivery-proof.md) gives the exact commands and covers proofs that depend on commit identity and proofs taken beside unrelated dirty files.
3. Commit on a task branch. Prefer a small ordered commit. Do not commit Memory Bank, secrets, run-state, or unrelated dirty files. In a durable run with uncommitted proven content, stage it and pass `run_state.py check-gate --gate commit` first. Before any push, prove the committed head with exactly one gate, and stop if it fails:
   - Durable run: `run_state.py check-gate --gate ship`.
   - Program unit or integrated head: `program_state.py check-delivery`, with `--unit <id>` for a slice and `--checkout <worktree>` when the head lives in another worktree.
   - No durable store: rerun the authoritative check on the committed head. The review still holds only if the committed diff is the one the reviewer saw.
4. Resolve whether the branch already has a pull request. Use a non-force, non-lease-breaking push. If a pull request exists, update and re-check it; do not open a duplicate. Keep an existing draft in draft unless delivery intent includes a direct ready-PR request, explicit land or merge language, or overnight or continuation, and current-head verify plus review pass. Only then mark that draft ready and re-check it. If no pull request exists and the configured remote is an authorized target, open one ready pull request, never a draft. Report the URL or the exact reason delivery stopped.
5. Do not start the PR Readiness Handoff from this step. Keep building unless the user asked to move the PR toward merge-ready.
6. Merge only through [authorized delivery](authorized-delivery.md) when the user explicitly named `land` or `merge`. Overnight, going to bed, or don't-stop language drives the pull request to merge-ready and stops without merging. If CI is red, classify flake vs real fail; retry a flake once; do not land a real fail.
7. Pause for production deploy, package publish, force-push, secret rotation, protected-default merge without land language, and risky auth, billing, or permission changes.

An authorized multi-phase checkpoint is a separate progress operation described in [sequence verifiable units](../principles/sequence-verifiable-units.md). It requires exact-head verification and may not update an existing pull request until that exact head also has independent review. It never satisfies this playbook's final review or ready-PR gate.
