---
name: patpat-change
description: Implement one bounded repository change with a small diff and explicit proof. Use for clear features, localized refactors, and requested fixes after the root cause or design is known.
---

# Patpat Change

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), [preserve safety](../patpat-loop/principles/preserve-safety.md), and [proof over proxy](../patpat-loop/principles/proof-over-proxy.md). Apply the [bounded change playbook](../patpat-loop/playbooks/bounded-change.md).

For a behavior-preserving rename, move, extraction, inline, or deduplication, apply the [behavior-preserving refactor playbook](../patpat-loop/playbooks/behavior-preserving-refactor.md). When the user requests test-first work or a cheap deterministic regression target exists, apply [regression first](../patpat-loop/playbooks/regression-first.md).

For an explicit visual migration or pixel-equivalence claim, apply the [visual equivalence playbook](../patpat-loop/playbooks/visual-equivalence.md) without weakening its baseline or comparison harness.

Inspect version-control state and nearby contracts before editing. Define the proof contract. Make one coherent repository-native patch. Avoid unrelated cleanup, speculative abstractions, new dependencies, and public interface changes unless the objective requires them.

Do not claim completion from generation, compilation, or tests alone when the changed behavior has an observable surface.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
