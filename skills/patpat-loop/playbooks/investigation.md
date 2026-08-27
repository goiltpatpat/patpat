# Investigation Playbook

Read [repository truth](../principles/repository-truth.md) and [proof over proxy](../principles/proof-over-proxy.md).

1. Restate the question and identify what evidence would answer it.
2. Read repository instructions, relevant continuity files, current state, and the narrow code path.
3. Trace behavior through callers, boundaries, configuration, tests, and runtime evidence as needed.
4. Separate findings from inference and unresolved unknowns.
5. Recommend the smallest safe patch only when requested. Do not mutate during an audit or explanation.
6. Report evidence inspected, findings, severity, and what should remain unchanged.
