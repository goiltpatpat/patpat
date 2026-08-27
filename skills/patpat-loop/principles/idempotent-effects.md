# Idempotent Effects

Design retries and partial runs to converge on the same intended state.

Give every external effect an immutable identity, dedupe check, immediate preflight, bounded retry policy, and compensation path. Keep one coordinator responsible for writes and fail closed when ownership or prior state is uncertain.
