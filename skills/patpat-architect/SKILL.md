---
name: patpat-architect
description: Design repository-native architecture, migrations, and contracts before coding, or run a read-only opportunity scan.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"Codebase","requires_state":["workspace-root-open"],"produces_state":["architecture-design-settled"],"verification_cmd":"git diff --name-only"}'
---

# Patpat Architect

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), [preserve safety](../patpat-loop/principles/preserve-safety.md), [subtract before you add](../patpat-loop/principles/subtract-before-you-add.md), [attack the premise](../patpat-loop/principles/attack-the-premise.md), and [redesign from first principles](../patpat-loop/principles/redesign-from-first-principles.md). Apply the [architecture change playbook](../patpat-loop/playbooks/architecture-change.md).

## Core Selection Flow

1. **Trace & sharpen**: ground the design in live repository evidence—contract, callers, changed behavior, migration/compatibility risk, rollback path, and proof contract. Run two blind-spot checks: *(1) What would a top domain specialist check here that wasn't asked?* *(2) Which exact method or tool settles this?*
2. **Pre-Code Frontier Interview**: separate **Facts** (agent's job—inspect code or dispatch a read-only subagent) from **Decisions** (user's job). Compute the **decision frontier** (all unresolved decisions with settled prerequisites), ask the full frontier in one batch with recommended defaults worded so `"yes"` accepts, and proceed once the frontier is empty and shared understanding is confirmed.
3. **Sketch two shapes** (or 2–4 genuinely divergent orthogonal shapes): *minimal interface* (1–3 narrow entry points), *maximum flexibility* (composable primitives), *common-caller ergonomics* (80% happy path), or *ports and adapters* (strict core/I/O seam).
4. **Pick the winner**: choose **one owner per piece of state, one way to do each task, and the least for callers to know**—scored on **Depth** (high capability-to-interface ratio; prefer deep modules over shallow wrappers), **Locality** (co-locate what changes together), and **Seam** quality (testable, swappable boundary).
5. **Route large or contested designs** to [`patpat-arena`](../patpat-arena/SKILL.md). Keep smaller local changes on the bounded-change path.

**Prototype first:** when an observable experiment can settle a fork (latency, integration, failure mode, ergonomics), run the [prototype playbook](../patpat-loop/playbooks/prototype.md) in an isolated disposable scratch area and recommend from evidence instead of guessing. Escalate to the user only for product preferences, authority boundaries, or irreversible trade-offs.

## Deep Modules & Layering

Use **Deep Modules** terms: *Module* (hides complexity behind a clear boundary), *Interface* (narrow public surface), *Implementation* (hidden mechanics), *Adapter* (thin boundary translator), *Depth* (capability-to-interface ratio), *Seam* (test/substitution boundary).

Keep dependencies pointing inward across unidirectional layers:
- **Domain Core**: pure entities, state transitions, invariants (no framework, transport, or I/O dependencies).
- **Application Services**: use cases, command dispatchers, orchestration.
- **Adapters**: CLI parsers, HTTP/API clients, storage, external providers.

## Deliverables & Discovery

Write designs and trade-offs to a persistent artifact (`docs/designs/` or harness artifact dir); keep chat to the artifact path, executive summary, and open user decisions. Apply the **No-Stale-Paths** spec rule: omit volatile file paths and code snippets except decision-rich state machines, schemas, or type shapes trimmed to essentials. Gate ADRs strictly on all three criteria: **hard to reverse + surprising without context + real trade-off**. For auth, security, billing, or tenant boundaries, explicitly check whether the invariant can be encoded as a compile-time witness/guard type or unbypassable constructor so future edits fail to compile rather than relying on tests or prose. Include: caller usage sketch, core data/type shape, boundary signatures, failure modes, rejected alternatives, proof contract, and a compact before/after from [earned representation](../patpat-loop/references/earned-representation.md), plus a verification sequence:

```text
1. <step> -> verify: <targeted check or observation>
2. <step> -> verify: <targeted check or observation>
```

If implementation later needs an unplanned parameter, state escape hatch, or compatibility path, stop and revisit the sketch first. Require independent review and explicit approval before auth, billing, permissions, destructive migrations, production infra, or public contract changes. When designing CI, release, or deployment pipelines, align with [CI/CD Pipeline Design](../patpat-ship/references/cicd-design.md).

For open-ended architecture-opportunity scans (only when requested, never as an automatic prelude), run the bounded discovery route in [architecture change](../patpat-loop/playbooks/architecture-change.md), return <=3 source-backed candidates (friction, proposed boundary, test payoff, confidence), and stop for user selection.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
