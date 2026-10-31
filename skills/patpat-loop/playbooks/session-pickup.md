# Session Pickup Playbook

Read [repository truth](../principles/repository-truth.md), [guard the context window](../principles/guard-the-context-window.md), and [smallest safe change](../principles/smallest-safe-change.md).

Use this playbook when picking up or continuing in-flight work in an active workspace with minimal latency and zero friction.

## Rapid State Re-synchronization

1. **Working Tree Probe**: Run `git status --short` and `git rev-parse HEAD` immediately to ground current repository state without reading large diffs.
2. **Run Store Validation**: If a `.patpat/run/` state exists, load `program_state.json` directly. Check for uncommitted checkpoints or pending gates (`dispatch`, `delivery`).
3. **Evidence Freshness Check**: Verify whether previous test or build receipts match the current HEAD SHA. Never re-execute long test suites if HEAD and untracked surfaces are unchanged.
4. **Context Window Protection**: Do not replay long conversational histories or paste old subagent logs into context. Synthesize the immediate objective in three bullets:
   - Current Phase / Gate
   - Completed Verifications
   - Single Next Action
5. **Resume Execution**: Enter the active workflow graph directly at the earliest incomplete node.
