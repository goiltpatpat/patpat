# Statechart Modeling, Runtime, and Bug-Map Guide

Companion reference for [`patpat-statechart`](../SKILL.md). Load when importing from a repository diagram, authoring TLA+ specs/views, troubleshooting runtime setup, or rendering a historical bug map.

## Importing from a repository diagram

When a `patpat-repository-diagram` lifecycle or workflow JSON already exists for the flow:

1. Reuse its state and transition labels as `state()` and `step()` labels.
2. Take each event's file and line range from its `evidence_ids`, and treat workflow lanes as actors.
3. Name each TLA+ action after its diagram transition ID with `-` replaced by `_`.
4. Obtain rules directly from the reader (the diagram holds structure, not rules).

## TLA+ and view authoring rules

Write `SPEC.tla`, `SPEC.cfg`, and an ES module view (e.g., `view.mjs`) in a scratch folder outside the repository. Check the spec against these rules before the first run (each run incurs a TLC startup):

- Add `EXTENDS Naturals` (or `Integers`) whenever using numbers, ranges (`0..2`), `<`, or `>` (missing it causes SANY to fail with a Java stack trace and exit 2).
- Encode every reader rule as an `INVARIANT`; add a model variable if needed, and never weaken a rule to make it pass.
- Write `Next` as a disjunction of named actions (e.g., `YouPressPlay \/ YouPressStop`), otherwise TLC names every step `Next`.
- Prevent false `NoDeadlock` failures on valid terminal states by adding a stuttering action true only in end states (e.g., `Done == phase \in {"paid", "failed"} /\ UNCHANGED vars`) and labeling it in `step()`. When an `INVARIANT` or `PROPERTY` is already named `NoDeadlock`, the deadlock rule is `CHECK_DEADLOCK`.
- In `view.mjs`, `state(vars)` returns reader-visible labels (e.g., `"Paying"`, `"Refunded, screen still says Ready"`), never raw variable names; `step(action, from, to)` returns reader-visible event descriptions (e.g., `"the customer asks for a refund"`), never code or TLA+ identifiers.

## Runtime and platform setup

- **Runtimes**: `scripts/statechart` requires Node 22.18–22.x, Node 23.6+, Bun 1.1.5+, or Deno 2.0+ (Git Bash supported). On Windows `cmd` or PowerShell, run `scripts/statechart.cmd` (requires Node 22.18+ on `PATH`).
- **TLC / Java**: First run installs TLC and Java via `mise` (requires network). Set `TLA2TOOLS` to a pinned `tla2tools.jar` (v1.7.4) to skip `mise`; `JAVA` defaults to `java` on `PATH` (Java 11+).
- **Windows paths**: Java reads arguments in the system ANSI code page; keep specs in a path expressible in that code page.

## Historical bug map

When a project maintains a bug ledger (see [`patpat-formal-verify`](../../patpat-formal-verify/SKILL.md#maintain-the-check)) and the reader asks where the flow has broken over time:

1. Overlay each ledger number onto the current chart state where that bug broke, matching by recorded model or diagram ID (never by label text).
2. Include a numbered legend of reader sentences with replay evidence and fix references.
3. Title the map clearly as authored history (not current checker output), and report any current run's broken rules separately from fixed ledger entries.
4. List removed states in the legend as `state removed` (never place them on a guessed state), and list rows with ID `none` in the legend only as `no chart state`.
5. If the current model is too large to chart, shrink it with a `VIEW` or bounds, or report the legend alone and state why.
