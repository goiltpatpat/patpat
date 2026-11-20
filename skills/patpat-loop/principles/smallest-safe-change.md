# Smallest Safe Change

**Rule:** Stop at the first option that satisfies the proof contract: (1) delete obsolete code, (2) reuse a repo pattern, (3) use a language/platform primitive, (4) use an existing dependency, (5) add one local patch, (6) add a new dependency/abstraction only if 1-5 cannot meet the requirement. Preserve implicit invariants—no drive-by refactors or vanity modernization outside blast radius. Keep comments only for legal notices, upstream quirk/RFC citations, public API docstrings, or non-obvious constraints code cannot express.

**Test:** Every changed line in the diff must directly substantiate the requested requirement or defect fix; strip any line or comment that does not.
