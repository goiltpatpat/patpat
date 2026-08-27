# Autopilot Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [sequence verifiable units](../principles/sequence-verifiable-units.md), [preserve safety](../principles/preserve-safety.md), and the [operating protocol](../references/operating-protocol.md). Use [`patpat-run`](../../patpat-run/SKILL.md) for the durable graph.

Choose a mode from the request:

- **Queue:** independent items, one owner each, root verifies every merge-ready head.
- **Stack:** sequenced items, one linear chain, operator lands unless the request names merge.

1. State the plan and wait when the user asked for the protocol. Execution starts only on explicit go.
2. Split the queue into independent slices. Overlapping writers run serially. Each owner is [`patpat-engineer`](../../patpat-engineer/SKILL.md) with exclusive files or branches.
3. Each owner builds and proves on the real surface. The parent runs [default delivery](default-delivery.md) for that slice. Owners never merge.
4. At each merge-ready head, the root runs [swarm](swarm.md) verification: gates at that revision, live behavior on the load-bearing surface, and a diff audit that distrusts the PR body. A new head voids the verdict.
5. Findings go back to the owner. A clean verdict does not merge by itself.
6. Queue mode merges a green verified PR only when the program included explicit land or merge language. Overnight and ship it are not merge. Stack mode appends verified links and stops for the operator unless merge language was present.
7. Stand down immediately on stop. Pause for protected-default merge, production deploy, force-push, secrets, and risky auth or billing changes.
8. Report owners, head revisions, verdicts, gaps, and what was actually delivered.
