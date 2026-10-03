# Explain the Number

A measured number is a claim about a system. Before trusting, reporting, or acting on a measured metric—such as latency, throughput, CPU reduction, memory allocation, speedup, regression, or eval score—name the limiter that bounds it and rule out that it measured proxy artifacts, errors, or untuned noise.

A run that went wrong still produces plausible numbers. Fast errors masquerading as high throughput, caches skipping computation, dead code eliminated by an optimizing compiler or JIT, un-iterated lazy generators, un-awaited promises, and run-to-run noise all produce flattering numbers for work that never ran. If you cannot explain why the number is not twice as good, you do not know what you measured.

## The four requirements

1. **Ask "Why not double?"** Name the concrete resource or code path that bounds the result: a CPU core, memory bandwidth, disk I/O, lock contention, network round-trip time, or load generator saturation. Derive it from an active profile or system counters (`top`, `pidstat`, `perf`, `strace -c`, runtime profilers) taken during a non-reported run, then map the bottleneck to source code. A guess from reading source code is not a limiter. If the load generator saturates first, you measured the benchmark runner, not the subject.
2. **Rule out measurement theater.**
   - *Did it error?* Fast failures and unhandled exceptions are often orders of magnitude faster than successful work. Always count errors and assert that the outputs are correct, not merely present.
   - *Did it even happen?* Confirm that the work actually executed inside the timed block. Lazy sequences nobody consumes, promises nobody awaits, and results discarded by dead-code elimination produce zero-cost measurements for work that was skipped.
   - *Did it break physical limits?* Apply Amdahl's Law and hardware bounds. Removing a subsystem that consumes 10% of total runtime can make the system at most ~11% faster. Results exceeding theoretical limits indicate caching, no-ops, or measurement defects.
   - *Was it tuned equally?* Run candidates under identical production-grade configurations: release builds, optimization flags, warm or cold caches matching production, and realistic data scales. Comparing default settings against tuned settings compares configurations, not code.
3. **Reproduce with interleaved trials.** Run each side at least 5 times and alternate the executions (A, B, A, B...) so that warmup, JIT compilation, background noise, and thermal throttling do not favor one candidate. Report the median and range. Treat differences smaller than the run-to-run variation as no measurable difference.
4. **Keep the evidence with the number.** Record the sample count, spread, and identified limiter alongside any performance claim.

For full performance measurement verification, apply the [benchmark checklist](../references/benchmark-checklist.md).
