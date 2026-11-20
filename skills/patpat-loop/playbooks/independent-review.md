# Independent Review Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), and [preserve safety](../principles/preserve-safety.md).

## Review steps

1. Freeze the objective, proof contract, exact diff/artifact, and raw verification receipts.
2. Use a separate read-only reviewer for high-risk work when available and authorized; enforce double-blind review (pass only objective, diff, and raw receipts—strip implementer chain-of-thought, rationalizations, and intended conclusion). Maintain strict anti-sycophancy (no flattery or apologetic filler); lead with critique.
3. Trace changed contracts, callers, side effects, and safety boundaries.
4. Execute the solution-integrity audit.
5. Reconcile material requirements with the proof contract and try to falsify both implementation and proof claims (passing declared claims does not cover omitted requirements).
6. Report evidence-backed findings by severity (`blocker`, `high`, `medium`, `low`), discarding speculative style noise. Prefer compact diff/tree shapes from [earned representation](../references/earned-representation.md) for structural issues.
7. For accepted findings, name the earliest invalid decision via [failure edges](../references/execution-graph.md) and require the smallest fix + named re-verification.
8. Inspect the corrected artifact directly rather than accepting a summary.
9. State residual gaps; review never authorizes delivery.

## Solution-integrity audit

- **Assertion integrity (Floor Guard):** Flag deleted, relaxed, commented, or conditionalized assertions/rules and cheap-road-to-green moves: silenced checkers (`# noqa`, `# type: ignore`, `@ts-ignore`, `eslint-disable`, `nosemgrep`), unfinished stubs (`TODO`, empty `catch {}`/`except: pass`), weakened tests (`.skip`/`.todo`/`xit`, deleted tests/assertions), loosened thresholds, or unapproved exceptions. Require an explicit contract reason and replacement proof; confirm new behavioral tests fail against a one-line inversion or dummy return.
- **Genuine execution:** Behavioral proof must exercise the real target path and material side effects; mocks may support but never replace the authoritative surface.
- **Generalization:** Probe valid inputs, boundaries, and error paths; reject hardcoded fixture answers.
- **Fresh binding:** Bind evidence to the exact revision or reproducible snapshot, inputs, environment, and oracle. Delivery-bound claims require the committed head or [delivery proof](../../patpat-run/references/delivery-proof.md) (proven tree equals head tree).

Proven evidence laundering or correctness-invalidating bypass = `blocker`. Unavailable evidence is a verification gap, not proof of manipulation.

## Independent angles

When extra read-only reviewers are available and authorized, assign distinct angles with the same intent, diff, and rubric (never name model slugs; fall back serially if unavailable). Deduplicate, note disagreements, and weigh evidence independently of vote count (separate severity from confidence). Without safe execution, retain code-supported findings with conditions/impact and label the runtime gap (never call it reproduced); unproven impact stays a concern/gap.

## Lead judgment

Parent is a lead, not a neutral aggregator. Bucket findings into **Act on / Consider / Noted / Dismissed** keeping severity labels. Do not auto-apply. Check whether disputed findings stem from an ambiguous proof contract (`Contract misread` -> return to `PROOF CONTRACT`) before dismissing as noise. Flag **Doubt theater** if ≥2 consecutive cycles with substantive findings yield zero actionable items. Deliverable is a synthesized verdict only (no review comments, patches, or merges).
