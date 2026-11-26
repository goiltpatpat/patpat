---
name: patpat-review
description: Independently challenge an implementation, diff, or verification claim without editing.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"Codebase","requires_state":["acceptance-verified"],"produces_state":["delivery-review-cleared"],"verification_cmd":"python3 <loaded-skill-directory>/scripts/verify_review.py --root <workspace-root>"}'
---

# Patpat Review

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read repository truth, [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), and preserve safety. Apply the [independent review playbook](../patpat-loop/playbooks/independent-review.md).

Remain read-only. Inspect the objective, proof contract, exact diff or artifact, raw verification receipts, and affected contracts. When separate read-only reviewers are available and authorized, split the review across two **parallel fresh (non-forked) contexts** without passing the implementer's intended conclusion, so neither axis cross-contaminates the other:

- **Spec fidelity axis**: Challenges the diff and raw verification receipts against the user objective, proof contract, edge cases, invariants, and the playbook's solution-integrity audit (rejecting evidence laundering, unexplained assertion weakening, hardcoded fixture answers, and proof that bypasses the claimed authoritative surface).
- **Standards compliance axis**: Challenges the diff against repository standards (`CODING_STANDARDS.md`, `AGENTS.md`, local conventions), safety, maintainability, and code-smell heuristics without seeing implementer rationale.

When only one reviewer or a serial pass is available, run both axes as distinct passes and state that they were not independently isolated. For a second opinion or cross-vendor review, use a different vendor than the author (same-vendor families such as Claude and Fable cannot judge each other), and escalate model tier only on user request or after two failed runs of the same brief. Judge each finding on its evidence and impact, not the number of reviewers who reported it. Bucket the synthesized verdict Act on / Consider / Noted / Dismissed. Do not auto-apply.

## Overridable code-smell baseline

On the standards axis, apply this Fowler code-smell baseline as labeled heuristics—explicitly **overridden by repository standards** when present—so reviews stay sharp even without a `CODING_STANDARDS.md`: *Mysterious Name, Duplicated Code, Long Function / Large Class, Feature Envy, Data Clumps, Primitive Obsession, Shotgun Surgery / Divergent Change, Speculative Generality, and Message Chains / Middle Man*. Require a concrete failure input or contract impact for every finding (no concrete case, no finding); recommend splitting code by job, never by line count or into single-caller pass-through wrappers. Treat an explicit `shortcut: <limit>, <when to upgrade>` comment as a deliberate decision, not a finding, unless expected load or current inputs already cross its stated limit. Exclude speculative style preferences.

Bind evidence to the exact candidate revision or reproducible working-tree snapshot; for push-, PR-, or delivery-bound claims, require the committed head or the durable gate in [delivery proof](../patpat-run/references/delivery-proof.md). When a delivery review receipt is required for `verify_review.py`, keep the worktree untouched and record the JSON receipt under Git metadata (`<git-dir>/patpat/review-receipt.json`, or an explicit `--receipt` path outside the repo) rather than dirtying `.patpat/` in the worktree.

## Findings and reporting

Lead every review summary with a **Merge-Danger Callout** (`Door: one-way | two-way` and `Blast Radius`) so human reviewers triage by merge danger before reading line-by-line. When the main issue is a change in shape, prefer a diff-shaped or tree explanation from [earned representation](../patpat-loop/references/earned-representation.md) over long prose. Report findings first, ordered by `blocker`, `high`, `medium`, then `low`. Tie every finding to a file, symbol, behavior, or receipt and explain the concrete impact. Exclude speculative style preferences. For each accepted issue, recommend the smallest safe correction and required re-verification.

State `no findings` only after checking correctness, solution integrity, regressions, contracts, safety, performance implications, side effects, generated noise, and evidence mismatch. Review does not replace verification and never authorizes merge or delivery.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
