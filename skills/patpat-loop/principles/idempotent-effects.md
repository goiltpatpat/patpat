# Idempotent Effects

Design retries and partial runs to converge on the same intended state.

Give every external effect an immutable identity, dedupe check, immediate preflight, and bounded retry policy. Define compensation when reversal is possible. For an irreversible effect, fail before the effect when state or authority is uncertain and state the irreversibility explicitly. Keep one coordinator responsible for writes.
