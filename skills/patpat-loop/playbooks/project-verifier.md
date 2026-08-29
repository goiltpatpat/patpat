# Project Verifier Playbook

Read [proof over proxy](../principles/proof-over-proxy.md), [preserve safety](../principles/preserve-safety.md), and [smallest safe change](../principles/smallest-safe-change.md).

1. Identify the product claim, authoritative surface, launch path, readiness signal, and cleanup boundary.
2. Inspect existing tests, scripts, logs, browser or API tools, and project-local skills before adding anything.
3. When maintaining an existing verifier, enumerate every mapped feature and reconcile each entry to a concrete source entry point. Identify missing, dead, duplicate, and unmapped surfaces. Before editing, drive every mapped feature live or mark it `unreachable` with its prerequisite and attempted route so verifier drift is observed rather than guessed.
4. Reuse the narrowest harness that can drive and observe the real system.
5. If a reusable verifier is required, create `.agents/skills/verify-<app>/SKILL.md` with exact `Launch`, `Doctor`, `Exercise`, `Evidence`, and `Cleanup` sections. Alongside it, create `features/README.md` as the coverage index and one file for each identified high-value user surface, aiming for three to five when the repository provides that many. Do not add placeholder features.
6. In the index, link every feature file and name its source entry point, authoritative proof surface, and current reachability. In each feature file, record the user claim, how to reach it, the exact exercise, the observable proof, prerequisites, and cleanup. Keep project commands and selectors in this project-local map, not in Patpat core.
7. Use scoped process ownership, deterministic readiness checks, redacted output, and bounded timeouts.
8. Run one mapped workflow end to end and preserve inspectable evidence of the observed result. A new verifier is a draft until this succeeds.
9. Run cleanup, prove that verifier-owned resources stopped without affecting unrelated processes, and confirm the evidence still exists.
10. Report product defects, verifier defects, environment blockers, and unmapped feature drift separately.
