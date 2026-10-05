# Gameplay Validation Matrix

Use this matrix to turn the requested behavior into the smallest useful rule checks and player observations. Select applicable rows only. These are inspection prompts, not a mandate to implement every subsystem.

| Feature or promise | Invariant to consider | Focused check | Player-surface observation |
| --- | --- | --- | --- |
| Input | Press, release, hold, repeat, focus, and remapping have the intended semantics. | Input mapping or handler checks for accepted and rejected events. | The intended device triggers the correct action once, with understandable feedback. |
| State and replay | Actions are legal only in intended states; reset returns all required state. | Transition checks for start, play, pause, terminal, and reset states that exist. | Start, pause/resume, finish, and replay through the actual interface when in scope. |
| Hits, collisions, pickups, and scoring | One opportunity is consumed once, and its lifecycle or repeat rule is explicit. | Boundary and duplicate-event cases; use stable entity or opportunity identity when practical. | No duplicate hit, pickup, score, or missing response along the tested path. |
| Timers, cooldowns, and resources | Values stay in range; pause and terminal states affect time and regeneration as specified. | Boundary values, expiry, pause/resume, and terminal-state transitions. | The player can see relevant readiness, cost, or remaining resource before acting. |
| Random generation | Generated starts and sequences respect named solvability or minimum-response constraints. | Repeat a fixed validation seed and inspect the sequence that affects the claim. | Threats and rewards are perceptible before the player must respond. |
| Save, load, and progression | Persisted values and transitions preserve the stated contract. | Existing checks or an isolated save fixture that cannot overwrite user progress. | State survives the requested restart or session boundary; never delete user saves to test. |
| Multiplayer or online play | The authoritative side validates requests and owns contested state; client builds contain no server credentials or privileged keys. | Existing local or staged integration checks; inspect client artifacts for secrets and do not write to live services without authority. | Exercise only an authorized target and report untested latency, disconnect, or peer cases. |
| HUD, audio, and visual cues | Feedback corresponds to the actual rule state and is available when it changes a decision. | State-to-presentation checks where the project supports them. | Inspect current runtime captures and listen to changed audio through the real interface. |
| Resolution, device, and performance | Layout and input remain usable on the named target; performance has a defined workload. | Target-specific checks and a repeatable workload only when required. | Check requested viewport and actual input device; do not infer other platforms. |
