# Automation Design Playbook

Read [boundary discipline](../principles/boundary-discipline.md), [idempotent effects](../principles/idempotent-effects.md), and [preserve safety](../principles/preserve-safety.md).

1. Name the provider, immutable trigger identity, trusted coordinator, and exact allowed writes.
2. Define external secret sources and keep credentials out of workers, prompts, logs, and repository files.
3. Define idempotency keys, dedupe, trusted handoff markers, and preflight immediately before every write.
4. Define compensation for partial success and prove retries converge safely.
5. Bound time, retries, cost, scope, and follow-up windows.
6. Define a sandbox or dry-run surface, real verifier, observability, and kill switch.
7. Fail closed with a configuration checklist if any write-critical field is missing.
8. Scaffold disabled by default, verify, independently review, and require explicit authority before enabling.
