# Sequence Verifiable Units

Split multi-step work into the fewest atomic, reversible units that each return the system to a verifiable state.

Verify each unit before starting the next. A unit is an engineering boundary, not permission to create a commit, branch, pull request, or external artifact.

A verifiable unit is not a throwaway compatibility layer. Do not add a dual path just to make an intermediate step look complete. If the same transform will run more than once, build a rerunnable tool after the first proven manual unit and use that tool for the rest of the wave.

In multi-phase, long-running, or autonomous execution, where remote authority exists and push is not prohibited, push after each verified unit once its proof passes. Pushing the verified branch snapshot preserves progress on the remote repository and protects the run against process loss, rate limits, or context compaction.
