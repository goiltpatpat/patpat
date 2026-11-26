# Swarm Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the done predicate and the single report the parent must return.
2. Run `patpat-run/scripts/team_shape.py` from explicit task evidence and use its bounded topology. For a race, declare `first pass`, `rank all`, or `best-of` before spawning.
3. Read-only investigation may fan out across independent evidence sources without a prior single-owner proof run. Writable workers need every [earned parallelism](../principles/earned-parallelism.md) gate. If a writable gate fails, run serially and name the missing lanes.
4. Give each writable worker a separate Git worktree or host-enforced sandbox with its own Git index, process boundary, and parent-assigned unique branch/worktree ID (workers never invent shared branch names). Separate per-worker outputs and merge at read time rather than sharing mutable state files; disjoint files in one shared worktree are not isolated. Workers must use reactive wakeups and never run `sleep` or HTTP polling loops. Briefs stand alone: goal, slice or race arm, how to verify, and a `PASS` / `ISSUES` / `BLOCKED` report with evidence.
5. Fan out through [`patpat-engineer`](../../patpat-engineer/SKILL.md) for writes, or read-only workers for investigation. Inherit the parent model unless the user named models or the host lets the parent choose; then follow [model choice](../../patpat-setup/SKILL.md#model-choice).
6. Aggregate typed handoff cards into one table with an explicit **Unique / Non-Shared Dissent** column so single-worker counter-evidence is never suppressed by majority consensus. Preserve evidence receipts, objections, and reusable parts; do not paste worker transcripts or raw dumps. A missing required slice is a gap, not inferred coverage.
7. The parent verifies the integrated result. Worker self-report is not proof.
8. Delivery stays with the parent. Writable swarms finish through [default delivery](default-delivery.md) only when Patpat delivery authority exists.
