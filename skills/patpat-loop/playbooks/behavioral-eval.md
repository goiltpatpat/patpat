# Behavioral Evaluation Playbook

Read [proof over proxy](../principles/proof-over-proxy.md) and [earned parallelism](../principles/earned-parallelism.md).

1. Declare the capability, failure conditions, and scoring rubric before trials.
2. Prepare one positive trigger, one neighboring negative trigger, and a representative task when practical.
3. Create isolated disposable workspaces with equivalent inputs and sanitized candidate labels.
4. Run trials without revealing the expected conclusion or another candidate's output.
5. Inspect resulting artifacts, commands, evidence, cleanup, and scope control.
6. Compare results against the declared rubric; do not score self-reports.
7. Record verifier or environment limitations separately from skill defects.
8. Promote, revise, or reject the change based on observed behavior.

Live-agent receipts must record host, Patpat revision, declared rubric, +prompt, −prompt, observed artifacts and commands (not self-report), cleanup, and verdict.
