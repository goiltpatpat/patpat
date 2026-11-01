# Authorized Delivery Playbook

Use after [default delivery](default-delivery.md) when the work must land, publish, or deploy.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the remaining action and target: merge, publish, or deploy. Resolve the existing pull request or artifact directly; do not assume this session created it.
2. Inspect the live head, CI, and the PR URL. Require current verify and review receipts for that head, and fetch the merge target. Durable work must pass `run_state.py check-gate --gate merge --base-head <base>` or `program_state.py check-delivery --gate merge --provider-receipt <file> --base-head <base>`. A head that does not contain the base has an unproven merged result: update it and prove the new head, as [delivery proof](../../patpat-run/references/delivery-proof.md) defines.
3. Require explicit `land` or `merge` language for the named pull request or stack. Overnight, going to bed, don't stop, or a generic ship request without a named merge action reaches merge-ready and stops. State-then-wait still applies when the user asked only for the plan. The user's latest instruction wins: a later `local only`, stop, wait, or retraction cancels an earlier land or merge request until the user names land or merge again. Re-read the conversation for such an instruction immediately before merging.
4. If CI is green, merge. If CI failed, classify flake vs real fail. Retry a flake once. Do not land a real fail. Do not land because the playbook ended.
5. Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification, then wait.
6. For squash merges, ensure the final commit subject is `<PR title> (#<PR number>)`; if GitHub's generated title differs, set the subject explicitly before merging. Verify the resulting subject. Do not rewrite base history solely to add a suffix to an already-merged commit.
7. Re-check the remote revision directly after the action.
