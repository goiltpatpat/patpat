Add monthly reporting to tally.

- `tally report --month YYYY-MM` prints one line per category that has entries in that month, sorted by category name, then a final TOTAL line. Each line is the name left-justified to 12 characters followed by the amount right-justified to 10 characters. A month with no entries prints only the TOTAL line, with amount 0.00.
- `list` and `total` accept an optional `--month YYYY-MM` that restricts them to that month. It combines with `--category`.
- A malformed month exits with status 2 and prints `error: invalid month` to stderr.

Add tests for the new behavior under `tests/`. Keep the standard library as the only dependency and keep `python -m tally` working from the repository root. Stay local; there is nothing to publish.
