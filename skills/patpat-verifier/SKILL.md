---
name: patpat-verifier
description: Create or maintain a project-specific verification skill that launches, exercises, observes, and cleans up the real system. Use when a repository lacks repeatable proof of its user-facing behavior.
---

# Patpat Verifier

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [preserve safety](../patpat-loop/principles/preserve-safety.md), and apply the [project verifier playbook](../patpat-loop/playbooks/project-verifier.md).

Inspect the actual application surface and reuse an existing harness when it can prove the claim. Otherwise create the smallest project-local verifier at `.agents/skills/verify-<app>/SKILL.md` with exact `Launch`, `Doctor`, `Exercise`, `Evidence`, and `Cleanup` procedures.

Make every command executable as written. Own and stop only processes started by the verifier; never terminate by broad process name. Keep secrets out of prompts, logs, artifacts, and external calls. Preserve evidence long enough for independent inspection.

Prove the verifier end to end by launching the system, checking readiness, exercising one representative workflow, inspecting the authoritative result, and cleaning up. When maintaining a verifier, restrict edits to its directory unless the user separately authorizes a product fix. Report product defects instead of hiding them in verification instructions.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
