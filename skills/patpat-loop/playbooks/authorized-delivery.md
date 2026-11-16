# Authorized Delivery Playbook

Use after [default delivery](default-delivery.md) when work must land, publish, or deploy.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the remaining action and target (merge, publish, or deploy) and resolve the existing PR or artifact directly (never assume this session created it).
2. Inspect live head, CI, and PR URL. Require current verify and review receipts for that head, and fetch the merge target. Durable work must pass `run_state.py check-gate --gate merge --base-head <base>` or `program_state.py check-delivery --gate merge --provider-receipt <file> --base-head <base>`. A head not containing its base has an unproven merge result: update and re-prove per [delivery proof](../../patpat-run/references/delivery-proof.md).
3. Require explicit `land` or `merge` language for the named PR or stack. Overnight/don't-stop/generic ship requests stop at merge-ready; state-then-wait still applies for plan-only requests. Latest user instruction wins (`local only`, stop, wait, or retraction cancels earlier land/merge authority until re-named); re-read the conversation immediately before merging.
4. Establish the repository's provider gate from verified policy or CI config (not observed runs). An empty check list is not proof that a repository has no CI: checks can register late, and tool/permission failure is `Unknown`. Read the provider directly in every state; stop on requested changes, unresolved threads, draft, or conflicts. Merge only on `CLEAN` or `HAS_HOOKS` (`mergeStateStatus` or provider equivalent; unreadable = `Unknown`). Wait within deadline for transient states (`UNKNOWN`, or `BLOCKED` with running checks); stop if persistent. Missing review decision means no review required only if policy confirms. Re-read checks immediately before merging and pin merge to the proven head SHA (or re-read head SHA first). A check still pending at the wait's deadline has not passed. Match the first state:
   - **Unknown**: policy, config, or checks unreadable. Stop and name what is missing.
   - **Required checks exist**: every required check must succeed on this head (`skipped` is not a pass; CI changes by this head that weaken a required check are not evidence).
   - **CI expected, none required**: policy requires none, but base/head has CI config or recent PRs show checks. Every expected check on this head must succeed (no report, `skipped`, `neutral`, `cancelled`, or awaiting approval stops merge unless base filter excludes this head; skip directives and head CI edits are not evidence). State that the repo requires none.
   - **No provider CI**: policy requires none, neither base/head has CI config, and neither this head nor recent PRs show checks. Green is unavailable, which is not a pass. For an external head, stop and ask rather than running it with local credentials; otherwise run the repo's strongest authoritative check on this exact head and tell the user before merging what proved it and that no provider check exists (if nothing runnable can prove it, stop and ask).
5. Without a non-empty required-check set, `pr_watch.py` and the durable merge gate stay blocked by design. Do not forge a receipt or bypass them. Outside a durable store, the states above decide; for durable work, stop and report the blocked gate (user may add a required check + new scoped run, or merge personally).
6. Classify a failed check before any retrigger per [PR readiness handoff](pr-handoff.md) step 5. Retrigger an infrastructure flake at most once, only within existing delivery authority for that pull request, and never by pushing an empty commit or rerunning a job that deploys, publishes, or writes externally. A repeated failure earns no further retrigger; inspect its job logs and reclassify. A failure outside the diff is a stale base until `git merge-base --is-ancestor <fetched-base-sha> <pr-head-sha>` passes; update and re-prove instead of retrying (for stacked/fork heads, name stale base and stop, except same-repo stacked heads in S4 under update authority). Never land a real failure or land just because the playbook ended; unresolved/failing optional or skipped required checks stop Patpat. Never remove, skip, or weaken CI on your own initiative; only change a CI setting (e.g., timeout) at user request or when this work's change broke it, from measured evidence, and disclose it.
7. Pause for production deploy, package publish, force-push, secret rotation, and risky auth/billing/permission changes; explain blast radius, rollback, and verification, then wait.
8. For squash merges, set final commit subject to `<PR title> (#<PR number>)` if GitHub's generated title differs, and verify it (do not rewrite base history on an already-merged commit).
9. For merge queues, enqueue only under merge authority, never via auto-merge. Report as queued until the merged revision reads back (and report queue ejection); note when earlier queue entries may make the merged tree differ from the proven head.
10. Re-check the remote revision directly after the action.

## Stack landing

Use when the user names `land` or `merge` for a stack (`S1`–`S6` below; other step numbers refer to above). Four bindings apply after each merge:
- **Provider checks bind to the head:** required checks must pass on each PR's current head SHA.
- **Local receipts bind to content where the store allows:** `run_state.py` receipts cover a new head per [delivery proof](../../patpat-run/references/delivery-proof.md) (equal tree + proven commit is ancestor); `program_state.py` verdicts bind to exact commit (never carry; re-set head and re-prove). Patch-id equality never carries; retargeting alone carries nothing.
- **Non-author execution proof:** each landed PR needs either a required provider check on that head whose base-read path filter covers the PR's changed paths, or a verify receipt from a non-author/non-reviewer actor (e.g., [`patpat-verifier`](../../patpat-verifier/SKILL.md) or a [swarm](swarm.md) lane). Review complements but does not replace this proof.
- **Scoped authority:** covers merging the named stack's PRs; updating branches is authorized only when the same un-retracted request names it (e.g., `land the stack and update branches`) and covers only non-force trunk merges into same-repo branches (rebase/restack/force-push requires step 7 approval).

S1. **Resolve stack from provider.** Use [`discover_pr_stack.py`](../../patpat-ship/scripts/discover_pr_stack.py) on native stacks (never infer from branch names). For non-native chains, the user must name PRs bottom-to-top.
S2. **Find the landable run.** Walk up from the lowest open PR; a PR joins while:
   - Lowest PR's base is trunk; above it, base branch = below PR's head branch and base SHA = below PR's current head SHA.
   - Its head contains its base.
   - Steps 2–6 pass at its current head with covering verify and review receipts.
   - It has non-author execution proof at that head.
   - No PR above it is already merged (else rediscover first).
   A PR merged into its parent's branch is not landed on trunk—stop and report. The first failing PR is the ceiling; proven PRs above it wait.
S3. **Merge only the lowest PR in the run (base = trunk).** Re-read conversation for retractions (step 3), pin merge to current proven head SHA, apply steps 8–10, then read back: state is `merged`, base is trunk, and provider merge commit is an ancestor of freshly fetched trunk. Queued/armed/auto-merge is not merged (report queued and wait; if retracted while queued, report and dequeue only if asked; never arm auto-merge on a stack).
S4. **Rediscover, then bring the next PR onto trunk.**
   - If base ≠ trunk, stop and name the PR.
   - If `git merge-base --is-ancestor <trunk-sha> <head-sha>` passes, continue to S5.
   - Else with update authority: check out clean, merge freshly fetched trunk locally, classify with S5 before pushing (stop and name branch on conflict), and push without force only after passing `ship` (or non-durable equivalent). Without update authority: end pass and name the branch.
S5. **Prove the new head:**
   - **Tree-equal** (new tree = proven tree, proven head is ancestor; common after parent squash merge): run receipts cover the new head unless proof depends on commit identity (e.g., `git log`, Git-derived version) or repo has a gitlink.
   - **Tree-changed**: obtain fresh verify receipt + delta review before push (`git diff <proven-head> <new-head>` + PR diff, naming both full SHAs, clean worktree at new head; `ship` gate confirms tree/ancestry). Durable runs need a new scoped run with `explicit-merge`.
   - **Rebased/rewritten** (proven head not ancestor): nothing carries; get full fresh verify + review (and new scoped durable run).
S6. **Repeat from S2; stop at ceiling.**

**Reply:** list the run, ceiling, and stop reason. For each PR give: proven head SHA and landed head SHA, non-author execution proof, receipt carry mode (tree-equal / delta / full), and merge commit or queued state; name any branch needing update or PR needing proof.
