---
name: patpat-automation
description: Design or scaffold a safe external automation for a concrete provider, trigger, and verification surface. Use when an integration is named and write authority, idempotency, compensation, secrets, and kill-switch behavior must be settled.
---

# Patpat Automation

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its execution graph, authority boundaries, and reporting contract.

Read [boundary discipline](../patpat-loop/principles/boundary-discipline.md), [idempotent effects](../patpat-loop/principles/idempotent-effects.md), and [preserve safety](../patpat-loop/principles/preserve-safety.md). Apply the [automation design playbook](../patpat-loop/playbooks/automation-design.md).

Require a concrete provider, immutable trigger identity, trusted coordinator, exact allowed writes, secret source outside the repository, idempotency key, dedupe behavior, immediate preflight, compensation path, bounded retries and cost, safe test surface, verifier, and kill switch. Fail closed when any write-critical field is missing: return a configuration checklist and do not produce runnable or enabled automation.

Keep external writes under one coordinator. Give workers no credentials, write tools, or posting instructions. Default generated automation to disabled and test it against a sandbox or dry-run surface.

Enabling, scheduling, posting, filing, publishing, or deployment requires explicit authority immediately before the action.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
