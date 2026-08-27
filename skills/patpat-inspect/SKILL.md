---
name: patpat-inspect
description: Investigate a repository and explain how behavior works, including placement, ownership, layering, and critique after an explanation, without making changes. Use for how-does-X-work, where-should-this-live, who-owns-this, and are-we-sure questions. Do not use for historical why-was-it-shaped questions or for fix, ship, or merge work.
---

# Patpat Inspect

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md) and apply the [investigation playbook](../patpat-loop/playbooks/investigation.md). Report with the [how-report contract](references/how-report.md).

This skill owns the how-equivalent: how it works, where it lives, who owns it, which layer it occupies, and critique after that explanation. There is no `/how` slash skill. Do not rewrite [rationale-forensics](../patpat-loop/playbooks/rationale-forensics.md); why-shaped questions still go there.

For a live resource symptom, apply [runtime forensics](../patpat-loop/playbooks/runtime-forensics.md) and capture passively. For a supplied trace, profile, spindump, or heap snapshot, apply [trace forensics](../patpat-loop/playbooks/trace-forensics.md). Do not hot-patch, inject, or alter a live process inside this read-only workflow.

When the question asks why code or a contract reached its current shape, apply [rationale forensics](../patpat-loop/playbooks/rationale-forensics.md) and calibrate historical claims by direct evidence.

Keep the task read-only. Inspect version-control state first when available. Load only the repository instructions, continuity files, code paths, tests, configuration, logs, and runtime state needed to answer the question.

Default to one read-only pass. Use 2-4 parallel read-only explorers only when independent evidence sources are required, then one explainer. Fall back to serial work when isolation is missing.

Verify claims against primary artifacts. State whether each material conclusion is confirmed, inferred, or unknown. Cite files and functions. If a change appears necessary, recommend the smallest safe patch and stop unless the user also requested implementation. Critique uses `Act on` / `Consider` / `Noted` / `Dismissed` only after Explain. Do not open a pull request from inspect.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
