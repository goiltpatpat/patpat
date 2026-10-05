# Gameplay Contract

Turn each material design promise into an observable player condition and a rule that can be checked. Use this chain:

**Design promise → acceptance condition → gameplay invariant → player feedback → verification oracle**

- State action semantics precisely when they affect the rule: press, release, hold, repeat, timing window, focus, and cooldown.
- Model only states and transitions needed by the requested slice. Name valid start, active, paused, terminal, and reset states when they exist.
- Give repeatable opportunities an explicit lifecycle. A hit, pickup, pulse, score event, or reward must not apply twice unless the design allows a new opportunity.
- Bound resources, timers, score, and entity lifetimes where an invalid value or unbounded event could break play. Validate relevant boundaries, not arbitrary edge cases.
- If a rule changes the player's next decision, make its state or consequence observable in time to act. Correct but hidden rules are not usable feedback.
- Keep random scenarios reproducible for rule checks when randomness affects the outcome. Use a test seed or replay input; do not add test-only exceptions to production rules.
- Treat rule correctness, balance, and fun as different claims. Assertions can prove a rule. Balance needs a declared comparison. Fun or feel needs play from the intended player and cannot be inferred from code or the author's confidence.

Do not encode design prose as an untestable comment. Do not solve a rule defect by tuning a nearby number unless evidence shows the number is the cause.
