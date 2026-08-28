# Earned Parallelism

Use parallel work only when all gates pass:

- A recent representative single-owner run in this repository passed the same verifier and integration path.
- A stable verifier can judge each result.
- Work splits into independent, deterministic slices.
- Every writable worker has its own worktree or host-enforced sandbox, Git index, process space, and external-resource boundary.
- Workers do not share a mutable file, branch, key, environment, or external resource. Disjoint files in one worktree do not count as isolation.
- One integration owner is named.
- The integrated result receives whole-system verification.

Keep mutating work serial when any gate fails or that repository-specific trust evidence does not exist. Read-only investigation may parallelize across independent evidence sources.

Arena, swarm, and autopilot are admitted only through these gates. Missing isolation is a serial fallback, not invented coverage. The parent owns integration, verification, and any named delivery. Never enable auto-merge merely because independent checks are green.
