# Project Verifier Playbook

Read [proof over proxy](../principles/proof-over-proxy.md), [preserve safety](../principles/preserve-safety.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Identify the product claim, authoritative surface, launch path, readiness signal, and cleanup boundary.
2. Inspect existing tests, scripts, logs, browser or API tools, and project-local skills before adding anything.
3. When maintaining an existing verifier, enumerate every mapped feature and reconcile each entry to a concrete source entry point. Identify missing, dead, duplicate, and unmapped surfaces. Before editing, drive every mapped feature live or mark it `unreachable` with its prerequisite and attempted route so verifier drift is observed rather than guessed.
4. Reuse the narrowest harness that can drive and observe the real system.
5. If a reusable verifier is required, create `.agents/skills/verify-<app>/SKILL.md` with exact `Launch`, `Doctor`, `Exercise`, `Evidence`, and `Cleanup` sections.
6. Use scoped process ownership, deterministic readiness checks, redacted output, and bounded timeouts.
7. Run one complete workflow and preserve inspectable evidence of the observed result.
8. Run cleanup and prove that verifier-owned resources stopped without affecting unrelated processes.
9. Report product defects, verifier defects, environment blockers, and unmapped feature drift separately.
