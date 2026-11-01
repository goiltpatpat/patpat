Add currencies to tally.

- `add` accepts `--currency`, three uppercase letters, defaulting to USD. Anything else exits with status 2 and `error: invalid currency` on stderr. An amount is stored in the currency it was entered in.
- A new top-level option, `tally --rates PATH ...`, names a JSON object mapping a currency code to its USD value per unit, as a string: `{"EUR": "1.10"}`.
- `total` and `report` print USD. Convert each entry on its own, rounding half up to cents, and then sum. When an entry they need has no rate, they exit with status 2 and `error: no rate for EUR` (with the code in question) on stderr. USD entries never need a rate.
- In `list`, an entry in another currency shows a space and its code straight after the amount column, for example `    10.00 EUR  lunch`. USD lines stay exactly as they are. `list` never needs rates.
- Ledger files written before this change have no currency on their entries. Those entries are USD.

Add tests for the new behavior under `tests/`. Keep the standard library as the only dependency and keep `python -m tally` working from the repository root. Stay local; there is nothing to publish.
