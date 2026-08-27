---
name: patpat-arena
description: Run isolated competing attempts at the same brief, pick a base, graft the strongest parts, and verify the synthesis. Use for /patpat-arena, competing designs, or when one attempt would lock the wrong shape.
---

# Patpat Arena

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [earned parallelism](../patpat-loop/principles/earned-parallelism.md) and apply the [arena playbook](../patpat-loop/playbooks/arena.md).

Fan out only after exclusive output paths exist. If isolation is unavailable, run one serial attempt and say so. Inherit the parent model unless the user named models. The parent owns pick, graft, verification, and any named delivery. Worker output is a candidate, not a completed change.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
