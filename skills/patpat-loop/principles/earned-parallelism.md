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

Before admitted fan-out, bind a schema-v2 coordinator attestation to the active program, validated plan, integration owner, and one unique isolation identity per unit. Attach bounded `{path, sha256, size}` file bindings for every gate check; `team_shape.py --bind-evidence /absolute/path/to/safe-artifact` creates one. The validator rechecks those files at dispatch open and before assignments, worker mutations, and delivery readiness. Their hashes make the coordinator's basis inspectable, but do not prove the claims, authorship, or host-enforced isolation. Substantiate gates from the actual worktree, verifier, and resource boundaries. If evidence is unavailable or stale, use serial work. Schema-v1 receipts cannot admit writable fan-out; read-only selection remains eligible under its own checks. Recompute and rebind when the plan, integration owner, evidence, or isolation identity changes; the dependency frontier may advance without changing run-wide gate evidence. Pass the `worker_limit` returned by `team_shape.py` when opening dispatch. `program_state.py` enforces it over recorded assignments in `pending` or `running` state, but does not count host processes. An optional deadline with an integration reserve blocks new assignments and reactivations after its dispatch cutoff while existing assignments can finish and record proof. The execution workflow owns receipt mechanics and team-shape selection; neither grants execution or delivery authority.
