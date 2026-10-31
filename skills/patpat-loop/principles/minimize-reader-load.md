# Minimize Reader Load

Code and documentation are read far more often than they are written. Optimize ruthlessly for the next human or agent reading the change.

1. Make control flow predictable, linear, and localized. Avoid hidden indirection, spooky action-at-a-distance, or dynamic dispatch when a direct call suffices.
2. Choose precise, domain-aligned names for symbols and files that describe their exact invariant.
3. Keep the diff minimal and focused; do not mix unrelated aesthetic restructuring with behavioral changes.
4. Do not force the reader to simulate complex state transitions in their head when an explicit data structure makes the legal states obvious.
