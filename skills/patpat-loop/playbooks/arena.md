# Arena Playbook

Read [earned parallelism](../principles/earned-parallelism.md), [smallest safe change](../principles/smallest-safe-change.md), [shape before logic](../principles/shape-before-logic.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the artifact and a rubric of 3-6 gradeable criteria. Run `patpat-run/scripts/team_shape.py`; its explicit budget and observed capacity replace a preset candidate count. Candidates receive the same brief. They do not receive the rubric.
2. If any [earned parallelism](../principles/earned-parallelism.md) writable gate fails, run one serial attempt. Do not fake parallel coverage.
3. Give each writable candidate a separate Git worktree or host-enforced sandbox with its own Git index and process boundary. A separate directory or disjoint file set inside one worktree is not isolation. Shared branches, indexes, processes, credentials, or external resources are a stop.
4. Fan out through [`patpat-engineer`](../../patpat-engineer/SKILL.md). Each candidate returns a typed card: candidate id, artifact, evidence receipts, objections, reusable parts, verdict, and rejected alternatives. Do not retain its transcript. Inherit the parent model unless the user named models.
5. Run an adversarial falsification pass on each surviving candidate before selection. Challenge material edge cases, missing error paths, regression risks, negative side effects, and unstated assumptions; record bounded objections and falsifying observations. Use a separate read-only reviewer only when available, authorized, and within the earned worker budget. Otherwise the parent performs the pass and reports that actor independence was not attested.
6. Evaluate candidates against the rubric alongside their falsification findings. Pick the base a future maintainer can extend that withstands the challenge. Prefer the smaller surface when two tie.
7. Graft only the parts that keep one coherent model. Record grafts, rejections, dropouts, and preserved objections. If candidates wildly diverge, reframe instead of averaging.
8. Verify the synthesized artifact on its authoritative surface through [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md). The arena does not waive proof.
9. The parent runs [default delivery](default-delivery.md) on the synthesized artifact when Patpat delivery authority exists. Merge requires explicit `land` or `merge` language; overnight only drives the pull request to merge-ready.
