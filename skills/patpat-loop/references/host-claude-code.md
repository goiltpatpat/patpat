# Claude Code Host Map

Read this once per session when the host is Claude Code (CLI, desktop, IDE, or `claude -p`). It maps Patpat's host-neutral terms to Claude Code surfaces. It grants no authority beyond the [operating protocol](operating-protocol.md).

## Skills

- The plugin namespace is `patpat`, so the entry is `/patpat:patpat`. `.claude-plugin/plugin.json` keeps that name when the plugin loads through `--plugin-dir` from a directory with any name.
- Specialist skills carry `disable-model-invocation: true`. Claude Code does not offer them to the model's `Skill` tool. This was observed in a desktop session with 0.8.1-a, where only the unflagged skills appeared in the model's skill list. Compose a specialist by reading its `SKILL.md` with `Read`, resolving the relative link from this skill's base directory or from `${CLAUDE_PLUGIN_ROOT}/skills/<name>/SKILL.md`. Do not retry the `Skill` tool for them.
- When you tell the user to run a specialist directly, write `/patpat:<name>`.

## Task list and questions

- Put playbook steps in the host task list: `TodoWrite`, or the app's plan tool when the desktop app provides one. Do not keep a second list in prose. The desktop plan tool caps step length, so shorten each step's wording there while keeping the playbook's order and step count.
- Ask a human-only question with `AskUserQuestion`. `claude -p` has no interactive user. There, do not wait. Take the most reversible option, record it as an `inferred` assumption in the report, and stop before any action that needs human authority.
- In plan mode, stay in FRAME, INSPECT, and PROOF CONTRACT. Mutate only after the user accepts the plan.

## Workers

| Patpat term | Claude Code |
| --- | --- |
| Independent reviewer | `Agent` with `subagent_type: "patpat:patpat-reviewer"` (read-only `Read`, `Grep`, `Glob`). Brief it with the claim, the changed paths, and the evidence paths, not your transcript. |
| Read-only investigator | `Agent` with `subagent_type: "Explore"`. The brief says "do not edit files". Check `git status` afterward. |
| Writable worker with its own worktree | `Agent` with `isolation: "worktree"`. This gives a separate checkout and Git index. Process, port, key, and external-resource isolation are not implied. Prove them before the earned-parallelism gate passes. |
| Model per role | `model: "opus"`, `"sonnet"`, or `"haiku"`, following [patpat-setup](../../patpat-setup/SKILL.md) guidance. Omit `model` to inherit the session model. |

A worker's report is a candidate; verify it yourself before reporting.

## Sticky mode and hooks

The bundled `UserPromptSubmit` hook was observed dispatching on Claude Code 2.1.296 and 2.1.319 with `--plugin-dir`: an activating prompt returns `hookSpecificOutput.additionalContext` in the same session. The `SessionStart` (`resume|compact`) hook has not been observed. A trusted receipt is present only when that context appears in your session. Otherwise report `current-turn-only` after a restart, as the loop requires.

## Delivery

A repository rule about commit or PR attribution overrides the host's default attribution text.
