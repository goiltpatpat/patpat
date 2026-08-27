# Authorized Delivery Playbook

Use after [default delivery](default-delivery.md) when the work must land, publish, or deploy.

Read [preserve safety](../principles/preserve-safety.md), [proof over proxy](../principles/proof-over-proxy.md), and the [operating protocol](../references/operating-protocol.md).

1. Name the remaining action and target: merge, publish, or deploy. Resolve the existing pull request or artifact directly; do not assume this session created it.
2. Inspect the live head, CI, and the PR URL. Require current verify and review receipts for that head.
3. Require explicit `land` or `merge` language for the named pull request or stack. Overnight, going to bed, don't stop, or a generic ship request without a named merge action reaches merge-ready and stops. State-then-wait still applies when the user asked only for the plan.
4. If CI is green, merge. If CI failed, classify flake vs real fail. Retry a flake once. Do not land a real fail. Do not land because the playbook ended.
5. Pause for production deploy, package publish, force-push, secret rotation, and risky auth, billing, or permission changes. Explain blast radius, rollback, and verification, then wait.
6. Re-check the remote revision directly after the action.
