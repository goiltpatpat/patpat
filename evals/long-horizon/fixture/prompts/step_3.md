Let tally void entries instead of deleting them.

- Every entry has a stable integer id. New entries take the next id, and an id is never reused. Entries in files that predate ids are numbered from 1 in file order. The output of `add` does not change.
- `list --ids` prefixes each line with `#<id>  `.
- `tally void <id>` marks an entry void and prints `voided <id>`. An unknown id exits with status 2 and `error: no entry <id>`. Voiding twice exits with status 2 and `error: entry <id> already voided`.
- A void entry takes no part in `list`, `total`, or `report`, and it cannot cause a missing-rate error.
- `list --all` also shows void entries, with ` [void]` at the end of the line. It combines with `--ids`.

Add tests for the new behavior under `tests/`. Keep the standard library as the only dependency and keep `python -m tally` working from the repository root. Stay local; there is nothing to publish.
