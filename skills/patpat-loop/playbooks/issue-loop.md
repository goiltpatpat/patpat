# Issue Loop Playbook

Triage incoming reports, then reproduce confirmed defects with real evidence. This playbook does not enable itself.

Read [automation design](automation-design.md), [defect](defect.md), [preserve safety](../principles/preserve-safety.md), [idempotent effects](../principles/idempotent-effects.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the provider, channel, trigger identity, allowed reads, allowed writes, secret source, sandbox, verifier, and kill switch. Fail closed with a checklist if any write-critical field is missing. Do not copy a dormant pack into `.cursor/automations` or enable a host scheduler.
2. Keep the loop `PAUSED` until the user names enable after a dry-run canary. Polling is not event delivery; bound the interval and overlap window.
3. **Triage** is strictly read-only. Classify each report: bug, question, duplicate, insufficient evidence, or out of scope. Do not post, file, react, label, assign, or update external state during triage.
4. Before competing for a confirmed bug, inspect provider and repository evidence for an owner, in-progress thread, open pull request, or commit that plausibly addresses the symptom. When one exists, stop new implementation and verify that candidate on the reported surface. Resume reproduction only when the candidate fails or is abandoned by authoritative evidence.
5. **Reproduce** only confirmed, unowned bugs. Require a failing observation on the real surface. Workers get no credentials and no external write tools. They return a typed proposal: repro evidence, suspected cause, and an optional draft diff.
6. A separate coordinator write may post or file only when the provider configuration names that exact action and destination in `allowed writes`, the user supplied fresh authority for it, and an idempotency preflight passes. External comments stay in the source thread. Do not broadcast. The coordinator applies a draft only after [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md).
7. A provider-triggered run may commit, non-force push, and create or update a draft pull request only when those exact actions are allowed and fresh automation authority exists. Event delivery, scheduler enablement, and provider configuration never authorize a ready pull request. Only a fresh interactive Patpat activation or direct ready-PR request may hand the verified diff to [default delivery](default-delivery.md). Overnight triage may drive an existing pull request to merge-ready but does not merge. Land only with explicit `land` or `merge` language.
8. Stop on ambiguous writes, secret leakage, missing sandbox proof, or a failed canary. Leave the loop paused.
