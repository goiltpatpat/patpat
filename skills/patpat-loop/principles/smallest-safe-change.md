# Smallest Safe Change

Stop at the first approach that fully satisfies the proof contract.

1. Delete obsolete code when deletion solves the problem.
2. Reuse an existing repository pattern.
3. Use a language, platform, browser, or framework primitive.
4. Use an existing dependency.
5. Add one local patch.
6. Add a dependency or abstraction only when the earlier options cannot meet the requirement.

Preserve stable interfaces and avoid unrelated cleanup. Choose for the consumer outcome and the next maintainer, not implementation convenience. Collapse pass-through layers and shrink hidden mutable state when doing so lowers reader load without widening the diff. Minimal means the smallest change that remains correct, safe, readable, and verifiable.

Keep a comment only when it encodes a constraint the code cannot show. Strip narrative commentary, paraphrased code steps, workaround sermons, and commented-out dead code. Comments are never a substitute for descriptive symbol names, domain types, or cleanly decomposed functions. Only three categories survive: legal notices, platform or third-party immutable quirks citing an upstream issue or RFC, and public API docstrings. Encode a claimed rule as a type, test, lint, or runtime check when practical; otherwise keep one concise comment that names the source of the constraint or the condition for removing it.
