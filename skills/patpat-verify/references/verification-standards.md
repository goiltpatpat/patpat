# Verification Standards and Isolation

Companion reference for [`patpat-verify`](../SKILL.md). Load when classifying broader-suite failures, isolating live runtimes, or applying claim-adaptive proof rules.

## Broader-suite failure classification

A broader-suite failure counts as `pre-existing` only when the exact same test fails with the same signature on the pinned base SHA in an equivalent environment inside a temporary worktree outside the repository, removed afterward with `git worktree remove`. That worktree is diagnostic only, never part of the candidate, and requires no proof-contract revision.

- If the base run cannot be made equivalent, classify the failure as `unclassified`; otherwise classify it as `new`.
- Any `new` or `unclassified` failure blocks `verified`.
- A `pre-existing` failure may accompany `verified` only when explicitly listed and when it does not exercise the changed behavior.

## Runtime isolation

When verifying live servers, browsers, or databases:

- Bind isolated ports and use temporary data/profile directories (`mktemp`) so all runtime state stays ephemeral.
- Keep default user ports, shared browser profiles, and persistent databases untouched so parallel workers and verification runs never interfere with live sessions.
- Clean up all temporary processes and directories on exit.

## Claim-adaptive verification and fresh binding

| Claim type | Required proof standard |
| --- | --- |
| Behavioral | Vary material inputs, error branches, or state transitions through the authoritative interface and assert literal observed output or material effect. When a new test is the primary behavioral proof for changed logic, confirm mutation resilience with a one-line scratch fault (invert the condition or early-return, verify the test fails, then revert immediately). |
| Static | Run deterministic structure, schema, type, or content checks on the authoritative artifact; skip runtime theater for non-runtime claims. |
| Proxy rejection | Fixtures and mocks isolate contracts but never replace the real system for system-level claims. Reject mock-call counts, copied constants, self-referential expected values, narrative summaries, and clean compilation as sole behavioral proof. If a behavioral claim has no observable oracle, report `INCONCLUSIVE`. |
| Fresh binding | Bind evidence to the exact candidate revision or reproducible working-tree snapshot plus material inputs, environment, and oracle. For push-, PR-, or delivery-bound claims, run at the committed head or validate a durable receipt via [delivery proof](../../patpat-run/references/delivery-proof.md) (proven tree equals head tree on a clean checkout; report as reused). Checks depending on commit identity (Git history, derived versions) must run at the head. Reject stale, cached, or transferred logs. |

Inspect artifacts and results directly rather than trusting an implementing agent's summary. For high-risk boundaries, obtain an independent review without leaking the intended conclusion.
