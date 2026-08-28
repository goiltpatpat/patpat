# Understand and Design Before Editing

The fastest safe change starts with a precise model of the current system. Patpat separates mechanics, rationale, blast radius, and the proposed contract so a plausible story cannot substitute for evidence.

## Trace mechanics

Use inspection for questions about where behavior enters, which layer owns it, how data moves, and which boundary validates it.

```text
/patpat inspect how a webhook becomes a persisted order. Show entry points, transformations, trust boundaries, and the authoritative store. Do not edit.
```

The report should cite code anchors and distinguish observed control flow from inferred intent.

## Recover rationale carefully

Current code proves what exists, not why it was chosen. For rationale-shaped questions, Patpat anchors the behavior in code first, then checks focused history and durable project records. Missing evidence stays unknown.

```text
/patpat explain why retries are disabled on this path. Separate repository evidence from inference.
```

## Prove the blast radius

Name the contract and find its consumers before changing it. Search direct call sites, generated surfaces, configuration, tests, persistence, and external adapters only where the contract reaches them.

For a contract change, report:

- what changes;
- migration impact;
- compatibility risk;
- call sites checked;
- proof for preserved behavior.

## Match design effort to uncertainty

Use the first rung that resolves the decision:

1. Reuse or delete existing code.
2. Make one bounded patch following an established pattern.
3. Write a small prototype when one unknown blocks the design.
4. Compare isolated candidates only when no repository precedent settles a costly choice.

Architecture work should finish with explicit boundaries and proof hooks, not an inventory of possible abstractions.

## Stop at the safety boundary

Do not simplify away auth, permission gates, validation, redaction, rollback, billing checks, or destructive-operation controls. If the requested design changes one of those contracts materially, Patpat pauses for explicit authority and additional review.

Next: [Build, debug, and verify](./04-build-debug-and-verify.md).
