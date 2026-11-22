# Route Catalog

Read this catalog only when the common routes in `patpat-loop` do not settle the workflow.

**Two-Load & Composable Primitives:** User-invoked workflows set `disable-model-invocation: true` (zero ambient load) and are called explicitly or read by orchestrators. Composable primitives chain along declared `metadata.patpat.ontology` state-graph edges in `patpat-loop` or `patpat-run`.

When one request needs outputs from multiple rows, keep `patpat-loop` as orchestrator and run each relevant workflow rather than dropping an explicit deliverable. Use `patpat-plan` when dependent phases need a separate execution plan.

| Intent | Workflow | Playbook |
| --- | --- | --- |
| Read-only question, audit, or diagnosis-only defect | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Investigation](../playbooks/investigation.md) |
| Defective behavior with fix requested | [`patpat-debug`](../../patpat-debug/SKILL.md) | [Defect](../playbooks/defect.md); [Regression first](../playbooks/regression-first.md) for cheap deterministic reproducers |
| Bounded feature or localized edit | [`patpat-change`](../../patpat-change/SKILL.md) | [Bounded change](../playbooks/bounded-change.md) |
| Map an unfamiliar workspace into a context graph | [`00-workspace-mapper`](../../00-workspace-mapper/SKILL.md) | Explicit request only; optional |
| Design architecture changes or run an opportunity scan | [`patpat-architect`](../../patpat-architect/SKILL.md) | [Architecture change](../playbooks/architecture-change.md) |
| Explain why code reached its current shape | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Rationale forensics](../playbooks/rationale-forensics.md) |
| Build or extend a playable game | [`patpat-game-builder`](../../patpat-game-builder/SKILL.md) | [Build slice](../../patpat-game-builder/playbooks/build-playable-slice.md); [diagnose](../../patpat-game-builder/playbooks/diagnose-gameplay.md), [verify playthrough](../../patpat-game-builder/playbooks/verify-playthrough.md), [visual iteration](../../patpat-game-builder/playbooks/visual-iteration.md) |
| Draw an interactive architecture or workflow visual | [`patpat-repository-diagram`](../../patpat-repository-diagram/SKILL.md) | Explicit request only; brief-only or repo-backed |
| Analyze blast radius or downstream regressions | [`patpat-impact`](../../patpat-impact/SKILL.md) | [Blast radius](../playbooks/blast-radius.md) |
| Fix a one-off latency, CPU, memory, or throughput regression | [`patpat-perf`](../../patpat-perf/SKILL.md) | [Performance](../playbooks/performance.md) |
| Drive sustained improvement on one numeric metric | [`patpat-perf`](../../patpat-perf/SKILL.md) | [Metric hillclimb](../playbooks/metric-hillclimb.md) |
| Diagnose a live leak, idle spin, or runtime glitch | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Runtime forensics](../playbooks/runtime-forensics.md) |
| Analyze a captured profile, trace, or heap snapshot | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Trace forensics](../playbooks/trace-forensics.md) |
| Execute one delegated implementation slice | [`patpat-engineer`](../../patpat-engineer/SKILL.md) | Direct |
| Refactor without changing external behavior | [`patpat-change`](../../patpat-change/SKILL.md) | [Behavior-preserving refactor](../playbooks/behavior-preserving-refactor.md) |
| Build a throwaway prototype to settle a design fork | [`patpat-change`](../../patpat-change/SKILL.md) | [Prototype](../playbooks/prototype.md) |
| Verify pixel-level UI parity | [`patpat-verify`](../../patpat-verify/SKILL.md) | [Visual equivalence](../playbooks/visual-equivalence.md) |
| Compete isolated attempts at the same brief | [`patpat-arena`](../../patpat-arena/SKILL.md) | [Arena](../playbooks/arena.md) |
| Fan out parallel slices, races, or coverage | [`patpat-swarm`](../../patpat-swarm/SKILL.md) | [Swarm](../playbooks/swarm.md) |
| Inspect PR or stack status/topology (read-only) | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [PR Drive](../playbooks/pr-drive.md); stack discovery in [PR Handoff](../playbooks/pr-handoff.md) |
| Durable multi-phase execution, PR stack, or overnight run | [`patpat-run`](../../patpat-run/SKILL.md) | [Multi-phase run](../playbooks/multi-phase-run.md); [Autopilot](../playbooks/autopilot.md) for PR queues |
| Run a named issue-source triage and repro loop | [`patpat-automation`](../../patpat-automation/SKILL.md) | [Issue loop](../playbooks/issue-loop.md) |
| Pause in-flight work or go offline | [`patpat-run`](../../patpat-run/SKILL.md) | [Pause safely](../playbooks/pause-safely.md) |
| Resume in-flight work without a valid run store | [`patpat-run`](../../patpat-run/SKILL.md) | [Session takeover](../playbooks/session-takeover.md) |
| Summarize recent changes and pending decisions (read-only) | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Catch-up](../playbooks/catch-up.md) |
| Pick up a session with an active run store or clean tree | [`patpat-run`](../../patpat-run/SKILL.md) | [Session pickup](../playbooks/session-pickup.md) |
| Drive a PR to merge-ready status or resolve review threads | [`patpat-change`](../../patpat-change/SKILL.md) | [PR Readiness Handoff](../playbooks/pr-handoff.md) |
| Prune merged or abandoned Git worktrees | Direct | [Worktree cleanup](../playbooks/worktree-cleanup.md) |
| Design, harden, or audit CI/CD and release pipelines | [`patpat-ship`](../../patpat-ship/SKILL.md) | [CI/CD Pipeline Design](../../patpat-ship/references/cicd-design.md); explicit request or accepted gap suggestion only |
| Commit, PR update, merge, publish, or deploy | [`patpat-ship`](../../patpat-ship/SKILL.md) | [Default delivery](../playbooks/default-delivery.md); [Authorized delivery](../playbooks/authorized-delivery.md) for merge/publish/deploy |
| Create or revise a reusable agent skill | [`patpat-skill`](../../patpat-skill/SKILL.md) | [Skill change](../playbooks/skill-change.md) |
| Evaluate skill triggering and behavior | [`patpat-eval`](../../patpat-eval/SKILL.md) | [Behavioral evaluation](../playbooks/behavioral-eval.md) |
| Create or maintain a project-local real-surface verifier | [`patpat-verifier`](../../patpat-verifier/SKILL.md) | [Project verifier](../playbooks/project-verifier.md) |
| Model a state flow, check invariants, or render a model-check receipt | [`patpat-statechart`](../../patpat-statechart/SKILL.md) | Broken model rules require runtime replay before claiming a code bug |
| Create or maintain a TLA+/TLC formal verification suite | [`patpat-formal-verify`](../../patpat-formal-verify/SKILL.md) | Hand charts to `patpat-statechart`; keep bounds, mutants, mapping, and replay separate |
| Encode a recurring mistake into a durable constraint | [`patpat-learn`](../../patpat-learn/SKILL.md) | [Learning](../playbooks/learning.md) |
| Audit recurring mistakes or unenforced repo rules (read-only) | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Learning](../playbooks/learning.md) history pass; approved rows land via `patpat-change` |
| Design or scaffold an external automation | [`patpat-automation`](../../patpat-automation/SKILL.md) | [Automation design](../playbooks/automation-design.md) |
| Sequence multi-phase work or multiple contracts | [`patpat-plan`](../../patpat-plan/SKILL.md) | [Bespoke workflow](../playbooks/bespoke-workflow.md) |
| Install, update, remove, or validate Patpat on a host | [`patpat-setup`](../../patpat-setup/SKILL.md) | Direct |
| Cut AI tropes and filler from docs, PRs, or diffs | [`patpat-unslop`](../../patpat-unslop/SKILL.md) | Direct |
| Independent diff and evidence review (mandatory delivery gate) | [`patpat-review`](../../patpat-review/SKILL.md) | [Independent review](../playbooks/independent-review.md) |
| Adversarial skeptical probe of logic, edge cases, and assumptions | [`patpat-interrogate`](../../patpat-interrogate/SKILL.md) | Direct (distinct from `patpat-review`) |

Resolve overlaps by the earliest unsettled decision: architect settles the contract, plan sequences phases, impact assesses downstream risk without redesigning, and prototype settles an empirical fork.
