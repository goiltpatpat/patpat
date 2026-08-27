# Smallest Safe Change

Stop at the first approach that fully satisfies the proof contract.

1. Delete obsolete code when deletion solves the problem.
2. Reuse an existing repository pattern.
3. Use a language, platform, browser, or framework primitive.
4. Use an existing dependency.
5. Add one local patch.
6. Add a dependency or abstraction only when the earlier options cannot meet the requirement.

Preserve stable interfaces and avoid unrelated cleanup. Minimal means the smallest change that remains correct, safe, readable, and verifiable.

Keep a comment only when it encodes a constraint the code cannot show. If the comment claims a rule, encode that rule as a type, test, lint, or runtime check and delete the comment.
