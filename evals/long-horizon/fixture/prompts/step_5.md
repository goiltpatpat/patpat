Move tally's storage to SQLite.

- The path given by `--file` is now an SQLite database, created when first written.
- A JSON ledger at that path, from any earlier version of tally, is migrated in place the first time it is opened. The original bytes are kept at `<file>.bak`, which later runs leave alone.
- A file at that path that is neither SQLite nor a JSON ledger is left untouched, and the command exits with status 2 and `error: unrecognized store`.
- Nothing else about the command line changes.

Add tests for the new behavior under `tests/`. Keep the standard library as the only dependency and keep `python -m tally` working from the repository root. Stay local; there is nothing to publish.
