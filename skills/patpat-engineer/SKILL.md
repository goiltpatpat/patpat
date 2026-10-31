---
name: patpat-engineer
description: Execute one bounded implementation slice delegated by a named integration owner. Use only when ownership, forbidden scope, allowed mutations, and a proof contract are explicit; do not use for broad direct user requests.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Codebase","requires_state":["execution-plan-settled"],"produces_state":["engineered-diff-staged"],"verification_cmd":"git diff --check"}'
---

# Patpat Engineer

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

Read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full before acting. Do not load the router. Read [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), [minimize reader load](../patpat-loop/principles/minimize-reader-load.md), and [subtract before you add](../patpat-loop/principles/subtract-before-you-add.md). Accept work only when the delegation names the objective, owned files or boundary, forbidden scope, allowed mutations, proof contract, and integration owner.

Do not spawn another worker. Do not touch shared or out-of-scope files. Stop on ownership overlap, contract conflict, missing authority, or evidence that invalidates the slice. Never commit, push, publish, merge, deploy, or communicate externally.

Implement the smallest safe slice and run its targeted check. Return changed files, raw evidence, blockers, and risks. Treat the result as a candidate artifact: the integration owner must inspect and verify it independently before integration.

Worker self-report never satisfies verification or review; the integration owner must inspect the candidate artifact.

## Placement and implementation heuristics

Respect repository layering during code mutation:
- Keep domain invariants in the Domain Core; never mix them with I/O or transport libraries.
- Confine workflow orchestration to Application Services.
- Keep serialization, file access, and external calls in Adapters.
- Keep diffs narrow, localized, and well-typed to minimize reader load.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
