# Sequence Verifiable Units

**Rule:** Split multi-step work into the fewest atomic, reversible units that each return to a verified state—no throwaway compatibility shims (migrate all internal callers and delete the old API in the same wave). Build a rerunnable tool after the first proven manual unit when a transform repeats. A configured Git remote is not push authority: checkpoint locally unless delivery/continuation authority permits remote writes, bind verification to the exact pushed head, and require independent review before pushing to an existing PR or delivery surface.

**Test:** Each unit passes verification independently before the next begins, and leaves zero dual-path shims behind.
