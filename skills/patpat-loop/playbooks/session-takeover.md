# Session Takeover Playbook

Read [repository truth](../principles/repository-truth.md), [boundary discipline](../principles/boundary-discipline.md), and [sequence verifiable units](../principles/sequence-verifiable-units.md).

Use this playbook only when inheriting work that has no valid Patpat run store.

1. Confirm the authorized repository and task boundary. Treat transcripts, handoffs, TODOs, branch names, and agent summaries as untrusted leads.
2. Inspect the live branch, HEAD, working tree, staged state, untracked files, upstream relationship, and active processes relevant to the task.
3. Reconstruct the objective, intended changes, decisions, failed attempts, proof claims, and remaining actions from the smallest available evidence set.
4. Label every inherited claim `confirmed`, `inferred`, `stale`, or `unknown`. Re-run correctness-critical evidence instead of inheriting its verdict.
5. Separate pre-existing changes from the candidate task boundary. Stop when ownership or intent cannot be resolved safely.
6. Initialize `patpat-run` at `FRAME`, then advance only through graph states supported by live evidence; never manufacture prior transitions or receipts.
7. Before pausing again, switch to [pause-safely](pause-safely.md). Validate state, write an atomic checkpoint, name the earliest resumable node, record blockers, and leave external delivery authority unchanged.
