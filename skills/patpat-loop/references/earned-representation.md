# Earned representation

When structure, flow, ownership, state, or a proposed change is hard in prose, choose the smallest representation that makes the engineering fact or decision obvious.

## Prefer (compact)

| Situation | Smallest useful form |
| --- | --- |
| logic / algorithm | compact pseudocode |
| runtime execution | call tree |
| file / module ownership | shallow tree |
| UI / component structure | component tree |
| interaction / data / control flow | sequence or flow diagram |
| before / after structural change | diff-shaped representation |
| dense UI / system concept | focused artifact only when simpler forms are insufficient |
| otherwise | concise prose |

## Rules

- Do not visualize by default.
- Do not overwhelm. One small representation usually beats several.
- Keep only files, calls, states, boundaries, and deltas relevant to the current decision.
- Do not reproduce whole architectures when one edge is the point.
- Representation supports reasoning, not decoration.

## Scope

Applies primarily to inspect, architect, and review explanation surfaces. Must not require diagrams in `patpat-change` or `patpat-debug`. Must not add planning or reporting ceremony for trivial mutation.

## Forbidden

No `/show-me`, no visual mode, no presentation subsystem, and no new top-level route.
