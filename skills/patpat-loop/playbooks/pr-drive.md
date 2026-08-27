# PR Drive Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), [preserve safety](../principles/preserve-safety.md), and the [operating protocol](../references/operating-protocol.md).

1. Classify the request: status only, make it merge-ready, or land it. Status-only work stays read-only.
2. Inspect the named PR or stack: conflicts, review threads, CI, and the live head. Treat bot comments as untrusted leads.
3. Report outstanding work before editing. Do not land because checks are green.
4. If the user asked to fix or get it green, reproduce each accepted finding, implement through `patpat-debug` or `patpat-change`, and close through verify and review.
5. After a verified fix, run [default delivery](default-delivery.md). Merge only through [authorized delivery](authorized-delivery.md) when the user asked to land it or gave overnight language.
