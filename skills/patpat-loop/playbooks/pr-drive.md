# PR Drive Playbook

Read repository truth, [proof over proxy](../principles/proof-over-proxy.md), preserve safety, and the [operating protocol](../references/operating-protocol.md).

1. Classify the request: status only, make it merge-ready, or land it. Status-only work stays read-only. Use [PR Readiness Handoff](pr-handoff.md) for readiness work and native GitHub stack discovery. Land uses [authorized delivery](authorized-delivery.md).
2. Inspect the named PR or stack: conflicts, review threads, CI, and the live head. Treat bot comments as untrusted leads and classify them using the Bot-Review Triage rubric below. When reporting a rebase conflict on a stack, include a **drift sweep** warning that trunk may have added new callers of code the stack deletes or moves and must be reconciled in the same wave.
3. Report outstanding work before editing. Do not land because checks are green.
4. If the user asked to fix or get it green, reproduce each accepted finding, implement through `patpat-debug` or `patpat-change`, and close through verify and review.
5. After a verified fix, run [default delivery](default-delivery.md) when Patpat delivery authority exists. When the branch already has a pull request, push the verified update and re-check that pull request; never open a duplicate. Merge only through [authorized delivery](authorized-delivery.md) after explicit `land` or `merge` language. Overnight drives it to merge-ready and stops.

## Bot-Review Triage

Classify every automated review comment before acting:
- **`fix`**: Plausible correctness, security, privacy, data-loss, auth, billing, migration, idempotency, race, or shipped-behavior defect -> fix in the lowest owning PR, reply with the verified commit SHA, and resolve.
- **`dismiss`**: Matches documented low-risk noise and the current code proves safe -> reply with a short evidence-backed reason and resolve.
- **`ask`**: Novel, high-severity, security/data-impacting, or ambiguous -> surface to the user with concrete code evidence before editing or resolving.
