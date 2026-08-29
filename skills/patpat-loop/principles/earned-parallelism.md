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

Before admitted fan-out, write a bounded structured receipt that binds the program id, validated plan digest, integration owner, every earned-parallelism check, and one unique isolation identity per unit. Pass its absolute path to [`team_shape.py`](../../patpat-run/scripts/team_shape.py) with observed capacity and an explicit worker budget, then use the same receipt to open the program dispatch gate. A boolean claim or missing receipt forces `iterative`. Treat exact, ancestor, and conservatively intersecting glob ownership as shared mutable scope unless dependency order serializes the units. Use `distributed` for decomposable slices and `adversarial` only when an independent oracle can falsify high-uncertainty candidates. The output recommends a smallest team and never grants execution or delivery authority. Recompute and rebind when the plan, frontier, integration owner, or isolation identity changes.
