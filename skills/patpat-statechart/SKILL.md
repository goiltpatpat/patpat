---
name: patpat-statechart
description: Model a flow's states, check its rules with TLA+/TLC, and render broken rules as Mermaid statechart paths.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Artifact","requires_state":["workspace-root-open"],"produces_state":[],"verification_cmd":""}'
---

# Patpat Statechart

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

Answer one reader's question in their words: can this flow reach a state that breaks a rule they care about?

## Choose the route

- **Use here**: Behavior over time where a rule must be checked (stuck states, double-charge, invalid handoff). Keep runs ephemeral in scratch or `/tmp/` and report rules, bug paths, and Mermaid in chat; never write statechart runs or dashboards into `docs/diagrams/`.
- **Structure without rule-checking**: Route to [`patpat-repository-diagram`](../patpat-repository-diagram/SKILL.md).
- **Durable project suite**: Route to [`patpat-formal-verify`](../patpat-formal-verify/SKILL.md) (which sends its TLA+ results back here).
- **Saved `patpat-model-check-receipt` without running TLC**: Follow [`references/receipt-rendering.md`](references/receipt-rendering.md).

## Frame

1. Name the reader and write each rule as one user-agreeable sentence; ask only when a rule is an unsettled product choice.
2. List actors and events (citing owning file and function for code flows; if a `patpat-repository-diagram` JSON exists, import it per [`references/modeling-and-handoff.md`](references/modeling-and-handoff.md#importing-from-a-repository-diagram)).
3. State omissions, explicit bounds, and any waived rules. Define the five-field proof contract before committing a chart or model; scratch charts require only a rerunnable command.

## Model

Work in a scratch folder outside the repository (`SPEC.tla`, `SPEC.cfg`, `view.mjs`). Encode each reader rule as an `INVARIANT` without weakening it, map `state(vars)` and `step(action, from, to)` to reader-visible wording, and follow TLA+/view conventions in [`references/modeling-and-handoff.md`](references/modeling-and-handoff.md#tla-and-view-authoring-rules). Read [`references/chart-view.md`](references/chart-view.md) for parent states, parallel regions, bracketed conditions, phase colors, and keeping charts to ~20 arrows.

## Run

```sh
<skill dir>/scripts/statechart SPEC.tla [--config FILE] [--view FILE] [--out DIR]
```

- `--out` must be a new or empty folder (use a new folder on reruns).
- Exit codes: `0` all rules hold; `1` rule broken; `2` TLC/command error; `130`/`143` interrupted (only `0` and `1` emit output).
- See [`references/modeling-and-handoff.md`](references/modeling-and-handoff.md#runtime-and-platform-setup) for Node/Bun/Deno/Windows setup, `TLA2TOOLS` (v1.7.4), and `JAVA` (11+).

## Verify

Read `report.md` before the chart and confirm: every reader rule appears under "Rules that hold", broken, or "Rules not checked"; every unchecked rule is surfaced in hand-off; every broken rule has a readable numbered path. Consult [`references/reading-results.md`](references/reading-results.md) for `breaks`/`mayBreak`, rerun bounds, `VIEW`/`SYMMETRY` merging, and the 500-state budget.

Replay every code-flow bug path against real code (one step per action); if it does not reproduce, treat the model as wrong until proven otherwise. Label each path `replayed`, `model-only` (including non-code flows), or `replay-inconclusive`.

## Hand off

Show `chart.mmd` as a `mermaid` code block (render images or oversized charts with Pele per [`references/render.md`](references/render.md); use another renderer only on request). Report:

- Per broken rule: rule name from `report.md`, reader sentence, marked chart state, numbered path, and replay label.
- Rules that hold, rules not checked, and rules waived.
- Omissions, added bounds, and hidden chart steps.
- For diagram-derived flows: each bug path as ordered diagram state/transition IDs plus model states absent from the diagram.
- Exact rebuild command with a new `--out` folder.

For historical bug maps against a project bug ledger (see [`patpat-formal-verify`](../patpat-formal-verify/SKILL.md#maintain-the-check)), follow [`references/modeling-and-handoff.md`](references/modeling-and-handoff.md#historical-bug-map).

Origin, Patpat changes, and license notices: [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
