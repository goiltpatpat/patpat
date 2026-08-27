# Swarm Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the done predicate and the single report the parent must return.
2. Choose the shape: partitioned slices, a race on the same brief, or a mix. For a race, declare `first pass`, `rank all`, or `best-of` before spawning.
3. Read-only investigation may fan out across independent evidence sources without a prior single-owner proof run. Writable workers need every [earned parallelism](../principles/earned-parallelism.md) gate. If a writable gate fails, run serially and name the missing lanes.
4. Give each writable worker an exclusive path. Briefs stand alone: goal, slice or race arm, how to verify, and a `PASS` / `ISSUES` / `BLOCKED` report with evidence.
5. Fan out through [`patpat-engineer`](../../patpat-engineer/SKILL.md) for writes, or read-only workers for investigation. Inherit the parent model unless the user named models.
6. Aggregate into one table. Do not paste raw dumps. A missing required slice is a gap, not inferred coverage.
7. The parent verifies the integrated result. Worker self-report is not proof.
8. Delivery stays with the parent. Writable swarms finish through [default delivery](default-delivery.md).
