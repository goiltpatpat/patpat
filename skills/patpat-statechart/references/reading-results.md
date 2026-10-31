# Read the results

Read this before claiming a rule holds, when the report lists "Rules not checked", or when the model uses a CONSTRAINT, ACTION_CONSTRAINT, VIEW, or SYMMETRY.

## Marks

- A chart state that breaks a rule has the class `breaks`. When only some model states behind it break the rule, it has `mayBreak`. The Legend names the rules of each mark; when two rules break, it names both on one mark, so say in the hand-off which state breaks which rule.
- In a regions chart, a state gets a mark when each combination of region states that includes it can break a rule. When a combination can break a rule and none of its states has a mark, each state in that combination gets a mark.
- TLC goes past a state that breaks a rule, so the chart shows the states after a bug.

## How the command checks rules

- It runs TLC on the config as written, with one worker. When a rule breaks, it removes that rule and runs TLC again, until no rule breaks.
- After the first break, each run stops at 100,000 distinct states. When a run reaches that bound or stops on an error, the report lists the rules it did not check under "Rules not checked", and the chart does not mark them. An unchecked rule can hold or break. To check it, remove the broken rules from the config or make the model smaller.
- The bound adds a module that changes TLC's variable order, so for a property TLC can find a different counterexample than a run without the bound.
- Because TLC goes past bugs, a model with no limit on its states can run without end. Keep constants small, or add a CONSTRAINT.

## Bounds and state merging

- With a VIEW or a SYMMETRY, TLC counts states it treats as the same as one state, and the chart draws that one state. An arrow can lead to it rather than to the state the step reaches, and the report says so.
- TLC checks the rules in each state past a CONSTRAINT or an ACTION_CONSTRAINT, but does not explore that state or check it for deadlock. When TLC's shortest path for a rule ends in such a state, the chart draws that state and the report gives the path; other states past the bound are not drawn, and a deadlock there does not show.
- TLC also checks the rules after each step an ACTION_CONSTRAINT excludes, even when it reaches the next state another way. When TLC's shortest path for a rule ends with such a step, the chart draws that step.

## Size budget

The chart has a budget of 500 states, counted by TLC on the config as written. Above that, it draws only the paths to rules that break, and when no rule breaks the command writes no `chart.mmd`. It still checks each rule, and the report gives the state count and each bug path. Make the model smaller to see the whole graph.

## Output files

- `report.md`: state and step counts, rules that hold, broken rules with numbered paths, and rules not checked.
- `chart.mmd`: the Mermaid statechart.
- `tlc.out`: what TLC printed on the config as written. TLC prints its first warning twice when Java runs with `-XX:+UseParallelGC`; `tlc.out` shows it once, because TLC leaves the second copy out of the output the command reads.
- `tlc-RULE.out`: what TLC printed for the run that found a broken rule whose path the chart does not show.
