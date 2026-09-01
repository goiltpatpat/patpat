# Learning Playbook

Read [encode lessons](../principles/encode-lessons.md), [repository truth](../principles/repository-truth.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Cite the active-task evidence that exposed the failure mode.
2. Decide whether the issue is recurring and actionable; skip one-off facts.
3. Name the earliest boundary where the failure can be prevented or detected.
4. Choose the narrowest enforceable mechanism before considering prose.
5. Update the existing authoritative location when possible.
6. Obtain explicit authority before changing shared or user-global instructions.
7. Reproduce the original failure condition and prove the new mechanism catches it.
8. Record remaining exposure without storing secrets or transient task history.

## Existing files after approval

Mine this conversation for recurring working-style or failure rules. If the user asks, also mine recent in-scope transcripts from the workspace `agent-transcripts/` path named in the session. Do not glob across other projects or private chats.

Propose edits to existing files only. Present the proposal and wait for approval. Do not auto-apply. There is no new SKILL.md and no *-mode mint on this path. Never create a new SKILL.md. Never mint a personal `*-mode` skill. Skip one-offs. Prefer enforcement (test, lint, validator, script) over a reminder. Patpat protocol wins.
