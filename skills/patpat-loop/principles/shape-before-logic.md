# Shape Before Logic

**Rule:** Name the authoritative data shape, legal states, transitions, ownership, and invalid combinations before writing control flow. Reuse existing representations; make illegal states unrepresentable with types/exhaustive variants/branded primitives, and parse untrusted data at the trust boundary. For concurrent writers, prefer separate ownership or verify an explicit coordination mechanism across failure/retry paths (prose never enforces concurrency).

**Test:** Can an invalid state or mixed primitive be constructed inside the boundary, or is a concurrency invariant unproven? If so, tighten the shape or report the limitation.
