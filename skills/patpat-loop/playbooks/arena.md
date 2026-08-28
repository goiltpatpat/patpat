# Arena Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [smallest safe change](../principles/smallest-safe-change.md), [shape before logic](../principles/shape-before-logic.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the artifact, the rubric of 3-6 gradeable criteria, and N. Candidates receive the same brief. They do not receive the rubric.
2. If any [earned parallelism](../principles/earned-parallelism.md) writable gate fails, run one serial attempt. Do not fake parallel coverage.
3. Give each writable candidate a separate Git worktree or host-enforced sandbox with its own Git index and process boundary. A separate directory or disjoint file set inside one worktree is not isolation. Shared branches, indexes, processes, credentials, or external resources are a stop.
4. Fan out through [`patpat-engineer`](../../patpat-engineer/SKILL.md). Each candidate returns the artifact plus rejected alternatives. Inherit the parent model unless the user named models.
5. Read every complete candidate against the rubric. Pick the base a future maintainer can extend. Prefer the smaller surface when two tie.
6. Graft only the parts that keep one coherent model. Record grafts, rejections, and dropouts. If candidates wildly diverge, reframe instead of averaging.
7. Verify the synthesized artifact on its authoritative surface through [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md). The arena does not waive proof.
8. The parent runs [default delivery](default-delivery.md) on the synthesized artifact when Patpat delivery authority exists. Merge requires explicit `land` or `merge` language; overnight only drives the pull request to merge-ready.
