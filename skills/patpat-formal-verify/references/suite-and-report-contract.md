# Formal Verification Suite, Bug Ledger, and Report Contract

Companion reference for [`patpat-formal-verify`](../SKILL.md). Load when authoring a durable project-local formal-verification suite, maintaining a bug ledger, or formatting the full invariant report table.

## Runtime toolchain

Patpat's core runtime, AST symbol extraction, architecture diagrams, and counterexample replay operate in 100% pure Python 3.11+ standard library with zero external dependencies. Live TLA+/TLC model checking is an optional verification toolchain for exploring new state spaces and requires Java (`tla2tools.jar`). When Java is absent, environments still execute the pure-Python model checker (`check_assignment_model.py`) and counterexample replayer (`replay_assignment_counterexample.py`) to verify existing bounds, state invariants, and runtime replays.

## Durable project-local suite checklist

Create a durable project-local formal-verification skill and suite only when later changes must rerun the property. Keep one-off investigations local to that task.

1. Place the skill in the project's canonical skill tree from repository instructions and manifests; keep model, proof, harness, and small scripts beside it or in the repository's established verification location.
2. Author the skill so an agent arriving mid-change can: decide whether changed code is covered, run the exact command, distinguish a code defect from verification drift, update the check when the contract changes, and report uncovered behavior.
3. Record with zero placeholders: claim and harm, covered paths and functions, code-to-model mapping, action granularity, property, bounds, assumptions, tool identity, exact command, failure interpretation, limitations, and last synchronized commit.
4. Include a targeted mutant for every claimed user-facing property. For auxiliary model-consistency invariants, label their role and either provide a targeted mutant or explain why they add no independent product claim.
5. When claiming correspondence to implementation behavior, apply a scratch source mutation in an isolated copy or worktree and show the real-code checks catch it. Restore or discard each scratch mutation and rerun the unchanged check. Never mutate live source; if safe isolation is unavailable, report source-mutation evidence as `INCONCLUSIVE`.
6. Run the repository's skill validator and evaluate one prompt that routes here plus a neighboring prompt that belongs to [`patpat-verifier`](../../patpat-verifier/SKILL.md). Structural discovery alone does not prove prompt-time routing.

## Bug ledger contract

Keep a bug ledger in a linked project reference file (for example `references/bug-ledger.md`) so found bugs retain regression value while keeping the skill entry small.

- Number a `bug` only when its path is `replayed` or otherwise reproduced against current code; keep `model-only` and `replay-inconclusive` findings as unnumbered open model findings.
- Record on one row: the reader's sentence for what went wrong, the broken rule, the chart state with its model or diagram ID (or `none` when no statechart exists), the replay evidence, and the fix reference (commit, PR, or issue) once landed.
- Retain each counterexample as a regression: the unchanged property must hold on fixed code, and a replayed path becomes a real-code test when a safe entry point exists.
- Append-only history: mark obsolete rows `superseded` with a reason when a contract changes; never renumber or delete rows.

## Invariant report table schema

Assess product correctness separately from snapshot binding. Present one row per checked invariant with these exact columns (or, if a table is unsuitable, one complete labeled list item per invariant containing all fields inline):

| Column | Required content |
| --- | --- |
| `Invariant` | Property name |
| `Role` | Derived from the authoritative project contract, not the invariant name; for auxiliary invariants, state whether it is a separate product guarantee |
| `Meaning` | Start with `reader-confirmed` or `agent-derived`, followed by the one-sentence meaning |
| `Harm or consistency purpose` | User harm prevented or model-consistency purpose |
| `Code/model mapping` | Separate `Model:` (formula/property) and `Implementation:` (cited path and function, or `Implementation: model-only — <reason>` / `Implementation: INCONCLUSIVE — <missing evidence>`) |
| `Targeted mutant and observed result` | Targeted mutant and observed counterexample count inline, or `none` when no targeted mutant exists |

Additional required report fields:

- Full checker-version string and artifact digest copied from the current receipt.
- Bounds and assumptions, overall result (`in sync`, `updated`, `bug`, or `blocked`), numbered counterexample path, replay status, source-mutation result, sync commit, cleanup, and uncovered behavior.
- Mark any field unsupported by the evidence packet as `INCONCLUSIVE` and name the missing evidence; state plainly which evidence layer passed and which remains unproven.
