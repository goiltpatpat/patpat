# Earn Parallelism

![A proven path passes through a verification gate before helper drones work in three isolated bays and Patpat integrates their components with a reviewer.](./images/earned-parallelism.jpg)

Parallel generation multiplies output. It does not multiply trust. Patpat starts with one reliable end-to-end path and adds concurrency only where ownership and integration proof are explicit.

## Start serial

Run the task through inspection, implementation, verification, and review with one owner. Record the failure modes. Encode recurring failures as constraints or checks. Scale only after the path is repeatably trustworthy.

## Isolate before running concurrently

Writable workers need separate worktrees or host-enforced sandboxes. Each worker receives:

- one bounded brief;
- explicit file ownership;
- a proof surface;
- a return contract;
- no merge authority.

If isolation is unavailable, run the work serially. Locks do not turn a shared mutable worktree into independent evidence.

## Choose the right topology

Record one bounded receipt that binds the program id, validated plan digest, integration owner, every writable gate above, and one unique isolation identity per unit. Pass its absolute path to `patpat-run/scripts/team_shape.py` with observed capacity and a worker budget, then use the same receipt to open the program dispatch gate. Without a valid content-bound receipt it returns serial work and dispatch remains closed. Its non-authoritative recommendation selects the smallest viable topology: `iterative` for a tight test/refine loop, `distributed` for independent slices, or `adversarial` for high-uncertainty candidates that an independent oracle can falsify. Use `arena` for adversarial candidates, `swarm` for distributed coverage, and `autopilot` for a checked queue whose items each close their own proof loop.

Workers return typed cards with scope, proof, receipts, objections, reusable parts, verdict, and next frontier. Preserve those artifacts; discard transcript-shaped context.

Do not use parallelism to hide an unclear contract. Resolve shared shapes and integration boundaries before fan-out.

## Integrate under one owner

The integration owner checks current heads, reconciles overlaps, runs integration proof, and obtains independent review. Worker success is input to integration, not proof of the combined result.

Writable fan-out remains gated until representative behavioral evaluations prove that isolation, aggregation, and serial fallback behave correctly on the active host.

Next: [Extend and evaluate](./08-extend-and-evaluate.md).
