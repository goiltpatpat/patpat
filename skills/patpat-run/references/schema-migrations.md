# Program Store Schema Migrations (v1 / v2 / v3)

Load this reference only when `program_state.py` reports a legacy schema version (`v1`, `v2`, or `v3`) on an existing store. Current code deliberately refuses older program-state schemas rather than silently upgrading them.

## Migration commands

- **Schema v1** (created before assignment fencing): Do not trust or silently upgrade actor labels or evidence. Run `migrate-v1 --invalidate-legacy-evidence` explicitly; migration preserves the plan and heads, clears legacy evidence and inbox, closes gates, and requires fresh dispatch plus assignments.
- **Schema v2**: Run `migrate-v2 --invalidate-legacy-evidence`.
- **Schema v3**: Run `migrate-v3 --invalidate-legacy-evidence` (also creates the execution-policy record with no configured budget).

Each migration preserves the plan and heads, clears verification and review evidence, removes the old dispatch binding and inbox, resets units to pending, revokes assignments, and closes both gates. Assignment generations advance when a prior assignment snapshot exists. Require fresh schema-v2 parallel-gate receipt evidence and rerun unit proof before delivery.

## Safety and rollback

1. Stop all writers before migrating a real store.
2. Create and verify a protected copy of the exact `state.json` outside the live store.
3. Obtain explicit user authorization for that exact store and migration.
4. If post-migration status is wrong, stop writers and restore the verified copy with the pre-migration Patpat version that reads that schema before resuming.
