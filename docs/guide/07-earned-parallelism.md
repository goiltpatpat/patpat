# Earn Parallelism

![One trusted path passes a verification gate before splitting into three isolated workspaces and recombining under one review owner.](./images/earned-parallelism.jpg)

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

Use `arena` when multiple isolated attempts solve the same brief and one result will become the base. Use `swarm` when independent slices or declared race arms cover different surfaces. Use `autopilot` for a checked queue whose items each close their own proof loop.

Do not use parallelism to hide an unclear contract. Resolve shared shapes and integration boundaries before fan-out.

## Integrate under one owner

The integration owner checks current heads, reconciles overlaps, runs integration proof, and obtains independent review. Worker success is input to integration, not proof of the combined result.

Writable fan-out remains gated until representative behavioral evaluations prove that isolation, aggregation, and serial fallback behave correctly on the active host.

Next: [Extend and evaluate](./08-extend-and-evaluate.md).
