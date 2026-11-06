---
name: patpat-learn
description: Convert a recurring failure, correction, or verification gap from the active task into the smallest durable constraint. Use when the same engineering mistake could recur and should be prevented structurally.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"AgentSkill","requires_state":["delivery-review-cleared"],"produces_state":["durable-constraint-recorded"],"verification_cmd":"python3 <loaded-skill-directory>/scripts/verify_corrections.py --root <workspace-root>"}'
---

# Patpat Learn

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [encode lessons](../patpat-loop/principles/encode-lessons.md), [repository truth](../patpat-loop/principles/repository-truth.md), and apply the [learning playbook](../patpat-loop/playbooks/learning.md).

Use evidence from the active task: user corrections, failed verification, repeated retries, review findings, or verifier defects. Separate one-off facts from recurring failure modes. Encode only the latter.

Choose the strongest narrow mechanism that prevents recurrence: type or contract, focused test, lint or validator rule, deterministic script, workflow instruction, then documentation. Prefer enforcement over reminders and update an existing authoritative location before creating a new file. Mine this conversation for recurring working-style or failure rules. Propose edits to existing files only. Present the proposal and wait for approval. Do not auto-apply. There is no new SKILL.md and no *-mode mint on this path. Never create a new SKILL.md. Never mint a personal `*-mode` skill.

Record the encoded constraint as a row in the repository's correction ledger and close with its ledger check, both as the [learning playbook](../patpat-loop/playbooks/learning.md#correction-ledger) defines them. Run proofs only for rows written in this task; other rows' proofs are repository commands that need the user's approval. When the check exits 3, the repository has no ledger: report the constraint as enforced but not recorded, and do not create an instruction file unasked.

Do not mine unrelated conversations or store sensitive task data. Do not modify shared or user-global rules without explicit authority. Verify that the chosen mechanism detects or prevents the original failure, then report what remains unprotected.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
