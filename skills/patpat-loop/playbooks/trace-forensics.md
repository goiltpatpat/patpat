# Trace Forensics Playbook

Read [repository truth](../principles/repository-truth.md), [boundary discipline](../principles/boundary-discipline.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Identify the artifact format, capture conditions, symbols, clock, and known limitations.
2. Preserve the original and analyze a copy or read-only view.
3. Reduce the trace to the hot path, wait chain, retained object, or state transition relevant to the claim.
4. Map evidence back to source and distinguish missing symbols from absent activity.
5. Compare with a paired artifact when one exists.
6. Report the bounded mechanism, alternative explanations, and the next discriminating capture; do not implement a fix.
