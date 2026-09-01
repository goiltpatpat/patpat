# Behavioral Evaluation Playbook

Read [proof over proxy](../principles/proof-over-proxy.md) and [earned parallelism](../principles/earned-parallelism.md).

1. Declare the capability, failure conditions, and scoring rubric before trials.
2. Prepare one positive trigger, one neighboring negative trigger, and a representative task when practical.
3. Create isolated disposable workspaces with equivalent inputs and organic names. Keep candidate, eval, test, judge, and rubric vocabulary out of candidate-visible paths and prompts.
4. Run trials without revealing the expected conclusion, scoring rubric, or another candidate's output. Preserve the raw event stream or transcript at an inspectable path and bind it by content digest.
5. Inspect resulting artifacts, commands, evidence, cleanup, and scope control.
6. Compare results against the declared rubric; do not score self-reports.
7. Record verifier or environment limitations separately from skill defects.
8. Promote, revise, or reject the change based on observed behavior.

Live-agent receipts must record host, Patpat revision, the rubric frozen before execution, prompt digests, event-stream or transcript digests and paths, before/after artifacts and commands (not self-report), cleanup, and verdict. Missing raw evidence is `INCONCLUSIVE`; a receipt from another revision or host is stale.
