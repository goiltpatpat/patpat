# Subtract Before You Add

Before introducing new files, flags, configuration options, or abstraction layers, examine what can be deleted or simplified.

1. Delete dead code, unused helpers, and obsolete branches before implementing new behavior.
2. Every new line of code is a maintenance liability, a reader burden, and a potential fault surface.
3. If an existing module can be refactored or consolidated to accommodate the requirement cleanly, do not create a parallel mechanism.
4. Prefer shrinking the conceptual surface of the repository over expanding it.
