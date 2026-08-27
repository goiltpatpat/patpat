# Shape Before Logic

Name the authoritative data shape, legal states, transitions, ownership, and invalid combinations before adding control flow.

Use an explicit table, state machine, tagged model, or type boundary only when it removes invalid states, duplicated branches, or ambiguous ownership now. Reuse the repository's existing representation when it already expresses the contract. Do not introduce a domain abstraction for speculative flexibility.

Where the language can enforce the contract, make illegal combinations unrepresentable. Parse untrusted data at the trust boundary. Do not bypass the checker, exhaust variants, brand distinct primitives that must not mix, and derive types from the authoritative schema when one exists.
