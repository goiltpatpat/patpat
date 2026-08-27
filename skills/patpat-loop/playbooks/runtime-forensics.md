# Runtime Forensics Playbook

Read [repository truth](../principles/repository-truth.md), [boundary discipline](../principles/boundary-discipline.md), and [proof over proxy](../principles/proof-over-proxy.md).

1. Define the live symptom, time window, workload, and expected idle or steady state.
2. Capture passive runtime evidence with bounded overhead and preserve raw artifacts.
3. Correlate observations across process, thread, task, allocation, I/O, and lifecycle boundaries as relevant.
4. Identify the earliest abnormal state and distinguish cause from correlated activity.
5. Map the mechanism to source and state the evidence that would falsify it.
6. Remain read-only. Do not hot-patch, inject, or change a live process without separate authority and a mutating workflow.
