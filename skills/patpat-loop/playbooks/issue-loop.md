# Issue Loop Playbook

This is the Benny job under Patpat's protocol: triage incoming reports, then reproduce confirmed defects with real evidence. It is not a Slack-specific pack and it does not enable itself.

Read [automation design](automation-design.md), [defect](defect.md), [preserve safety](../principles/preserve-safety.md), [idempotent effects](../principles/idempotent-effects.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the provider, channel, trigger identity, allowed reads, allowed writes, secret source, sandbox, verifier, and kill switch. Fail closed with a checklist if any write-critical field is missing. Do not copy a dormant pack into `.cursor/automations` or enable a host scheduler.
2. Keep the loop `PAUSED` until the user names enable after a dry-run canary. Polling is not event delivery; bound the interval and overlap window.
3. **Triage** is read-only. Classify each report: bug, question, duplicate, insufficient evidence, or out of scope. Post or file only through one coordinator, with an idempotency key, and only to destinations the user named.
4. **Reproduce** only confirmed bugs. Require a failing observation on the real surface. Workers get no credentials and no external write tools. They return a typed proposal: repro evidence, suspected cause, and an optional draft diff.
5. The coordinator applies a draft only after [`patpat-verify`](../../patpat-verify/SKILL.md) and [`patpat-review`](../../patpat-review/SKILL.md). External comments stay in the source thread. Do not broadcast.
6. Land a fix only when the current request named commit, PR, or merge. Overnight triage does not imply ship.
7. Stop on ambiguous writes, secret leakage, missing sandbox proof, or a failed canary. Leave the loop paused.
