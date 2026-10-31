---
name: patpat-verifier
description: Create or maintain a project-specific verification skill that launches, exercises, observes, and cleans up the real system. Use when a repository lacks repeatable proof of its user-facing behavior.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"AgentSkill","requires_state":["workspace-root-open"],"produces_state":["project-verifier-configured"],"verification_cmd":"git status --short"}'
---

# Patpat Verifier

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [proof over proxy](../patpat-loop/principles/proof-over-proxy.md), [preserve safety](../patpat-loop/principles/preserve-safety.md), and apply the [project verifier playbook](../patpat-loop/playbooks/project-verifier.md).

Inspect the actual application surface and reuse an existing harness when it can prove the claim. Otherwise create the smallest project-local verifier at `.agents/skills/verify-<app>/SKILL.md` with exact `Launch`, `Doctor`, `Exercise`, `Evidence`, and `Cleanup` procedures. Seed `features/README.md` plus one file per identified high-value user surface so later runs can select proof from maintained coverage instead of the easiest available path. Do not invent features to reach a quota.

Make every command executable as written. Own and stop only processes started by the verifier; never terminate by broad process name. Keep secrets out of prompts, logs, artifacts, and external calls. Preserve evidence long enough for independent inspection.

Isolate instances so two can run side by side (ports, data dirs, profiles), or refuse to double-drive a shared instance.

Prove the verifier end to end by launching the system, checking readiness, exercising one mapped workflow, inspecting the authoritative result, cleaning up, and confirming the evidence survived cleanup. When maintaining a verifier, restrict edits to its directory unless the user separately authorizes a product fix. Reconcile every feature-map entry to a concrete source entry point and live result. Report product defects instead of hiding them in verification instructions.

## Automated harness scaffolding (.patpat/verify.sh or scripts/verify.py)

When a project lacks an existing automated test suite or repeatable CLI verification command, scaffold a minimal, deterministic project-local verifier script (such as `.patpat/verify.sh` or `scripts/verify.py`):

1. **Auto-detect Runtime & Entrypoint**:
   - Python: detect `pytest`, `unittest`, or entrypoint script (`main.py`, `app.py`).
   - Node/TypeScript: detect `npm test`, `jest`, `vitest`, or direct node runner.
   - Go / Rust: detect `go test ./...` or `cargo test`.
   - Generic CLI: detect main binary or entrypoint script.
2. **Structure the 5-Phase Verifier**:
   - **Phase 1: Environment & Dependency Doctor**: Fast non-destructive check that required runtimes, tools, and ports are available.
   - **Phase 2: Static Sanity**: Fast syntax, type-check, or manifest parse.
   - **Phase 3: Targeted Behavioral Exercise**: Invoke the real binary or endpoint against representative concrete inputs (no mock theater).
   - **Phase 4: Invariant & Evidence Assertions**: Check exit codes, stdout patterns, and generated artifact hashes; return exit code 0 on strict pass.
   - **Phase 5: Deterministic Cleanup**: Clean temporary files, shut down spawned test processes by held PID.
3. **Execution Guardrails**:
   - Keep the harness strictly local, idempotent, and non-destructive.
   - Never mutate external databases or remote services without explicit authorization.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
