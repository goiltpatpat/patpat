# Independent Review Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), and [preserve safety](../principles/preserve-safety.md).

## Review steps

1. Freeze the objective, proof contract, exact diff or artifact, and raw verification receipts.
2. Use a separate read-only reviewer for high-risk work when delegation is available and authorized; omit the intended conclusion. Enforce double-blind review: provide only the original user objective, candidate diff, and raw verification receipts; strip the implementer's internal chain-of-thought, rationalizations, and intended conclusion to prevent cognitive anchoring. Maintain strict anti-sycophancy: eliminate validating flattery (*great*, *brilliant*, *smart*, *spot-on*) and apologetic filler (*I apologize*, *I am sorry*). Lead with critique: probe what is missing, vulnerable, or unproven before acknowledging merits.
3. Trace changed contracts, callers, side effects, and safety boundaries.
4. Execute the solution-integrity audit.
5. Reconcile material requirements with the proof contract, then try to falsify the implementation and each proof claim. Passing declared claims does not cover an omitted requirement.
6. Report evidence-backed findings by severity (`blocker`, `high`, `medium`, `low`) and discard speculative style noise. When the main issue is a change in shape, prefer a compact diff-shaped or tree form from [earned representation](../references/earned-representation.md).
7. For accepted findings, name the earliest invalid requirement, design, implementation, or proof decision using the [failure edges](../references/execution-graph.md), then require the smallest correction and named re-verification.
8. Inspect the corrected artifact rather than accepting a remediation summary.
9. State residual gaps; review never authorizes delivery.

## Solution-integrity audit

Audit the candidate diff and proof evidence against the checks material to its claims and risk:

- **Assertion integrity (Floor Guard)**: Identify deleted, relaxed, commented, or conditionalized assertions and validation rules. Specifically audit the candidate diff for cheap-road-to-green moves: silenced checkers (`# noqa`, `# type: ignore`, `@ts-ignore`, `eslint-disable`, `nosemgrep`), unfinished stubs (`TODO`, empty `catch {}` or `except: pass`), weakened tests (added `.skip`/`.todo`/`xit`, deleted test files, or removed assertions in surviving tests), directional threshold loosening in budgets or configs, and unapproved exception rows. Require an explicit contract reason and replacement proof; reject unexplained weakening that manufactures a pass, and confirm new behavioral tests would fail against a one-line inversion or dummy return of the changed subject logic.
- **Genuine execution**: For behavioral claims, confirm proof exercises the real target path and material state or side effects when applicable. Fixtures and mocks may support the proof but must not replace its authoritative surface.
- **Generalization**: Probe representative valid inputs, material boundaries, and relevant error paths. Reject hardcoded fixture answers; use code-path reasoning where exhaustive execution is impossible.
- **Fresh binding**: Bind evidence to the exact candidate revision or a reproducible working-tree snapshot, plus the material inputs, environment, and oracle. For push-, PR-, or delivery-bound claims, require the committed head or the durable gate in [delivery proof](../../patpat-run/references/delivery-proof.md), which accepts a proof-first review when the proven tree equals that head's tree.

Classify proven evidence laundering or a bypass that invalidates the correctness claim as `blocker`. Grade other integrity findings by concrete impact; unavailable evidence is a verification gap, not proof of manipulation.

## Independent angles

When extra read-only reviewers are available and authorized, give each the same intent, diff, and integrity rubric from a distinct independent-angle. Do not name model slugs. Serial fallback when isolation or extra reviewers are missing.

Deduplicate and note disagreements. Assess each finding's evidence, assumptions, and impact independently of vote count; reviewers may share the same blind spot. Separate severity from confidence. A single supported finding can outweigh consensus. When safe execution is unavailable, retain a concrete code-supported finding with its conditions and impact, label the runtime evidence gap, and do not describe it as reproduced. If the conditions or impact are unproven, report a concern or evidence gap rather than a confirmed defect.

## Lead judgment

The parent is a lead, not a neutral aggregator. Bucket each synthesized finding: Act on / Consider / Noted / Dismissed. Keep existing severity labels. Do not auto-apply. Apply reconciliation precedence: test whether a disputed finding stems from an ambiguous or incomplete proof contract (`Contract misread`) before treating it as noise, routing directly back to `PROOF CONTRACT`. Flag **Doubt theater** as a review defect if across $\ge 2$ consecutive cycles with substantive reviewer findings, zero findings are classified as actionable. The deliverable is a synthesized verdict. Review comments, patches, and merges are out of this playbook.
