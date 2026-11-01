# Session Pickup Playbook

Read [repository truth](../principles/repository-truth.md), [guard the context window](../principles/guard-the-context-window.md), and [smallest safe change](../principles/smallest-safe-change.md).

Use this playbook when picking up or continuing in-flight work in an active workspace with minimal latency and zero friction.

## Rapid State Re-synchronization

1. **Working Tree Probe**: Run `git status --short` and `git rev-parse HEAD` immediately to ground current repository state without reading large diffs.
2. **Run Store Validation**: Durable state lives in Git metadata, not the worktree: `git rev-parse --git-path patpat/runs` and `git rev-parse --git-path patpat/programs`, with one `<id>/state.json` per run or program. Each linked worktree has its own store, so an empty result in one worktree says nothing about another. Read state through [`run_state.py`](../../patpat-run/scripts/run_state.py) `status --run-id <id>` or [`program_state.py`](../../patpat-run/scripts/program_state.py) `--program <id> status --brief`. Check for checkpoints and pending gates (`pre-edit`, `verify`, `commit`, `ship`, `merge` for runs; `dispatch`, `delivery` for programs).
3. **Evidence Freshness Check**: `validate` checks structure and does not prove every receipt fresh. For a run, require `run_state.py check-gate --run-id <id> --gate verify`, or, when review must also be current, `--gate commit` for staged proven content and `--gate ship` for a clean head. For a program, read `head_sha`, `verification_fresh`, and `review_fresh` from `program_state.py --program <id> status --unit <unit>`, and also require that `head_sha` equals the live HEAD with a clean `git status`, because program verdicts bind the recorded head and do not see later commits or edits. Other test or build evidence may guide the next step only when HEAD, staged and unstaged tracked changes, untracked surfaces, and material inputs and environment all match what it ran against. Report it as reused evidence, and rerun the authoritative check before claiming `verified`.
4. **Context Window Protection**: Do not replay long conversational histories or paste old subagent logs into context. Synthesize the immediate objective in three bullets:
   - Current Phase / Gate
   - Completed Verifications
   - Single Next Action
5. **Resume Execution**: Enter the active workflow graph directly at the earliest incomplete node.
