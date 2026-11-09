# Authorized Delivery Playbook

Use after [default delivery](default-delivery.md) when the work must land, publish, or deploy.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the remaining action and target: merge, publish, or deploy. Resolve the existing pull request or artifact directly; do not assume this session created it.
2. Inspect the live head, CI, and the PR URL. Require current verify and review receipts for that head, and fetch the merge target. Durable work must pass `run_state.py check-gate --gate merge --base-head <base>` or `program_state.py check-delivery --gate merge --provider-receipt <file> --base-head <base>`. A head that does not contain the base has an unproven merged result: update it and prove the new head, as [delivery proof](../../patpat-run/references/delivery-proof.md) defines.
3. Require explicit `land` or `merge` language for the named pull request or stack. Overnight, going to bed, don't stop, or a generic ship request without a named merge action reaches merge-ready and stops. State-then-wait still applies when the user asked only for the plan. The user's latest instruction wins: a later `local only`, stop, wait, or retraction cancels an earlier land or merge request until the user names land or merge again. Re-read the conversation for such an instruction immediately before merging.
4. Establish this repository's provider gate before judging CI. Read required check names from verified repository policy or its CI contract, not from observed runs. An empty check list is not proof that a repository has no CI: checks can register late after a push, and a tool or permission failure means unknown, not absent. In every state, read the provider directly and stop on requested changes, unresolved threads, a draft, or conflicts. Merge only on a clean aggregate state: `CLEAN` or `HAS_HOOKS` in GitHub's `mergeStateStatus`, or the provider's equivalent. A provider with no readable equivalent counts as Unknown. While a state such as `UNKNOWN`, or `BLOCKED` with checks still running, can still change, wait within the deadline; stop if it persists. A missing review decision means no review is required only when policy shows that. Re-read the checks immediately before merging, and pin the merge to the proven head SHA when the provider allows it; otherwise re-read the head SHA first. A check still pending at the wait's deadline has not passed. Follow the first state that matches:
   - **Unknown**: policy, configuration, or checks could not be read. Stop and name what is missing.
   - **Required checks exist**: every required check must report success on this head. A `skipped` result is not a pass, and a CI change made by the head that weakens a required check is not evidence.
   - **CI expected, none required**: policy requires nothing, but the base or head holds CI configuration, or recent pull request heads show checks. Every check expected on this head must report success. Anything else, including no report, `skipped`, `neutral`, `cancelled`, or awaiting approval, stops the merge unless a filter read from the base shows this head does not trigger that check. Skip directives and CI changes made by the head are not evidence. Say that the repository requires none.
   - **No provider CI**: policy requires no check, neither the base nor the head holds CI configuration, and neither this head nor recent pull request heads show a check. Green is unavailable, which is not a pass. For a head from outside the repository, stop and ask the user rather than run its code with local credentials. Otherwise run the repository's strongest authoritative check on this exact head, then tell the user before merging that no provider check exists and what proved the head. If nothing runnable can prove it, stop and ask the user.
5. Without a non-empty required-check set, `pr_watch.py` and the durable merge gate stay blocked by design. Do not forge a receipt or bypass them. Outside a durable store, the states above decide. For durable work, stop and report the blocked gate. The user can add a required check and start a new scoped run, or merge personally.
6. If a check failed, classify it before any retrigger, as [PR readiness handoff](pr-handoff.md) step 5 defines. Retrigger an infrastructure flake at most once, only within existing delivery authority for that pull request, and never by pushing an empty commit or rerunning a job that deploys, publishes, or writes externally. A repeated failure earns no further retrigger; inspect its job logs and reclassify. A failure outside the diff is a stale base until `git merge-base --is-ancestor <fetched-base-sha> <pr-head-sha>` succeeds. Update a stale head and prove it again instead of retrying; for a stacked or fork head, name the stale base and stop. The one exception is a same-repository stacked head that [stack landing](#stack-landing) S4 may update under update authority. Do not land a real fail. Do not land because the playbook ended. A check that stays unresolved, including a failing optional check or a skipped required one, stops Patpat: the user can fix it or merge personally. CI belongs to the repository: never remove, skip, or weaken a check on your own initiative to reach green. Change a CI setting such as a timeout only at the user's request, or when this work's own change made it fail, from measured evidence, and disclose it.
7. Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification, then wait.
8. For squash merges, ensure the final commit subject is `<PR title> (#<PR number>)`; if GitHub's generated title differs, set the subject explicitly before merging. Verify the resulting subject. Do not rewrite base history solely to add a suffix to an already-merged commit.
9. If the repository requires a merge queue, enqueue only under this merge authority and never through auto-merge. Queued is not merged: report it as queued until the merged revision reads back, and report an ejection from the queue. A queue can land on earlier entries, so say when the merged tree may differ from the proven head.
10. Re-check the remote revision directly after the action.

## Stack landing

Use this when the user names `land` or `merge` for a stack. Labels S1 to S6 below are this section's steps; other step numbers refer to the numbered list above. Four bindings decide what still holds after each merge:
- **Provider checks bind to the head.** Required checks must pass on each PR's current head SHA. An old green never transfers to a new head.
- **Local receipts bind to content, and only where the store says so.** A [`run_state.py`](../../patpat-run/scripts/run_state.py) verify or review receipt covers a new head by the [delivery proof](../../patpat-run/references/delivery-proof.md) rule: its tree equals the proven tree, and the proven commit is an ancestor of the new head. A program verdict binds to its exact commit, so a program unit never carries; set its head and prove it again, as delivery proof's squash-landed dependency row says. Patch-id equality never carries a receipt, because it ignores whitespace and context. A retarget keeps the head but changes the merged result, so it carries nothing by itself.
- **Every landed PR has an execution proof its author did not produce.** In a stack, each landing changes the base under every PR above it, so the author's own run is not enough. Either a required provider check runs on that head and its path filter, read from the base, covers the PR's changed paths, or a verify receipt comes from an actor that is neither the PR's owner nor its reviewer, such as [`patpat-verifier`](../../patpat-verifier/SKILL.md) or a [swarm](swarm.md) lane. A read-only review complements this proof; it does not replace it.
- **Authority binds to the named stack and the named update method.** A land request covers merging the PRs of that stack. It covers updating their branches only when the same request names it, as in `land the stack and update branches`, and no later instruction withdrew it. Even then it covers only a non-force merge of trunk into a same-repository branch of that stack. A rebase, restack, or force-push needs step 7 and the user's approval for that branch.

S1. **Resolve the stack from the provider.** Use [`discover_pr_stack.py`](../../patpat-ship/scripts/discover_pr_stack.py) on a native stack. Never infer a stack from branch names. For a non-native chain, the user must name its PRs in order from bottom to top.

S2. **Find the landable run.** Walk up from the lowest open PR. A PR joins the run when every one of these holds:
   - The lowest PR's base is trunk. Above it, a PR's base branch is the head branch of the PR below it, and its base SHA equals that PR's current head SHA.
   - Its head contains its base, so its merged result is the tree that was proven.
   - Steps 2 through 6 pass for it at its current head, with verify and review receipts that cover that head.
   - It has an execution proof its author did not produce, at that head.
   - No PR above it is already merged. A merge above an open PR means the observation is stale, so rediscover before deciding.

   A merged PR counts as landed only when its base was trunk. One merged into its parent's branch put no code on trunk, so stop and report it.

   The first PR that fails any of these is the ceiling. A proven PR above the ceiling waits, because landing it would pull the unproven code below it into trunk.

S3. **Merge only the lowest PR of the run, and only when its base is trunk.** Re-read the conversation for a retraction first, as step 3 requires. Pin the merge to the current head SHA that its receipts cover, and apply steps 8 through 10. Then read it back:
   - Its state is merged and its base is trunk, not the branch of its parent.
   - The provider's merge commit is an ancestor of freshly fetched trunk.

   Queued, armed, or auto-merge-requested is not merged. Report a queued PR as queued and wait. If the user retracts while a PR is queued, it can still land: report it, and dequeue it only if the user asks. Never arm auto-merge on a stack.

S4. **Rediscover, then bring the next PR onto trunk.** Every merge makes the manifest stale. On GitHub, a merge with branch deletion retargets the next PR to trunk but does not rebase it. Its head then lacks the new trunk commit, so step 2 calls its merged result unproven.
   - If its base is not trunk, stop and name the PR. Retargeting is the provider's job or the user's.
   - If its head already contains the new trunk, as `git merge-base --is-ancestor <trunk-sha> <head-sha>` shows, continue with S5.
   - Otherwise, with update authority, check out its branch clean, merge freshly fetched trunk into it locally, and classify the result with S5 before any push. A merge conflict ends the pass, and the conflicting branch is named. Push without force only after the new head passes the `ship` gate in delivery proof, or its non-durable equivalent. This is the one stack update that step 6 permits under that authority.
   - Without update authority, end the pass and name the branch.

S5. **Prove the new head, reusing evidence only where content proves it.** If S4 made a merge update, classify it as below, then wait for required provider checks on the pushed head. A head that already contained trunk is checked by S2 as it stands.
   - **Tree-equal:** the new tree equals the proven tree and the proven head is an ancestor. This is the usual result after a squash merge of the parent when nothing else reached trunk. Run receipts cover the new head, unless the proof contract depends on commit identity, such as a check that reads `git log` or a version derived from Git. A repository with a gitlink never qualifies, because the delivery-proof tree is unavailable there.
   - **Tree-changed:** other commits reached trunk in between. Get a fresh verify receipt and a delta review before the push. Name both full SHAs, and leave the worktree checked out clean at the new head so the reviewer can read the files. The reviewer receives `git diff <proven-head> <new-head>`, which is the content the update added, together with the PR's own diff, and issues a receipt that names the new head. The `ship` gate, not the reviewer, confirms the tree and ancestry. A durable run needs a new scoped run declaring `explicit-merge` for the new head, as delivery proof's failure-mode table says.
   - **Rebased or rewritten:** the proven head is not an ancestor. Nothing carries. Get a full fresh verify and review; a durable run needs a new scoped run, as above.

S6. **Repeat from S2. Stop at the ceiling.** With update authority and an otherwise quiet trunk, a pass can land the whole stack. Without it, a pass usually lands one PR and names the next branch to update. Extending past the ceiling needs fresh proof for each PR above it, so it starts a new pass.

**Reply:** list the run and its ceiling with the reason it stopped. For each PR, give:
- the head SHA it was proven at, and the head it landed at;
- its non-author execution proof;
- whether its receipts carried by tree equality, or came from a delta or full review;
- its merge commit, or its queued state.

Name the branch that needs an update or the PR that needs proof before the next pass.
