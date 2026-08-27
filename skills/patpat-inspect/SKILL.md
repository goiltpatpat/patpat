---
name: patpat-inspect
description: Investigate a repository, explain behavior, or audit a code path without making changes. Use for evidence-backed questions, status checks, risk reviews, and requests to diagnose without fixing.
---

# Patpat Inspect

When invoked directly, read [`patpat-loop`](../patpat-loop/SKILL.md) and follow its authority boundaries and reporting contract.

Read [repository truth](../patpat-loop/principles/repository-truth.md) and apply the [investigation playbook](../patpat-loop/playbooks/investigation.md).

For a live resource symptom, apply [runtime forensics](../patpat-loop/playbooks/runtime-forensics.md) and capture passively. For a supplied trace, profile, spindump, or heap snapshot, apply [trace forensics](../patpat-loop/playbooks/trace-forensics.md). Do not hot-patch, inject, or alter a live process inside this read-only workflow.

When the question asks why code or a contract reached its current shape, apply [rationale forensics](../patpat-loop/playbooks/rationale-forensics.md) and calibrate historical claims by direct evidence.

Keep the task read-only. Inspect version-control state first when available. Load only the repository instructions, continuity files, code paths, tests, configuration, logs, and runtime state needed to answer the question.

Verify claims against primary artifacts. State whether each material conclusion is confirmed, inferred, or unknown. If a change appears necessary, recommend the smallest safe patch and stop unless the user also requested implementation.

## Mutation boundary

Remain read-only with respect to repository implementation and external delivery. Limit incidental verifier artifacts to the declared proof contract, clean them up, and hand any authorized mutation back to `patpat-loop`.
