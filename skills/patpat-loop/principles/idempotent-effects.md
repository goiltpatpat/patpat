# Idempotent Effects

**Rule:** Design retries and partial runs to converge on the same state: give every external effect an immutable identity, dedupe check, preflight, bounded retry, and single write coordinator. Define compensation when reversible; fail closed before irreversible effects when state or authority is uncertain.

**Test:** Re-running the step after a partial failure must produce the same end state with no duplicate external effect.
