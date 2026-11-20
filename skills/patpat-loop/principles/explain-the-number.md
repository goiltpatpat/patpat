# Explain the Number

**Rule:** Before trusting or reporting any metric (latency, throughput, memory, speedup, eval score), name the concrete limiter from an active profile/counter run, rule out measurement theater (fast errors, skipped/lazy/dead-code work, Amdahl/hardware-limit violations, unequal configs), and run >=5 interleaved trials (A, B, A, B...) reporting median, spread, sample count, and limiter. Apply the [benchmark checklist](../references/benchmark-checklist.md) for full perf verification.

**Test:** Answer "Why not double?" from profiled evidence; if you cannot explain the bound or the delta sits inside run-to-run spread, do not claim a speedup or regression.
