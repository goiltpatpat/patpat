# Prose-Only Fixes for Recurring Agent Mistakes

## Rejected idea

Fixing recurring agent failure modes by appending more reminder sentences to `AGENTS.md`, `SKILL.md`, or playbooks without an enforceable mechanism or an expiring exception.

## Why it is out of scope

Unenforced prose rules bloat always-loaded context, drift across files, and silently regress as soon as context pressure rises. Future contributors and agents copy the nearest code path, not buried instructions.

## What we do instead

- Follow [encode lessons](../skills/patpat-loop/principles/encode-lessons.md): fix recurring mistakes (≥2 independent occurrences) at the earliest enforceable boundary — architecture removal > type check > CI / validator / script / pre-tool hook > behavioral test > prose.
- Record every encoded class and repository policy in the `AGENTS.md` Correction Ledger, mechanically verified by `skills/patpat-learn/scripts/verify_corrections.py`.
- Any `prose` ledger row requires an explicit reason, an approver, and a ≤180-day expiry date (`<reason>; expires YYYY-MM-DD; approved-by <name>`).
