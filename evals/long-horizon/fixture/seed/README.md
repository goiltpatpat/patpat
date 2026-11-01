# tally

A small expense ledger for the command line. Python standard library only.

```
python -m tally --file my.json add --date 2026-01-05 --amount 12.50 --category food --note lunch
python -m tally --file my.json list
python -m tally --file my.json total
```

`python -m tally` runs from the repository root. Run the tests with:

```
python -m unittest discover -s tests -t .
```
