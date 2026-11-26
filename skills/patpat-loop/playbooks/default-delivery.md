# Default Delivery Playbook

Invoke after mutating work passes verify and review only when delivery intent exists: explicit commit/PR/ship language (`open a PR`, `commit`, `ship it`, named ship route), overnight/continuation (`overnight`, `going to bed`, `don't stop`), or explicit `land`/`merge`. A bare existing pull request is not delivery intent. Explicit `/patpat` activation alone does not invoke this playbook. Authority and pause gates still apply.

Read preserve safety, [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

Skip when higher-priority rules forbid automatic delivery, delivery intent is absent, the path was read-only or a throwaway prototype, the user said `don't commit`/`don't open a PR`/`local only`, or there is no in-scope change vs base. Default commit-and-PR requires delivery intent.

1. Inspect `git status`, full diff, unrelated dirty files, secrets, and generated noise; commit only in-scope changes.
2. Require fresh [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md) for that diff (stop if missing/failed). See [delivery proof](../../patpat-run/references/delivery-proof.md) for commit-identity proofs and dirty-tree handling.
3. Commit on a task branch (small ordered commit; never commit Memory Bank, secrets, run-state, or unrelated files). In a durable run with uncommitted proven content, stage and pass `run_state.py check-gate --gate commit` first. Before pushing, prove the committed head with one gate (stop on failure):
   - Durable run: `run_state.py check-gate --gate ship`.
   - Program unit/integrated head: `program_state.py check-delivery` (`--unit <id>` for a slice, `--checkout <worktree>` if in another worktree).
   - Non-durable: rerun the authoritative check on the committed head (review holds only if committed diff matches reviewed diff).
4. Push non-force, non-lease-breaking. If a PR exists, update and re-check (never duplicate); keep drafts in draft unless delivery intent includes a ready-PR request, `land`/`merge`, or overnight/continuation with passing current-head verify + review. If no PR exists on an authorized remote, open one ready PR (never draft). Keep the PR body <= 40 lines (lead with Merge-Danger Callout and goal under `## Why`; link long evidence logs or tables in a file or PR comment). Report the URL or exact stop reason.
5. Do not start PR Readiness Handoff from here unless asked to drive the PR to merge-ready.
6. Merge only via [authorized delivery](authorized-delivery.md) on explicit `land`/`merge`. Overnight/continuation stops at merge-ready. Classify red CI per [PR readiness handoff](pr-handoff.md) step 5 and follow the [CI flake policy](../references/git-and-ship.md#merge-and-ci-flake-policy). Never land a real failure.
7. Pause for production deploy, package publish, force-push, secret rotation, protected-default merge without land language, and risky auth/billing/permission changes.

Multi-phase checkpoints ([sequence verifiable units](../principles/sequence-verifiable-units.md)) require exact-head verification, may not update an existing PR without independent review at that head, and never satisfy this playbook's final review or ready-PR gate.
