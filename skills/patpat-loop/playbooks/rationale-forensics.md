# Rationale Forensics Playbook

Read [repository truth](../principles/repository-truth.md) and [boundary discipline](../principles/boundary-discipline.md).

This is the why-equivalent. There is no `/why` slash skill. Use it when the question is why code or a contract reached its current shape. How/placement questions stay on [investigation](investigation.md). Stay read-only. Do not mutate. Do not open a PR. Do not call Slack or Notion connectors.

## Code-anchor first

Start in the repository. Do not begin with a story.

1. Name the precise why-question and the current behavior that must be explained.
2. Anchor on paths and symbols: the file, function, test, or contract that exhibits the behavior.
3. Read that code, its tests, `git blame`, and a focused `git log`. Expand to in-repo pull requests and issues on the same repository when they name the symbol. Git plus GitHub PRs/issues on the target repo are required. Evidence before narrative.
4. Skip map: Slack is skipped (not connected; the user has not asked). Notion is skipped (not connected; the user has not asked). Do not fan out to other messengers. Record every skipped source as a null in Sources Consulted.
5. Distinguish contemporary evidence from later interpretation. A commit message, comment, or PR body is a lead, not proof, until the live code agrees.
6. Form competing hypotheses. Reconcile by date, scope, author proximity, and observed repository behavior. Label each material conclusion `confirmed`, `inferred`, or `unknown`.
7. Report with the [why-report contract](../../patpat-inspect/references/why-report.md). Recommend a present-day change only after separating historical intent from the current contract, then stop. Do not implement from this playbook.
