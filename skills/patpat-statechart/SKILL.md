---
name: patpat-statechart
description: Model how a product flow, protocol, service, or business process moves between states, check the rules the reader agrees to with TLA+/TLC, and show each broken rule as a path on a Mermaid statechart in the reader's words. Use to chart a flow, ask whether it can get stuck or break, show a bug as a path through states, or render a saved model-check receipt; use patpat-repository-diagram for structure-only diagrams and patpat-formal-verify for a durable project verification suite.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Artifact","requires_state":["workspace-root-open"],"produces_state":[],"verification_cmd":""}'
---

# Patpat Statechart

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

A statechart answers one question for one reader: can this flow reach a state that breaks a rule they care about? The reader may be an engineer, a product owner, or a shop owner describing a process with no code. The chart uses their words, and they decide whether the behavior is right.

## Choose the route

- Use this skill for behavior over time: a checkout, login, deploy, agent workflow, media player, or an order process, and whether it can get stuck, double-charge, or hand over something it should not.
- Use [`patpat-repository-diagram`](../patpat-repository-diagram/SKILL.md) for architecture, dataflow, and sequence views with no rules to check.
- Use [`patpat-formal-verify`](../patpat-formal-verify/SKILL.md) when later changes must rerun the check as a durable project suite. It hands its TLA+ results here.
- Use [`references/receipt-rendering.md`](references/receipt-rendering.md) to chart a saved `patpat-model-check-receipt` without running TLC.

## Frame

1. Name the reader and write each rule as one sentence they would agree to, such as "we never hand over a refunded drink". Ask only when a rule is a product choice the evidence cannot settle.
2. List the actors and events that move the flow. When the flow describes code, read the code that owns each event and note the file and function.
3. Say what the model leaves out, for example more than one instance, timing, or partial failures. Name every bound you add, such as a cap of two payment attempts, and every rule the reader waived.

If the chart or model will be committed, define the five-field proof contract first. A scratch chart needs only a rerunnable command.

## Model

Work in a scratch folder outside the repository. Write `SPEC.tla`, `SPEC.cfg`, and a view module.

- Write each reader rule as an INVARIANT. If the model has no variable for a rule, add one. Never weaken a rule to make it hold.
- Write `Next` as a disjunction of named actions, such as `YouPressPlay \/ YouPressStop`, or TLC names every step `Next`.
- A correct end state with no step out still breaks `NoDeadlock`. Add an action that is true only in end states and changes nothing, such as `Done == phase \in {"paid", "failed"} /\ UNCHANGED vars`, and label it in `step()`. When an INVARIANT or PROPERTY is already named `NoDeadlock`, the deadlock rule is `CHECK_DEADLOCK`.
- In the view, `state(vars)` returns what the reader sees, such as "Paying" or "Refunded, screen still says Ready", never a variable name. `step(action, from, to)` receives the TLC action name and the raw variable values before and after, and returns what the reader sees happen, such as "the customer asks for a refund", never the code or TLA+ action name.

Read [`references/chart-view.md`](references/chart-view.md) for parent states, parallel regions, conditions in brackets, phase colors, and cutting a chart to about 20 arrows.

## Run

```sh
<skill dir>/scripts/statechart SPEC.tla [--config FILE] [--view FILE] [--out DIR]
```

`scripts/statechart` needs Node 22.18 to 22.x, Node 23.6 or later, Bun 1.1.5 or later, or Deno 2.0 or later; Git Bash can run it. From Windows `cmd` or PowerShell, use `scripts/statechart.cmd`, which needs Node 22.18 or later on `PATH`.

- `--out` must name a new or empty folder. Rerun with a new folder.
- Exit 0: every rule holds. Exit 1: a rule breaks. Exit 2: TLC or the command failed. Exit 130 or 143: interrupted. Only 0 and 1 write output.
- The first run installs TLC and Java with mise and needs the network. Setting `TLA2TOOLS` to a `tla2tools.jar` (pinned release v1.7.4) skips mise; `JAVA` then defaults to `java` on `PATH` and must be Java 11 or later.
- On Windows, Java reads arguments in the system ANSI code page. Keep the spec in a folder whose name that code page can spell.

## Verify

Read `report.md` before reading the chart. Then check:

- every reader rule appears under "Rules that hold", as broken, or under "Rules not checked";
- no rule is listed as not checked without saying so in the hand-off;
- each broken rule has a numbered path whose steps make sense in the reader's words.

Read [`references/reading-results.md`](references/reading-results.md) for `breaks` and `mayBreak` marks, the rerun bound, state merging under VIEW or SYMMETRY, constraints, the 500-state chart budget, and each output file.

A broken rule is a model finding. When the flow describes code, replay each bug path against the real code, as a test or a live repro, one step per action. If the bug does not occur, treat the model as wrong until you show otherwise. Label each path `replayed`, `model-only`, or `replay-inconclusive`. A flow with no code, such as a written business process, is `model-only`.

## Hand off

Show `chart.mmd` as a `mermaid` code block. For an image, or a chart too large to read as text, render it with Pele as described in [`references/render.md`](references/render.md); use another renderer only when the user asks.

Then report:

- one line per broken rule: the rule name from `report.md`, the reader's sentence, the marked chart state where it breaks, the numbered path, and its replay label;
- the rules that hold, any rules not checked, and any rules the reader waived;
- what the model leaves out, the bounds you added, and which steps the chart hides;
- the command that rebuilds the files, with a new `--out` folder.

Origin and Patpat changes to the copied command are in [`UPSTREAM.md`](UPSTREAM.md); the license notice is in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
