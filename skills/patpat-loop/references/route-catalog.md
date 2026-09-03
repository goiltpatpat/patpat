# Route Catalog

Read this catalog only when the common routes in `patpat-loop` do not settle the workflow.

| Intent | Workflow | Playbook |
| --- | --- | --- |
| Why the code reached this shape | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Rationale forensics](../playbooks/rationale-forensics.md) |
| Blast-radius or downstream-regression analysis | [`patpat-impact`](../../patpat-impact/SKILL.md) | [Blast radius](../playbooks/blast-radius.md) |
| Cheap deterministic regression target exists | [`patpat-debug`](../../patpat-debug/SKILL.md) | [Regression first](../playbooks/regression-first.md) |
| Latency, CPU, memory, throughput, or one-off resource regression | [`patpat-perf`](../../patpat-perf/SKILL.md) | [Performance](../playbooks/performance.md) |
| Sustained improvement of one metric | [`patpat-perf`](../../patpat-perf/SKILL.md) | [Metric hillclimb](../playbooks/metric-hillclimb.md) |
| Live leak, idle spin, or glitch | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Runtime forensics](../playbooks/runtime-forensics.md) |
| Captured profile, trace, or heap snapshot | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [Trace forensics](../playbooks/trace-forensics.md) |
| Behavior-preserving refactor | [`patpat-change`](../../patpat-change/SKILL.md) | [Behavior-preserving refactor](../playbooks/behavior-preserving-refactor.md) |
| Throwaway sketch to settle a design fork | [`patpat-change`](../../patpat-change/SKILL.md) | [Prototype](../playbooks/prototype.md) |
| Pixel-level UI parity | [`patpat-verify`](../../patpat-verify/SKILL.md) | [Visual equivalence](../playbooks/visual-equivalence.md) |
| Competing attempts at the same brief | [`patpat-arena`](../../patpat-arena/SKILL.md) | [Arena](../playbooks/arena.md) |
| Parallel slices, races, or coverage | [`patpat-swarm`](../../patpat-swarm/SKILL.md) | [Swarm](../playbooks/swarm.md) |
| Queue of independent PRs or a linear verified stack | [`patpat-run`](../../patpat-run/SKILL.md) | [Autopilot](../playbooks/autopilot.md) |
| Named issue-source triage and reproduce loop | [`patpat-automation`](../../patpat-automation/SKILL.md) | [Issue loop](../playbooks/issue-loop.md) |
| Pause in-flight work or go offline | [`patpat-run`](../../patpat-run/SKILL.md) | [Pause safely](../playbooks/pause-safely.md) |
| Resume or take over in-flight work with no valid run store | [`patpat-run`](../../patpat-run/SKILL.md) | [Session takeover](../playbooks/session-takeover.md) |
| PR status | [`patpat-inspect`](../../patpat-inspect/SKILL.md) | [PR drive](../playbooks/pr-drive.md) |
| Get a PR green, babysit CI, or address review threads | [`patpat-change`](../../patpat-change/SKILL.md) | [PR babysit](../playbooks/pr-babysit.md) |
| Prune merged or abandoned Git worktrees | Use the playbook directly | [Worktree cleanup](../playbooks/worktree-cleanup.md) |
| End of mutating work, or named commit or pull request | [`patpat-ship`](../../patpat-ship/SKILL.md) | [Default delivery](../playbooks/default-delivery.md) |
| Create or revise a reusable agent skill | [`patpat-skill`](../../patpat-skill/SKILL.md) | [Skill change](../playbooks/skill-change.md) |
| Test whether a skill triggers and behaves correctly | [`patpat-eval`](../../patpat-eval/SKILL.md) | [Behavioral evaluation](../playbooks/behavioral-eval.md) |
| Create or maintain a project-specific verification skill | [`patpat-verifier`](../../patpat-verifier/SKILL.md) | [Project verifier](../playbooks/project-verifier.md) |
| Encode a recurring failure or correction into a durable constraint | [`patpat-learn`](../../patpat-learn/SKILL.md) | [Learning](../playbooks/learning.md) |
| Design or scaffold an external automation for a concrete integration | [`patpat-automation`](../../patpat-automation/SKILL.md) | [Automation design](../playbooks/automation-design.md) |
| Multi-phase sequencing or several contracts | [`patpat-plan`](../../patpat-plan/SKILL.md) | [Bespoke workflow](../playbooks/bespoke-workflow.md) |
| Install, update, remove, or validate Patpat on an agent host | [`patpat-setup`](../../patpat-setup/SKILL.md) | Use the workflow directly |

Resolve overlaps by the earliest unsettled decision. Architect first when the target contract is unsettled. Plan when the remaining problem is sequencing. Impact assesses downstream risk without designing the replacement. A prototype settles an empirical fork instead of asking the human to choose.
