---
name: patpat-inspect
description: Investigate a repository and explain how behavior works or why it reached its current shape, including placement, ownership, layering, and critique after an explanation, without making changes. Use for how-does-X-work, where-should-this-live, who-owns-this, are-we-sure, and why-was-this-shaped questions. Do not use for fix, ship, or merge work.
---

# Patpat Inspect

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [repository truth](../patpat-loop/principles/repository-truth.md) and apply the [investigation playbook](../patpat-loop/playbooks/investigation.md). Report with the [how-report contract](references/how-report.md).

This skill explains how repository behavior works, where it lives, who owns it, which layer it occupies, and any critique that follows that explanation. Questions about why the code reached its current shape go to [rationale forensics](../patpat-loop/playbooks/rationale-forensics.md).

For a live resource symptom, apply [runtime forensics](../patpat-loop/playbooks/runtime-forensics.md) and capture passively. For a supplied trace, profile, spindump, or heap snapshot, apply [trace forensics](../patpat-loop/playbooks/trace-forensics.md). Do not hot-patch, inject, or alter a live process inside this read-only workflow.

When the question asks why code or a contract reached its current shape, apply [rationale forensics](../patpat-loop/playbooks/rationale-forensics.md) and report with the [why-report contract](references/why-report.md): code anchors first, evidence before narrative, competing hypotheses, and an honest account of material sources used or unavailable. Keep rationale questions in this skill; do not create a separate `/why` skill. Do not call unrelated external connectors to fill the report.

Keep the task read-only. Inspect version-control state first when available. Load only the repository instructions, continuity files, code paths, tests, configuration, logs, and runtime state needed to answer the question.

Default to one read-only pass. Use 2-4 parallel read-only explorers only when independent evidence sources are required, then one explainer whose synthesis is the product. Fall back to serial work when isolation is missing. For teach-me questions, the user-facing reply is the layered explanation, not a report about the work.

Verify claims against primary artifacts. State whether each material conclusion is confirmed, inferred, or unknown. Cite files and functions. If a change appears necessary, recommend the smallest safe patch and stop unless the user also requested implementation. Critique uses `Act on` / `Consider` / `Noted` / `Dismissed` only after Explain. Do not open a pull request from inspect.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
