# Rationale Forensics Playbook

Read [repository truth](../principles/repository-truth.md) and [boundary discipline](../principles/boundary-discipline.md).

1. State the precise historical question and the current behavior that needs explanation.
2. Start with the relevant code, tests, blame, and focused commit history. Expand to pull requests, issues, architecture decisions, incidents, or operational evidence only when available and directly relevant.
3. Distinguish contemporary evidence from later interpretation. Do not treat a commit message, comment, or external record as authoritative merely because it is specific.
4. Reconcile contradictions by date, scope, author proximity, and observed repository behavior.
5. Report the supported rationale, competing explanations, missing evidence, and confidence. Cite the exact artifact for each material conclusion.
6. Keep the investigation read-only. Recommend a present-day change only after separating historical intent from the current contract.
