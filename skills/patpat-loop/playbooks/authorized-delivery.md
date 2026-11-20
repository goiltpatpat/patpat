# Authorized Delivery Playbook

Use after [default delivery](default-delivery.md) when work must land, publish, or deploy.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the remaining action and target (merge, publish, deploy) and resolve the existing PR or artifact directly.
2. Inspect live head, CI, and PR URL. Require fresh verify and review receipts for that head, and fetch the merge target. Durable work must pass `run_state.py check-gate --gate merge --base-head <base>` or `program_state.py check-delivery --gate merge --provider-receipt <file> --base-head <base>`. A head not containing its base is unproven: update and re-prove per [delivery proof](../../patpat-run/references/delivery-proof.md).
3. Require explicit `land` or `merge` language for the named PR or stack. Overnight/don't-stop/generic ship stop at merge-ready. Latest user instruction wins (`local only`, stop, wait, or retraction cancels earlier merge authority until re-named); re-read conversation immediately before merging.
4. Establish the provider gate from verified policy or CI config (never observed runs). An empty check list is not proof that a repository has no CI: checks can register late, and tool/permission failure is `Unknown`. Read the provider directly; stop on requested changes, unresolved threads, draft, or conflicts. Merge only on `CLEAN` or `HAS_HOOKS` (`mergeStateStatus` or equivalent; unreadable = `Unknown`). Wait within deadline for transient `UNKNOWN`/`BLOCKED` with running checks; stop if persistent. Missing review decision means no review required only if policy confirms. Re-read checks immediately before merging and pin merge to the proven head SHA. A check still pending at the wait's deadline has not passed. Match the first state:
   - **Unknown:** policy/config/checks unreadable -> stop and name what is missing.
   - **Required checks exist:** every required check must succeed on this head (`skipped` is not a pass; head CI edits weakening checks are not evidence).
   - **CI expected, none required:** policy requires none, but base/head has CI config or recent PRs show checks. Every expected check must succeed (no report, `skipped`, `neutral`, `cancelled`, or awaiting approval stops merge unless base filter excludes this head; skip directives and head CI edits are not evidence). State that the repo requires none.
   - **No provider CI:** policy requires none, no CI config, and no checks on this head or recent PRs. Green is unavailable, which is not a pass. For an external head, stop and ask; otherwise run the repo's strongest authoritative check on this exact head and tell the user before merging what proved it and that no provider check exists (if nothing runnable proves it, stop and ask).
5. Without a non-empty required-check set, `pr_watch.py` and the durable merge gate stay blocked by design. Do not forge a receipt or bypass them. Outside a durable store, step 4 decides; for durable work, stop and report the blocked gate.
6. Classify failed checks per [PR readiness handoff](pr-handoff.md) step 5. Retrigger an infrastructure flake at most once, only within existing delivery authority for that pull request, and never by pushing an empty commit or rerunning a job that deploys, publishes, or writes externally. A repeated failure earns no further retrigger; inspect its job logs and reclassify. Failure outside the diff is a stale base until `git merge-base --is-ancestor <fetched-base-sha> <pr-head-sha>` passes (update and re-prove; for stacked/fork heads, name stale base and stop except same-repo stacked heads in S4 under update authority). Never land a real failure, failing optional check, or skipped required check. Never weaken CI unasked; adjust CI settings only on user request or measured evidence when this change broke it, and disclose it.
7. Pause for production deploy, package publish, force-push, secret rotation, and risky auth/billing/permission changes; explain blast radius, rollback, and verification, then wait.
8. Squash merges: set subject to `<PR title> (#<PR number>)` if GitHub's default differs, and verify (never rewrite merged base history).
9. Merge queues: enqueue only under merge authority, never auto-merge. Report queued until merged revision reads back (report ejections; note earlier queue entries may alter the merged tree).
10. Re-check the remote revision directly after the action.

## Stack landing

Use when the user names `land` or `merge` for a stack (`S1`–`S6`; other numbers refer above). Four bindings apply after each merge:
- **Provider checks bind to head:** required checks must pass on each PR's current head SHA.
- **Local receipts bind to content where allowed:** `run_state.py` receipts carry per [delivery proof](../../patpat-run/references/delivery-proof.md) (equal tree + proven ancestor); `program_state.py` verdicts bind to exact commit (never carry). Patch-id equality and retargeting carry nothing.
- **Non-author execution proof:** each landed PR needs a required provider check whose base-read path filter covers its changed paths, or a verify receipt from a non-author/non-reviewer actor (e.g., [`patpat-verifier`](../../patpat-verifier/SKILL.md) or [swarm](swarm.md) lane).
- **Scoped authority:** covers merging the named stack; updating branches requires explicit naming in the same un-retracted request and covers only non-force trunk merges into same-repo branches (rebase/restack/force-push requires step 7 approval).

S1. **Resolve stack from provider:** [`discover_pr_stack.py`](../../patpat-ship/scripts/discover_pr_stack.py) on native stacks (never infer from branch names); user names non-native chains bottom-to-top.
S2. **Find landable run** from lowest open PR while: lowest base is trunk and each higher PR's base branch/SHA equals the PR below; head contains base; steps 2–6 pass with covering verify/review receipts; non-author execution proof exists; no higher PR is already merged (else rediscover). A PR merged into its parent's branch is not landed on trunk—stop. First failing PR is the ceiling.
S3. **Merge lowest PR only (base = trunk):** re-read conversation for retractions (step 3), pin to proven head SHA, apply steps 8–10, verify readback (`merged`, base = trunk, merge commit is ancestor of freshly fetched trunk). Queued/armed is not merged; never arm auto-merge on a stack.
S4. **Rediscover and advance next PR onto trunk:** if base ≠ trunk, stop and name it. If `git merge-base --is-ancestor <trunk-sha> <head-sha>` passes, go to S5. Else with update authority: clean checkout, merge freshly fetched trunk locally, classify with S5 before pushing (stop on conflict), push non-force only after passing `ship`. Without update authority: stop and name the branch.
S5. **Prove new head:**
   - **Tree-equal** (same tree, proven head is ancestor): run receipts carry unless proof depends on commit identity or repo has a gitlink.
   - **Tree-changed:** fresh verify + delta review before push (`git diff <proven-head> <new-head>` + PR diff, both full SHAs, clean worktree); durable runs need a new scoped run with `explicit-merge`.
   - **Rebased/rewritten** (proven head not ancestor): nothing carries; full fresh verify + review + new scoped durable run.
S6. **Repeat from S2; stop at ceiling.**

**Reply:** run, ceiling, stop reason; per PR: proven vs landed head SHA, non-author proof, carry mode (`tree-equal`/`delta`/`full`), merge commit or queued state, and any branch/PR needing update or proof.
