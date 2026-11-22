# Human decision trail

Append-only human decisions sit beside the graph store, not inside it. JSON events in `state.json` are not the human trail.

Path: `<git patpat/runs>/<run-id>/decisions.tsv` next to `state.json`. Same privacy as run state: do not commit unless the user asks.

Columns, tab-separated, one header row then append-only data rows:

ts, phase, decision, why, evidence, result

- `evidence` is a pointer: commit, PR, `file:line`, or artifact path. Never a paragraph.
- A wrong call gets a new row. Do not edit prior rows.
- One row per decision or unit checkpoint, not every action.
- **Mechanical cell sanitization**: write rows through `run_state.py decision-trail` (`sanitize_tsv_cell` / `format_tsv_row`), which strips tabs, CR, and LF from every cell and prefixes cells starting with `=`, `+`, `-`, or `@` with `'` to block spreadsheet formula injection.
- **Cross-run `start` provenance boundary**: when a pickup or replacement agent appends to an existing `decisions.tsv`, emit a `start` boundary row first (`run_state.py decision-trail --root <repo> --run-id <run-id> --start --actor <agent-id>`) recording its run/actor identity and the prior `ts` range it did not author.

Each unit: hypothesis, then smallest change, then measure on the real artifact, then keep or revert. Inspect the artifact, not a self-report.

Verdicts: `VERIFIED`, `NOT VERIFIED`, or `INCONCLUSIVE`. INCONCLUSIVE is not a pass. Do not map it to keep.

Reuse existing receipts. Do not treat this file as a `run_state.py` schema bump.
