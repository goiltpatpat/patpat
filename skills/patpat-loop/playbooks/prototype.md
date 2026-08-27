# Prototype Playbook

Read [repository truth](../principles/repository-truth.md), [smallest safe change](../principles/smallest-safe-change.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. State the empirical design question and the observation that will decide it.
2. Create the smallest alternatives in an isolated scratch area outside production paths.
3. Keep inputs and comparison conditions equivalent.
4. Exercise each alternative through the relevant surface and capture observable differences.
5. Choose, reject, or leave the decision open from evidence.
6. Clean up scratch artifacts unless the user requests retention.
7. Do not copy prototype code into production by implication; hand the selected design to `patpat-change`.
