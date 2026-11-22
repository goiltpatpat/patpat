# Parallelism Rules

Full worker isolation and fan-out rules referenced by the [operating protocol](operating-protocol.md#four-gates-and-mechanical-enforcement).

Default to one owner. Workers return compact findings and evidence, not transcripts. For follow-up rounds, retries, or next units, pass a consolidated brief (objective, later directives, prior evidence or branch state) rather than relying on chained interrupt-resumes; reuse a live worker only when it holds expensive process or environment state.

Writable fan-out requires a separate Git worktree or host-enforced sandbox per owner (own Git index and process boundary) plus a named integrator and verifier; disjoint paths in one worktree are not isolation, so otherwise run serially and say so. Read-only fan-out may share a worktree. Worker output is a candidate; the parent verifies and merges.
