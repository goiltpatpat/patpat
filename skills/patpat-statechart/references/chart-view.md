# Shape the chart

Read this when the view needs regions, conditions, phase colors, or fewer arrows. A small flat chart needs only `state()` and `step()` from the skill.

## The view module

The view is an ES module, such as `view.mjs`, passed with `--view`. The command calls `state()` and `group()` at most once for each model state, and `step()` at most once for each step. The chart and the report both use those answers, so make each function depend only on its arguments.

`state(vars)` returns the reader's label. Its type picks the chart form:

- A string gives a flat chart: `export const state = (v) => (v.paid ? "Paid" : "Paying");`
- An array gives parent states: `export const state = (v) => v.main.split(".");`
- An object gives one parallel region for each key: `export const state = (v) => ({ Playback: v.playback, Volume: v.volume });`

In `vars`, a TLA+ sequence is an object with keys from 1, so `v.pc[1]` is `pc[1]`. A set is an array.

`step(action, from, to)` gets the TLC action name and the values before and after the step, and returns the arrow label. Two actions that end the same in the chart get the same label, so that they share one arrow. Return `null` to hide a step.

Optional exports:

- `group(vars)` returns a phase name. Each chart state gets the color of its group. When the model states behind one chart state are in different groups, that state gets no color.
- `colors` maps each group name to `blue`, `orange`, `purple`, `yellow`, `teal`, `tan`, or `pink`.
- `title` is a string shown at the top of the chart.

## Labels and conditions

When a step can occur only in some conditions, end its label with the condition in brackets, in the reader's words, such as `you press play [while the file loads]`. In a regions chart, the command writes the condition on the other regions on the arrow, in the words of their labels, such as `[when Offline]`. Your brackets replace it, and two arrows from one state can then look the same, so in a regions chart do not write brackets for a condition on another region.

When a value that no label shows decides where a step goes, name the result in the label, such as "the roster read fails".

The chart does not draw a step that stays in one label. Split a label when the reader must see such a step.

## Keep it readable

Aim for about 20 arrows or fewer.

1. Return coarser labels from `state()` first. Give one label to values that act the same, and leave out detail the reader does not need, such as a call in flight whose return changes nothing.
2. Keep each state of a bug path and each mark. A merge that turns a `breaks` state into `mayBreak` hides where a rule breaks. Never merge two states that break different rules.
3. If the chart is still too busy, return `null` from `step()` for steps the reader does not need, such as a reset every state has, or an arrow that repeats what other arrows show.

When you hide steps:

- Keep each chart state reachable by arrows from a start state.
- Keep at least one arrow out of each chart state that has a step out in the model.
- Hide all the steps of an arrow, or none of them. Hiding only some narrows its condition.
- Name the hidden steps in the hand-off.
