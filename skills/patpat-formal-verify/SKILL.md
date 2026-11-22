---
name: patpat-formal-verify
description: Create or maintain a project-local formal verification suite for costly state, ordering, or concurrency invariants.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Codebase","requires_state":["workspace-root-open"],"produces_state":["formal-model-verified"],"verification_cmd":"python3 skills/patpat-run/scripts/check_assignment_model.py --pure-python"}'
---

# Patpat Formal Verify

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full without loading the router. Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), preserve safety, and smallest safe change.

## Choose the property and method

1. Target the user-named failure or the highest-cost invariant ordinary checks miss; keep the property strong rather than simplifying it for convenience.
2. Read the authoritative implementation, contract, checks, callers, and mutation boundaries. Write each property as one user-agreeable sentence naming the invariant and prevented harm. Label it `reader-confirmed` when stated in a user/human-approved contract, otherwise `agent-derived` (which persists across tasks until confirmed; show it in the user's terms before gating a claim and report unconfirmed results as conformance to an unconfirmed spec).
3. Pick the smallest fitting method: model checker (TLA+ first for concurrent/distributed protocols) for action ordering and finite transition systems; implementation verifier for input, memory-safety, overflow, or data-structure invariants; generated inputs against real code as a separate layer when no code-level verifier fits. Route ordinary runtime/property-based tests to [`patpat-verify`](../patpat-verify/SKILL.md) or [`patpat-debug`](../patpat-debug/SKILL.md).
4. Split modeled actions wherever the implementation can interleave. Record bounds, assumptions, omitted behavior, tool version, and expected counterexample before running.

## Create or update the project check

For durable project-local suites, follow [suite, ledger, and report contract](references/suite-and-report-contract.md) (toolchain notes, canonical skill placement, zero-placeholder metadata, targeted property mutants, isolated scratch source-mutation trials, and routing checks against [`patpat-verifier`](../patpat-verifier/SKILL.md)). Keep one-off investigations local to the task.

## Build and check the property

1. Define states, actions, guards, safety invariants, and justified fairness assumptions. Map every modeled variable, action, guard, and property to reviewable code; treat unverified actor identity, auth, atomicity, and external effects as assumptions.
2. Run the unchanged candidate first and inspect tool identity, status, explored bounds, and counterexamples. Checker errors, skipped properties, empty state spaces, missing inputs, or surviving mutants fail the check.
3. Translate each material counterexample into the shortest available numbered action path using terms its consumer can observe. For every step, name the model action, mapped code location, and expected observable state or effect. Replay through a real entry point when claiming code correspondence; otherwise label the path `model-only` or `replay-inconclusive` and never present it as a reproduced product defect.
4. For saved model-check receipts, render via [statechart receipt contract](../patpat-statechart/references/receipt-rendering.md) and [`patpat-statechart`](../patpat-statechart/SKILL.md), separating raw checker actions/`changed_keys` from authored interpretation.
5. Require both the property-specific mutant and (when claiming code correspondence) isolated source mutant to fail as expected, then restore scratch mutations and rerun the unchanged check.
6. Route confirmed product defects to `patpat-debug` or `patpat-change` without weakening invariants or editing product code unasked. Report model results, tests, source-mutation evidence, and runtime observations as separate layers.

## Maintain the check

Read TLA+/TLC results through [`patpat-statechart`](../patpat-statechart/SKILL.md) (name it in project skills rather than copying commands); use [`patpat-repository-diagram`](../patpat-repository-diagram/SKILL.md) for general repository visuals.

On subsequent changes, read the recorded sync commit, run the existing check first, and compare model actions/assumptions against actual code diffs touching covered paths (including moved functions and new state writers). Update the model from code before rerunning; change properties only on evidenced contract changes. Report one status per check: `in sync`, `updated`, `bug`, or `blocked` (retaining the prior sync commit when blocked). Maintain an append-only bug ledger per [suite, ledger, and report contract](references/suite-and-report-contract.md#bug-ledger-contract). Advance the sync commit only after reviewing mapped code at that committed revision and rerunning checks and mutants.

## Report

Start the report with a Snapshot line naming the base commit, working-tree status, and exact diff digest. A snapshot binding is `PASS` only when the candidate is tied to independently reproducible bytes:

- For a clean committed candidate, record the exact `HEAD` and `git status --short --untracked-files=all` showing no changes.
- For a dirty candidate, record its base, a SHA-256 digest of `git diff --binary <base>`, and paths plus content hashes for every untracked candidate file. Include the command or receipt so a reviewer can reproduce the binding.

If identifiers or a self-reported digest cannot be reproduced from the candidate, mark the binding `INCONCLUSIVE`; supplied identifiers alone never earn `PASS`. Bind any ignored or external input that affects the check separately. If such an input cannot be identified or bound, name the gap and mark the affected claim `INCONCLUSIVE`.

Format the invariant table (`Invariant`, `Role`, `Meaning`, `Harm or consistency purpose`, `Code/model mapping`, `Targeted mutant and observed result`) and remaining evidence fields per [invariant report table schema](references/suite-and-report-contract.md#invariant-report-table-schema).

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
