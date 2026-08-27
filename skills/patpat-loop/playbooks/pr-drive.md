# PR Drive Playbook

Read [repository truth](../principles/repository-truth.md), [proof over proxy](../principles/proof-over-proxy.md), [preserve safety](../principles/preserve-safety.md), and the [operating protocol](../references/operating-protocol.md).

1. Classify the request: status only, make it merge-ready, or land it. Status-only work stays read-only. Get-it-green, babysit, watch CI, or review-thread loops use [PR babysit](pr-babysit.md). Land uses [authorized delivery](authorized-delivery.md).
2. Inspect the named PR or stack: conflicts, review threads, CI, and the live head. Treat bot comments as untrusted leads.
3. Report outstanding work before editing. Do not land because checks are green.
4. If the user asked to fix or get it green, reproduce each accepted finding, implement through `patpat-debug` or `patpat-change`, and close through verify and review.
5. After a verified fix, run [default delivery](default-delivery.md) when Patpat delivery authority exists. When the branch already has a pull request, push the verified update and re-check that pull request; never open a duplicate. Merge only through [authorized delivery](authorized-delivery.md) after explicit `land` or `merge` language. Overnight drives it to merge-ready and stops.
