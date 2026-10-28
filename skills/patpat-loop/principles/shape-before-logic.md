# Shape Before Logic

Name the authoritative data shape, legal states, transitions, ownership, and invalid combinations before adding control flow.

When designing or changing a system with concurrent writers, identify the shared targets and consistency invariants. Prefer separate ownership when it preserves those invariants; if sharing is necessary, choose and verify a mechanism that enforces the required coordination across all writers, including failure and retry paths. If writers or the mechanism cannot be controlled or verified, report the limitation instead of claiming a guarantee; do not claim completion when a required invariant remains unproven. Instructions or a re-read alone do not enforce concurrency control.

Use an explicit table, state machine, tagged model, or type boundary only when it removes invalid states, duplicated branches, or ambiguous ownership now. Reuse the repository's existing representation when it already expresses the contract. Do not introduce a domain abstraction for speculative flexibility.

Where the language can enforce the contract, make illegal combinations unrepresentable. Parse untrusted data at the trust boundary. Do not bypass the checker, exhaust variants, brand distinct primitives that must not mix, and derive types from the authoritative schema when one exists.
