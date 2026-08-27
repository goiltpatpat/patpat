# Why-report contract

Use this shape for rationale-forensics. Do not omit a section. Do not add a slash skill named `/why`. How-shaped questions use the how-report contract instead.

## Required sections

### Question

The why-question and the current behavior under explanation.

### Code anchors

Paths, symbols, blame, and focused log. Cite files and commits.

### Sources Consulted

List every source, including nulls. Required:

- Git (used)
- GitHub PRs/issues on the target repo (used or null with reason)
- Slack (skipped: not connected; user has not asked)
- Notion (skipped: not connected; user has not asked)

No connector calls for skipped sources.

### Competing hypotheses

At least two, each labeled `confirmed`, `inferred`, or `unknown`.

### Supported rationale

The account that survives the code anchors. Evidence before narrative.

### Gaps

What remains unknown and which skipped sources would have been next if the user had asked.
