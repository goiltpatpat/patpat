# Autopilot Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), [preserve safety](../principles/preserve-safety.md), and the [operating protocol](../references/operating-protocol.md). Use [`patpat-run`](../../patpat-run/SKILL.md) for the durable graph.

Choose a mode from the request:

- **Queue:** independent items, one owner each, root verifies every merge-ready head.
- **Stack:** sequenced items, one linear chain, operator lands unless the request names merge.

1. State the plan and wait when the user asked for the protocol. Execution starts only on explicit go. Validate multi-unit plans with `validate_plan.py`, initialize `patpat-run/scripts/program_state.py`, and keep its dispatch gate closed until the integration owner admits the dependency frontier.
2. Run `patpat-run/scripts/team_shape.py` from explicit task evidence and capacity. Split only a returned `distributed` frontier; run `iterative` serially, and use `adversarial` for falsifiable candidates rather than independent delivery slices. Overlapping writers run serially. Each writable owner is [`patpat-engineer`](../../patpat-engineer/SKILL.md) in a separate worktree or host-enforced sandbox; exclusive files in one shared worktree are not sufficient.
3. Each owner builds and proves on the real surface in a separate worktree or host-enforced sandbox. The parent runs [default delivery](default-delivery.md) for that slice only when Patpat delivery authority exists. Owners never ship or merge.
4. At each merge-ready head, the root runs [swarm](swarm.md) verification: gates at that revision, live behavior on the load-bearing surface, and a diff audit that distrusts the PR body. A new head voids the verdict. When trusted provider observations are available, evaluate each head with [`patpat-ship/scripts/pr_watch.py`](../../patpat-ship/scripts/pr_watch.py); its `ready` verdict stops at handoff and never grants merge authority.
5. Findings go back to the owner. A clean verdict does not merge by itself.
6. Queue and stack modes merge a green verified PR only when the request explicitly says `land` or `merge`. Overnight, going to bed, or don't-stop language continues verification and PR driving until merge-ready, then stops without merging.
7. Stand down immediately on stop. Pause for protected-default merge, production deploy, force-push, secrets, and risky auth or billing changes.
8. Record worker handoffs in the program inbox. Peek events and acknowledge their sequence only after processing succeeds. Record exact-head verification plus independent review in the ledger. A changed dependency head invalidates downstream evidence. Report owners, head revisions, verdicts, gates, gaps, and what was actually delivered.
