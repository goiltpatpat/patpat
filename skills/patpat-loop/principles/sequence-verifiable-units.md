# Sequence Verifiable Units

**Rule:** Split multi-step work into the fewest atomic, reversible units that each return to a verified state—migrate all internal callers (using expand → batched green migrate → contract for wide mechanical refactors) and delete the old API in the same wave so zero throwaway compatibility shims remain. When a transform or check is non-trivial—not only when it repeats—build a small rerunnable script after the first proven manual unit and land that script in the diff (never a framework). A configured Git remote is not push authority: checkpoint locally unless delivery/continuation authority permits remote writes, bind verification to the exact pushed head, and require independent review before pushing to an existing PR or delivery surface.

**Test:** Each unit passes verification independently before the next begins, any non-trivial transform has its rerunnable script present in the diff, and zero dual-path shims remain.
