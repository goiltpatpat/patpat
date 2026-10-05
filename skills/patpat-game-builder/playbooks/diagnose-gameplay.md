# Diagnose Gameplay Behavior

Use this playbook for a mechanic that fails while building or extending a game slice. For a standalone reproducible defect in an existing project, use [patpat-debug](../../patpat-debug/SKILL.md) as the owner and apply this game-specific evidence where useful.

1. Freeze the failing action sequence, expected result, actual result, starting state, target runtime, and random seed or replay input when applicable. Reproduce it on the real project when safe.
2. Classify the first failing boundary: launch or resource load, input mapping, rule evaluation, state transition, timing or collision, feedback, or terminal/reset behavior.
3. Compare the earliest observable state that diverges from the acceptance condition. Use existing logs, tests, replays, and runtime inspectors first. Add instrumentation only when it reveals a named unknown; remove it after proof.
4. State one causal hypothesis and the observation that would falsify it. Change one cause at a time. Do not hide a rule failure with a presentation change, or a visual symptom with score tuning.
5. Replay the same action sequence after the correction, then exercise one normal neighboring path to check for regression. Recheck any dependent invariant the patch changes.
6. If two corrections based on the same assumption fail the same condition, test the assumption or inspect the first divergent state before another patch.

If the target runtime or reproducible input is unavailable, stop at code-path or rule evidence and report the missing player-surface proof. Do not substitute a sample game, mock input, or a passing unit test and call the result fixed.
