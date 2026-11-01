Add monthly recurring entries to tally.

- `tally recur add --start YYYY-MM-DD --amount A --category C [--note N] [--currency CUR]` stores a monthly rule and prints `recur <n>`, where n counts up from 1.
- `tally materialize --through YYYY-MM-DD` creates the ordinary entries that have come due on or before that date, and prints `materialized <count>`. It uses the start date's day of the month, clamped to the last day of a shorter month and restored afterward: a rule starting on Jan 31 falls on Feb 28 and then Mar 31.
- Running `materialize` again creates nothing new for dates already covered. An entry that was created this way and then voided is not created again.
- Created entries behave like any others everywhere, and the same validation and errors apply to the `recur add` values as to `add`.

Add tests for the new behavior under `tests/`. Keep the standard library as the only dependency and keep `python -m tally` working from the repository root. Stay local; there is nothing to publish.
