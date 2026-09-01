# Blast Radius Playbook

Read [repository truth](../principles/repository-truth.md), [boundary discipline](../principles/boundary-discipline.md), and [proof over proxy](../principles/proof-over-proxy.md).

The job is the one-safety-fact the change depends on, not a caller list. Grep callers is not the deliverable.

1. Name the changed symbol, behavior, data shape, or contract.
2. Name the one safety fact that change depends on.
3. Climb the certainty ladder for that fact and say where it stopped:
   1. said so (worthless alone)
   2. pointed at `file:line`
   3. walked the failure and it does not reach
   4. ran real code (a script or test that calls the shipped function and fails loud if wrong)
   5. reproduced in the running app
4. Require executable proof or explicit `unproven`. Any fact that does not reach ladder step 4 is unproven. Do not write it as settled.
5. Remain read-only. Hand back, small: what it does; the one fact, the step reached, and the proof or unproven; real risks with `file:line`; cleared; cheapest check before merge.
