# Sequence Verifiable Units

Split multi-step work into the fewest atomic, reversible units that each return the system to a verifiable state.

Verify each unit before starting the next. A unit is an engineering boundary, not permission to create a commit, branch, pull request, or external artifact.

A verifiable unit is not a throwaway compatibility layer. Do not add a dual path just to make an intermediate step look complete. If the same transform will run more than once, build a rerunnable tool after the first proven manual unit and use that tool for the rest of the wave.

A configured Git remote is a destination, not authority. Remote Git writes remain fail-closed: a remote existing grants no push authority by itself. In multi-phase, long-running, or autonomous execution, push a verified unit checkpoint only when existing delivery intent or continuation authority permits remote writes and repository or user policy does not prohibit them. Bind verification to the exact pushed head. If the push updates an existing pull request or otherwise exposes that candidate for delivery, require independent review of that exact head before pushing. A checkpoint push is not a ready-PR or merge decision; completion still follows default delivery with current verification and review. Without remote-write authority, checkpoint locally only.
