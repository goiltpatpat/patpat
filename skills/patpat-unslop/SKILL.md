---
name: patpat-unslop
description: Cut superficial patterns and fluff from engineering docs, PR text, and code diffs.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"Artifact","requires_state":["workspace-root-open"],"produces_state":["prose-code-unslopped"],"verification_cmd":"git diff | python3 <loaded-skill-directory>/scripts/unslop_ast_check.py --diff"}'
---

# Patpat Unslop

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

Review engineering docs, PR text, and code diffs for fluff and structural bloat while preserving technical meaning and author voice. Scan against the catalog below, propose concrete rewrites, and replace hand-waving with exact symbols, numbers, or references.

## Pattern Catalog

Rule numbers are stable: retired rules leave gaps and are never renumbered so cross-references never shift.

### Content and Substance

1. **Superficial participial clauses.** Cut ungrounded trailing `-ing` clauses (*highlighting, ensuring, reflecting, showcasing, fostering*); state the concrete causal fact.
2. **Vague attributions.** Cut *"Industry standards suggest / Experts believe / Many developers prefer"*; cite the exact spec, RFC, or constraint, or delete.
3. **Empty summary filler.** Cut cheerleading intros/outros (*"In summary, this enhances stability"*, *"It is worth noting..."*); state the fact directly.

### Language and Vocabulary

4. **Inflated vocabulary.** Replace decorative/vague terms only when preserving exact meaning: *additionally*->*also*, *crucial/pivotal*->*required*, *delve*->*inspect*, *enhance*->*improve/name change*, *foster*->*enable*, *intricate*->*complex*, *landscape*->*context*, *underscore*->*show/confirm*; cut decorative *tapestry/testament/vibrant* (keep literal uses).
5. **Fancy copulas.** Replace *"serves as / stands as / boasts / features"* with *"is"* or *"has"*.
6. **False contrasts.** Cut *"Not only X, but also Y"*; state both facts plainly.
7. **Rule-of-three bias.** Use the natural item count; do not pad lists to three.
8. **Synonym cycling.** Keep one canonical domain term per entity (*caller*, not *caller/invoker/consumer*).
9. **Fake ranges.** Replace *"from X to Y"* with an exact list unless X..Y is a continuous scalar range.

### Style and Punctuation

10. **Em dash overuse.** Remove em dashes used only to join clauses; keep them for asides, interruptions, or attributions when clearer.
11. **Excessive bullet nesting.** Prefer flat bullets or code blocks over multi-nested outlines.
12. **Apologetic or sycophantic tone.** Cut *"Certainly!"*, *"I would be happy to..."*, *"You are absolutely right!"*; stay neutral.
13. **Narrative code commentary.** Strip conversational prose from diffs; communicate through types, names, and structure.
14. **Unproven claims.** Never claim a fix works or tests pass without fresh command receipts.

### Code and Comment Discipline

15. **Redundant paraphrasing and compensating comments.** Delete comments that restate code (`// loop over items`). Comments explain *why* or non-obvious constraints only. If a comment compensates for an unclear name or tangled flow, rename or simplify instead.
16. **Dead code and historical commentary.** Delete commented-out code, obsolete workarounds, and apologies (`// hack: fix later`); Git holds history.
17. **Decorative comment dividers.** Remove ASCII banners, `// ====`, and boxes; use blank lines and modules.
18. **Orphaned TODOs.** Delete unanchored `TODO`/`FIXME`s lacking an owner, issue link, or actionable condition. Keep anchored `shortcut: <limit>, <when to upgrade>` comments encoding deliberate bounded trade-offs.
19. **Keep high-value invariants; cut structural bloat.** Keep comments encoding non-obvious *why*, domain invariants, `shortcut: <limit>, <when to upgrade>` limits, concurrency fences, upstream bug URLs/RFCs, or legal notices. Cut single-caller pass-through wrappers, helpers split merely by line count, silent broad catches (`except Exception: pass`), speculative fallback flags, and duplicate helpers.
20. **Anti-reward-hacking and verifier integrity.** Reject test skips (`@pytest.mark.skip`, `test.skip(`, `it.skip(`, `[Fact(Skip=...)]`), linter/warning suppressions (`# noqa`, `// eslint-disable`, `#pragma warning disable`, `// @ts-ignore`), and arbitrary sleeps (`time.sleep(`, `Task.Delay(`) added to force green builds. Fix the defect, never silence the oracle.

## Diataxis mode rule

- One document, one mode: keep `tutorial`, `how-to`, `reference`, and `explanation` separate when pruning or rewriting docs.
- Match tone to mode: keep `reference` dry and factual; let `explanation` state a clear point of view.
- Name exact symbols, flags, and commands throughout so canonical domain terms stay consistent.

## Deterministic AST and comment check

Run [`scripts/unslop_ast_check.py`](scripts/unslop_ast_check.py) for deterministic checking across Rules 12/16 (`ai-conversational-slop`), 19 (`broad-exception-swallowing`, `single-caller-wrapper`), and 20 (`test-skipping-annotation`, `test-skipping-call`, `linter-suppression`), supporting whole paths and `--diff` filtering.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
