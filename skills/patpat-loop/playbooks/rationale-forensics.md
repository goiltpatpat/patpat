# Rationale Forensics Playbook

Read [repository truth](../principles/repository-truth.md) and [boundary discipline](../principles/boundary-discipline.md).

Use this playbook when the question is why code or a contract reached its current shape. Questions about current behavior or placement stay on [investigation](investigation.md). Stay read-only. Do not mutate or open a pull request. Do not call unrelated external connectors to fill an evidence list.

## Code-anchor first

Start in the repository. Do not begin with a story.

1. Name the precise why-question and the current behavior that must be explained.
2. Anchor on paths and symbols: the file, function, test, or contract that exhibits the behavior.
3. Read that code, its tests, `git blame`, and a focused `git log`. When available and material, expand to pull requests and issues from the repository's configured provider that name the symbol. Record an access gap instead of guessing. Evidence before narrative.
4. Record every material source used. If a material source is unavailable, record the reason and the resulting gap. Do not fan out to unrelated external systems merely to make the source list longer.
5. Distinguish contemporary evidence from later interpretation. A commit message, comment, or PR body is a lead, not proof, until the live code agrees.
6. Form competing hypotheses. Reconcile by date, scope, author proximity, and observed repository behavior. Label each material conclusion `confirmed`, `inferred`, or `unknown`.
7. Report with the [why-report contract](../../patpat-inspect/references/why-report.md). Recommend a present-day change only after separating historical intent from the current contract, then stop. Do not implement from this playbook.
