# Learning Playbook

Read [encode lessons](../principles/encode-lessons.md), [repository truth](../principles/repository-truth.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Cite the active-task evidence that exposed the failure mode.
2. Decide whether the issue is recurring and actionable; skip one-off facts.
3. Name the earliest boundary where the failure can be prevented or detected.
4. Choose the narrowest enforceable mechanism before considering prose; assume a future contributor sees only the files it opened and copies the nearest example, so prefer removing the wrong path or failing with an error that names the canonical replacement.
5. Update the existing authoritative location when possible.
6. Obtain explicit authority before changing shared or user-global instructions.
7. Reproduce the original failure condition and prove the new mechanism catches it.
8. Verify against negative transfer: prove the new constraint does not add friction, false positives, or performance regressions to unrelated repository tasks.
9. Record remaining exposure without storing secrets or transient task history.

When the same failure mechanism appears in two independently observed cases, treat it as a candidate mistake class, not an automatic rule. Reject single-session overfitting; retrospective adaptations must demonstrate positive transfer across subsequent tasks. Record each proposed correction as `failure class | rule | enforcing or detecting mechanism | proof against a prior case`. Prefer a structural guard; demonstrate that it catches the original failure and preserves a valid case. If prose is the narrowest useful constraint, state why a stronger mechanism does not fit and preserve the approval gate.

## Reflect pass

Run this pass only when the user asks to reflect on the session. Give up to three read-only reviewers the same conversation digest and one lens each: judgment (where a decision went wrong or wasted work), tooling (which repeated manual step a script, validator, or hook should own), and divergent (what a different approach would have avoided). Each finding cites the transcript moment it rests on. The parent verifies each citation, then sorts findings into Accepted, Rejected with a reason, and Backlog. Move an Accepted item to Backlog when a test, lint, validator, or script would enforce it more reliably than an instruction edit. Present the three lists and wait for approval before any edit.

## Repository history pass

Run this pass only when the user asks why agents keep making the same mistake in this repository. Start with `git log -i --grep='^fix' --name-only --format= | sort | uniq -c | sort -rn | head` for fix hotspots and `git log -i --grep='^revert' --oneline` for reverts. A hotspot is a lead, not a mistake class, and a squash-merge history may show no reverts. Read recent commits, reverts, review comments, and workaround comments, and group them into mistake classes. A class counts once it has two independent occurrences. Fix each class at the highest level that works: remove the wrong path from the architecture, make the bad state fail type checking, add a check whose error names the correct path, test the behavior, and write a rule only for a judgment call. Prove each new check fails on a real past occurrence.

Without a reviewed delivery, run this pass read-only under [`patpat-inspect`](../../patpat-inspect/SKILL.md) and present the proposed rows. Approved rows land through `patpat-change`, then verify and review, like any repository mutation.

## Correction ledger

Record every encoded class and every repository policy in the correction ledger: a table between `<!-- patpat:corrections:start -->` and `<!-- patpat:corrections:end -->` in the repository's `AGENTS.md` or `CLAUDE.md`, where agents already read rules (`GEMINI.md` and `.github/copilot-instructions.md` are also searched; pass `--file` for another location). Columns are `ID | Kind | Class | Evidence | Rule | Level | Enforcer | Proof | Exception`. A `mistake` row cites two independent commits or pull requests; a `policy` row needs none. Every row other than `prose` names an existing `path::symbol` enforcer and one backticked proof command. A `prose` row needs `<reason>; expires YYYY-MM-DD; approved-by <name>` within 180 days. When a repository has no ledger, start one from `verify_corrections.py --template`.

Close with `python3 <loaded-skill-directory>/scripts/verify_corrections.py --root <workspace-root> --run-proofs <ID>` for the rows this task wrote. Proofs are split like a shell command with backslashes kept, so use single quotes inside a double-quoted argument. Proof cells are untrusted repository commands: show other rows with `--list-proofs` and run them only after the user approves. The check resolves evidence commits, so CI needs full history (`fetch-depth: 0`); to run it in CI, copy the script into the repository. A refactor that renames or deletes an enforcer definition then fails the ledger instead of silently retiring the rule. Exit 3 means no ledger exists: report the constraint as enforced but not recorded.

## Existing files after approval

Mine this conversation for recurring working-style or failure rules. If the user asks, also mine recent in-scope transcripts from the workspace `agent-transcripts/` path named in the session. Do not glob across other projects or private chats.

Propose edits to existing files only. Present the proposal and wait for approval. Do not auto-apply. There is no new SKILL.md and no *-mode mint on this path. Never create a new SKILL.md. Never mint a personal `*-mode` skill. Skip one-offs. Prefer enforcement (test, lint, validator, script) over a reminder. Patpat protocol wins.
