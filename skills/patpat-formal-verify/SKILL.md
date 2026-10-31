---
name: patpat-formal-verify
description: Create or maintain a project-local formal verification skill and suite for a costly invariant that ordinary tests may miss. Use for state machines, action ordering, concurrency, retries, fencing, or bounded input properties; use patpat-verifier for real-app behavior and user-surface checks.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Codebase","requires_state":["workspace-root-open"],"produces_state":["formal-model-verified"],"verification_cmd":"python3 skills/patpat-run/scripts/check_assignment_model.py --self-test"}'
---

# Patpat Formal Verify

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [preserve safety](../patpat-loop/principles/preserve-safety.md), and [smallest safe change](../patpat-loop/principles/smallest-safe-change.md).

## Choose the property and method

1. If the user named an area or failure, start there. Otherwise inspect contracts and code to find the highest-cost invariant ordinary checks rarely reach; do not choose a weaker property just because it is easier to model.
2. Name the invariant and the user harm it prevents. Read the authoritative implementation, contract, existing checks, callers, and all relevant mutation boundaries.
3. Choose the smallest method that answers the question. Use a model checker for action ordering and finite transition systems; use a verifier on the implementation for input, memory-safety, overflow, or data-structure properties. For concurrent or distributed protocols, consider TLA+ first. If no code-level verifier fits, use generated inputs against the real implementation as a separate evidence layer; a hand model alone does not verify the function.
4. State what one modeled action means in code. Split a model action when the implementation can interleave at that point. Record bounds, assumptions, omitted behavior, checker/tool version, and the expected counterexample before running anything.
5. If the task only needs example or property-based runtime checks and no formal model or implementation verifier answers a distinct property, route to [`patpat-verify`](../patpat-verify/SKILL.md) or [`patpat-debug`](../patpat-debug/SKILL.md); do not create a formal-verification suite just to host ordinary tests, and do not call those checks formal proofs.

Patpat's core runtime, AST symbol extraction, architecture diagrams, and counterexample replay operate in 100% pure Python 3.10+ standard library with zero external dependencies. Live TLA+/TLC model checking is an optional verification toolchain for exploring new state spaces and requires Java (`tla2tools.jar`). When Java is absent, environments still execute the pure-Python model checker (`check_assignment_model.py`) and counterexample replayer (`replay_assignment_counterexample.py`) to verify existing bounds, state invariants, and runtime replays.

## Create or update the project check

Create a durable project-local formal-verification skill and suite when later changes should rerun the property. For a one-off investigation, keep the check local to that task and do not mint a reusable skill.

1. Find the project's canonical skill tree and host install contract from repository instructions and manifests. Put the skill there; keep model, proof, harness, and small scripts beside it or in the repository's established verification location. Do not invent a competing host path.
2. Write the skill so an agent arriving mid-change can decide whether the code is covered, run the exact command, distinguish a code defect from verification drift, update the check when the contract changes, and report uncovered behavior.
3. Record the claim and harm, covered paths and functions, code-to-model mapping, action granularity, property, bounds, assumptions, tool identity, exact command, interpretation of failures, limitations, and last synchronized commit. Leave no placeholders.
4. Include a targeted mutant for every claimed user-facing property. If the checker also uses auxiliary model-consistency invariants, label their role and either give them a targeted mutant or explain why they add no independent product claim. If claiming correspondence to implementation behavior, also apply a scratch source mutation in an isolated copy or worktree and show the real-code checks catch it. Never mutate the user's live source for this trial. If safe isolation is unavailable, report source-mutation evidence as `INCONCLUSIVE`.
5. Run the repository's skill validator and evaluate one prompt that should route here plus a neighboring prompt that belongs to [`patpat-verifier`](../patpat-verifier/SKILL.md). Structural discovery alone is not proof of prompt-time routing.

## Build and check the property

1. Define states, actions, guards, safety invariants, and any liveness properties. State fairness assumptions only when the environment justifies them.
2. Map every modeled state variable, action, guard, and property to code a reviewer can open. Treat actor identity, authorization, atomicity, and external effects as assumptions unless the covered implementation actually enforces them.
3. Run the unchanged candidate first. Inspect tool identity, process status, explored states or bounds, and all counterexamples. A checker error, skipped property, empty state space, missing input, or surviving mutant is not a pass.
4. Translate each material counterexample into the shortest available numbered action path using terms its consumer can observe. For every step, name the model action, mapped code location, and expected observable state or effect. Replay that path through a real entry point when implementation correspondence is claimed. If no implementation exists or safe replay is unavailable, label the path `model-only` or `replay-inconclusive`; never present it as a reproduced product defect.
5. When a saved model-check receipt would make the finding easier to inspect, use the [statechart receipt contract](statechart/references/receipt-rendering.md) and the [Patpat statechart module](statechart/STATECHART.md). Put the raw checker action and `changed_keys` on each connector or its adjacent receipt evidence; keep semantic descriptions in a separate authored-interpretation annotation. Map each edge to code and an expected effect or state why the receipt cannot support that mapping, and keep bounds, mutant, source mapping, and replay as distinct evidence. A diagram is a presentation of the receipt; it does not replace replay or source-mutation evidence.
6. Require both the property-specific mutant and, when code correspondence is claimed, the isolated source mutant to produce their expected failures. Restore or discard each scratch mutation and rerun the unchanged check.
7. If a counterexample exposes a product defect, preserve it in the report and route the fix through `patpat-debug` or `patpat-change`. Do not weaken the invariant or change product code unless the user asks.
8. Keep model results, implementation tests, source-mutation evidence, and runtime observations as separate evidence layers. A passing model proves only that model within its bounds.

## Maintain the check

Use the nested [statechart module](statechart/STATECHART.md) for native PStack-derived TLA+/TLC diagrams or saved-receipt rendering. The module is maintained with this formal-verification skill so the Patpat skill registry stays canonical; it is not separately auto-discovered. For general repository visuals, use [`patpat-repository-diagram`](../patpat-repository-diagram/SKILL.md).

For later changes, read the recorded sync commit and run the existing check before editing its description. Inspect every commit and working-tree change touching covered code, including moved functions and new writers of guarded state. Compare the model's actions and assumptions with the code, not with commit messages alone. Update the model from the implementation before rerunning; change the property only when a contract change is supported by repository evidence. Never weaken the property to make a failure disappear.

Report one result for each check:

- `in sync`: no covered behavior changed and the current check passes.
- `updated`: the code changed, the verification now describes it, and the required checks pass.
- `bug`: the check describes current code and a reproducible counterexample shows the code violates the unchanged property.
- `blocked`: required evidence, isolation, assumptions, or tools are missing; retain the previous sync commit.

Advance the sync commit only after reviewing the mapped code at that committed revision and rerunning the check and required mutants. For a dirty or uncommitted candidate, record the base commit and identify the working-tree snapshot separately; do not claim that the commit contains the checked candidate.

## Report

Start the report with a Snapshot line naming the base commit, working-tree status, and exact diff digest. A snapshot binding is `PASS` only when the candidate is tied to independently reproducible bytes:

- For a clean committed candidate, record the exact `HEAD` and `git status --short --untracked-files=all` showing no changes.
- For a dirty candidate, record its base, a SHA-256 digest of `git diff --binary <base>`, and paths plus content hashes for every untracked candidate file. Include the command or receipt so a reviewer can reproduce the binding.

If identifiers or a self-reported digest cannot be reproduced from the candidate, mark the binding `INCONCLUSIVE`; supplied identifiers alone never earn `PASS`. Bind any ignored or external input that affects the check separately. If such an input cannot be identified or bound, name the gap and mark the affected claim `INCONCLUSIVE`. Assess product correctness separately. Use a table with exactly one row per checked invariant and these columns: `Invariant`, `Role`, `Meaning`, `Harm or consistency purpose`, `Code/model mapping`, and `Targeted mutant and observed result`. If a table is unsuitable, use one complete labeled list item per invariant with the same fields; do not move required evidence outside its item. Derive each role from the authoritative project contract, not the invariant name. In the Code/model mapping cell, use separate `Model:` and `Implementation:` labels. Identify the model property or formula and cite the mapped implementation path and function when the source provides one; otherwise write `Implementation: model-only — <reason no code mapping is documented>` or `Implementation: INCONCLUSIVE — <missing evidence>` and name the limit. For an invariant with no targeted mutant, write `none`. For each auxiliary invariant, state in its row whether it is a separate product guarantee; follow the source contract when it says the auxiliary invariant is not an implementation guarantee. For each product property, put its targeted mutant and observed counterexample count in the same row or item. Copy the full checker-version string and artifact digest from the current receipt. Do not omit a field for brevity; when the evidence packet does not support a field, mark that field `INCONCLUSIVE` and name the missing evidence. Then report bounds and assumptions, overall result, numbered counterexample path, replay status, source-mutation result, sync commit, cleanup, and uncovered behavior. Say plainly which layer passed and which remains unproven.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
