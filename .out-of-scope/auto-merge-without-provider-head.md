# Auto-Merge Without Provider Head Verification

## Rejected idea

Allowing Patpat to arm GitHub auto-merge, merge from local test greenness alone, or treat an empty required-check list as a passing provider gate.

## Why it is out of scope

Delivery readiness inferred from a local proxy or stale snapshot causes silent bad merges when a branch is behind base, CI registers late, or a merge queue / retargeted stack changes the effective tree. Patpat Correction Ledger **C1** (`1828c7d`, `8000b6b`, `916f25d`, `406dc9e`) documents four separate incidents of proxy-inferred readiness.

## What we do instead

- Readiness comes exclusively from the provider's observed merge state (`mergeStateStatus`, `mergeable`, required checks, review state) bound to the exact committed head SHA via `skills/patpat-ship/scripts/github_observe.py::observation_document` and `pr_watch.py`.
- Merge requires explicit, un-retracted `land` or `merge` language from the user; overnight/continuation requests stop at merge-ready.
- An empty required-check set blocks `pr_watch.py` and the durable merge gate by design; never forge receipts or arm auto-merge.
