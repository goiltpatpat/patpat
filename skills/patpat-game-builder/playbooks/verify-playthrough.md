# Verify a Playthrough

Bind every claim to the current project snapshot, target runtime, and an observable result. Read only the relevant rows from the [gameplay validation matrix](../references/gameplay-validation-matrix.md).

## Separate the evidence

| Gate | Evidence | Does not prove |
| --- | --- | --- |
| Parse, import, or build | The project passes the selected engine processing step or launches to the checked point. | Correct rules, usable controls, or a complete game loop. |
| Rule | Focused tests or runtime assertions cover the named state transitions and boundaries. | Integration with the actual controls, rendering, or target platform. |
| Playable | Real player input through the target runtime produces the requested feedback and outcome. | Visual quality beyond the states and sizes observed. |
| Visual | A current capture from that runtime meets frozen visual conditions at the requested size and state. | Interactive correctness, fun, balance, or untested platforms. |
| Performance | A measured build meets the user's named target and workload. | Other workloads, hardware, platforms, or release readiness. |
| Package or export | The exact target artifact starts and includes the resources required by the requested path. | Store readiness, other platforms, or untested runtime behavior. |

For claims about difficulty, balance, feel, or fun, name the intended player group, relevant scenario, and observable question before evaluation. A balance claim needs a stated comparison or baseline. Use play from that group when authorized and available, and record only observations or feedback tied to the question. Agent-controlled play can prove that a path works, not how the intended player experiences it. Scope conclusions to the players and scenarios observed. If this evidence is unavailable, mark that claim unverified and name the gap.

## Run the declared path

1. Confirm the exact project launcher and runtime version from repository evidence. Record the command, source revision, platform, viewport, and input device. For a dirty worktree, identify which changed source, asset, and configuration files were included in the run.
2. Run existing focused rule checks before opening the game. If the project has no suitable harness, add a small check only when it fits project conventions; otherwise report the gap and rely on the direct playthrough for the behavior it can prove.
3. Launch the actual project through its intended entry point. Use keyboard, pointer, touch, controller, or requested input through the runtime interface, not direct state mutation in place of player action.
4. Exercise the acceptance path: valid start → requested input → visible or audible response → expected state change → relevant boundary → requested success, failure, pause, or replay path.
5. Inspect runtime output for errors, missing resources, and unexpected state transitions during that path. Test another platform or viewport only when it is requested or material to the claim.
6. Capture visual evidence only when it is part of the acceptance contract, then use [visual iteration](visual-iteration.md) for inspection.

Use an existing project harness or runtime inspector when available; never make a new CLI, MCP, daemon, plugin, or dependency a prerequisite for Patpat. A headless run can support rule evidence but does not replace player input.

If the target path is unavailable, try at most one distinct, already-installed path that proves the same target. Stop on the same sandbox or permission failure. Preserve host protections, stop runtime sessions after use, and report the gate as partially verified or inconclusive. Do not claim playable from compilation alone.

Any relevant code, asset, configuration, or runtime change after a check makes that gate's evidence stale. Re-run the affected gate before using the result.
