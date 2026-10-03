# Benchmark Checklist

Use this checklist whenever producing or reporting a performance number: before-and-after PR comparisons, regression diagnoses, metric hillclimbs, or dependency choices. Read [explain the number](../principles/explain-the-number.md) for the foundational principle. Answer each question below with empirical evidence from a run, not from code inspection alone.

## Before running

- State the concrete claim in falsifiable terms ("export throughput increases by >= 25% at p50 on 50k rows").
- Inspect the harness: confirm what it times, what it counts, and what it excludes.
- Check baseline system load (`uptime`, `nproc`). Interleave executions if system noise cannot be eliminated.

## The seven vetting questions

1. **Why not double?** Name the limiter. Profile in a separate run so profiler overhead does not contaminate measurements. Use CPU metrics (`top`, `pidstat`), runtime profilers (`py-spy`, `perf`, `node --cpu-prof`), I/O wait, and syscall counts (`strace -c`). Map the hot spot to code symbols. If the load generator maxes out first, you measured the generator.
2. **Was it tuned?** Run all candidates under production conditions: release builds, production flags, connection pools, and identical cache states. A candidate running on default settings while another is tuned compares configurations, not implementations.
3. **Did it break limits?** Check arithmetic against hardware bandwidth and Amdahl's Law. Compare time saved against total execution time of the modified path. If the math violates hardware throughput or core capacity, the benchmark measured a bug, cache hit, or no-op.
4. **Did it error?** Track failure counts and non-success statuses. Errors often return early, creating artificial speedups. Confirm outputs are semantically valid and non-empty.
5. **Does it reproduce?** Run at least 5 interleaved iterations per candidate (A, B, A, B...). Report the median and full range. If the difference is within noise margins, record it as no measurable difference.
6. **Does it matter?** Measure the end-to-end user-visible latency or throughput path with realistic data volumes, not just an isolated micro-loop.
7. **Did it even happen?** Verify that computation was not discarded by JIT dead-code elimination, un-iterated lazy generators, or un-awaited async tasks. Assert consumption of the computed output.

## Reporting contract

- Lead with the verdict: `faster`, `slower`, `no measurable difference`, or `inconclusive`.
- Report metric, unit, sample count, median, range, and identified limiter (e.g. `p50: 42ms -> 31ms, median of 7 runs, range 30-33ms, CPU-bound on single core`).
- Mark as `inconclusive` if the limiter cannot be identified, settings were untuned, or error checks were skipped.
