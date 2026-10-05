# Build a Playable Slice

Read [gameplay contract](../principles/gameplay-contract.md) and the applicable rows in the [gameplay validation matrix](../references/gameplay-validation-matrix.md).

## Establish the target

1. Read repository instructions and inspect Git status. Locate the actual engine and version, entry scene or boot path, input bindings, nearby gameplay, assets, and available launch and test commands. Preserve uncommitted user work.
2. Trace the requested behavior through the existing project: entry point → player action → rule → state transition → feedback → outcome. Find the smallest existing extension point.
3. Convert the brief into a short acceptance list: player, target platform, input, action, rule or challenge, feedback, outcome, and explicit constraints. Include visual, performance, save, or network requirements only when requested or necessary to the behavior.
4. Use the real launch command found in project instructions, scripts, manifests, or engine configuration. Do not invent a command.
5. Ask one focused question only when an unresolved choice materially changes platform, engine, control scheme, rules, asset rights, persistence, networking, or external authority. Otherwise state the smallest safe assumption and proceed.

## Shape and implement

1. Choose the smallest end-to-end slice that exercises the requested decision or action. Avoid isolated mechanics that cannot reach visible feedback or an outcome.
2. Sketch the relevant state transitions and invariants before coding. Cover only the states needed by the acceptance list; do not introduce an architecture layer solely for hypothetical future content.
3. Reuse the project's input, scene, UI, asset, and test patterns. Choose a new engine only if the user specified it or the existing project cannot satisfy the target. For a new project, use a supported runtime already available in the workspace and explain why it fits.
4. Implement rule and feedback together. Keep controls functional, status legible, and success, failure, pause, or replay paths reachable when they are in scope. Placeholder art is acceptable only when the user did not request finished visuals and the placeholder does not hide the mechanic.
5. For each deterministic rule change, write one focused behavior check in the project's existing harness when practicable. Run it to establish the expected failing assertion, implement only enough to satisfy that invariant, then rerun it before starting the next slice. Do not batch speculative tests or test private implementation details. If timing, physics, input feel, or another rule cannot be represented by the harness, state why; keep the actual target-runtime playthrough as a separate gate. Use seeded randomness only when needed to reproduce a rule.
6. Use existing or user-provided assets when suitable. Before adding external assets, verify their source, license, attribution, and rights for the intended use and distribution. Record the source, license, and required attribution or redistribution terms in the project's existing asset manifest or credits file. If none exists, add only the smallest provenance entry needed for those assets. If rights are unclear, do not include the asset. Inspect scripts, plugins, and native binaries from asset packs before importing or running them.
7. Do not upload project data, publish, buy assets, create accounts, or enable online services without explicit authority.

## Integrate and hand off

Run focused checks and the exact project launch path. Follow [verify a playthrough](verify-playthrough.md); add [visual iteration](visual-iteration.md) only when required by the brief. If behavior is broken, follow [diagnose gameplay behavior](diagnose-gameplay.md) before another similar patch.

Report the game loop, controls, changed files, exact launch command, evidence by gate, and open limitations. Do not describe a runnable slice as a complete game unless the requested scope is complete.
