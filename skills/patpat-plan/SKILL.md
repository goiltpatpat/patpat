---
name: patpat-plan
description: Design a falsifiable, multi-phase workflow with sequenced contracts and verification surfaces without editing.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"EngineeringTask","requires_state":["architecture-design-settled"],"produces_state":["execution-plan-settled"],"verification_cmd":"python3 <loaded-skill-directory>/scripts/verify_plan.py --root <workspace-root>"}'
---

# Patpat Plan

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read repository truth, [sequence verifiable units](../patpat-loop/principles/sequence-verifiable-units.md), and apply the [bespoke workflow playbook](../patpat-loop/playbooks/bespoke-workflow.md).

Resolve unknowns from repository evidence first; ask only questions whose answers change the contract, sequence, or acceptance.

## 5-Step Multi-Phase Plan

1. **Skip rule**: skip multi-phase planning for small, single-unit changes—route directly to `patpat-change` or `patpat-debug`.
2. **Prototype first**: when an observable experiment can settle an open design or sequencing question, run a disposable scratch prototype before locking the plan.
3. **Write one plan file**: define one falsifiable completion predicate, landing order, dependency graph, and one checkbox section per PR/verifiable unit (each independently returning to a verified state, with rollback hooks, unresolved facts, and authority gates).
4. **Add verification boxes**: include explicit **unit**, **live**, and **perf** verification checkboxes (marking N/A only when genuinely inapplicable) on every phase/PR section.
5. **Stop before execution**: remain read-only; present the plan and smallest safe first unit, and hand execution to the matched specialist or `patpat-run`—never implement inside this skill.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
