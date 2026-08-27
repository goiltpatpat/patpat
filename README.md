# Patpat

Engineering skills for work that must be proven.

Agents can generate code faster than teams can review it. Throughput without evidence is not a goal. If you want to go fast, make a smaller change and prove it.

Patpat turns an agent host into a disciplined engineering loop: inspect the real system, name the proof before editing, change the smallest safe surface, and verify the result where the user would see it.

The core is Patpat's operating protocol: judgment, safety, git, and honest evidence. The workflow machinery is informed by [pstack](https://github.com/cursor/plugins/tree/main/pstack). When those conflict, the protocol wins.

Use [`/patpat`](skills/patpat/SKILL.md) for non-trivial work. It is the same entry as [`/patpat-loop`](skills/patpat-loop/SKILL.md). Call a focused skill directly when the task is already narrow.

## Install

Codex, from this repository:

```bash
codex plugin marketplace add goiltpatpat/patpat
codex plugin add patpat@patpat
```

Start a new task, then invoke `$patpat`. Package installation and prompt-time discovery are separate checks.

Antigravity, from a clone that does not contain local development state:

```bash
git clone https://github.com/goiltpatpat/patpat.git
agy plugin validate /absolute/path/to/patpat
agy plugin install /absolute/path/to/patpat
```

Cursor native loading is experimental. Until a live project load is proven, install into a proven project skill directory and reload:

```bash
python3 scripts/install_skills.py \
  --target /absolute/path/to/project/.agents/skills \
  --dry-run
```

A working tree that still contains Memory Bank or other ignored files must be staged first. Agents should follow [`AGENTS.md`](AGENTS.md). Host commands, updates, and removal live in the [installation guide](docs/guide/installing.md).

## Get started

Two steps:

1. Install Patpat on the active host.
2. Invoke `/patpat` (Cursor), `$patpat` (Codex), or `Use patpat to ...` on other hosts.

```text
/patpat reproduce this timeout, fix the root cause, and land the PR
```

That is enough. The router stays on across later turns, selects a playbook, and loads the other skills as the steps need them. Say `disable /patpat` to opt out.

## Usage

[`/patpat`](skills/patpat/SKILL.md) is the default entry point. It reads the request, copies a playbook, and routes through inspection, proof, implementation, verification, and review. Trusted host hooks persist the mode across resume. Without a hook receipt the mode still applies for the rest of the current session.

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY -> REVIEW -> LEARN? -> REPORT
```

A proof contract names the claim, authoritative surface, action, expected observation, and cleanup. A build supports a claim. It does not prove user-visible behavior.

Cursor uses `/patpat` or `/patpat-loop`. Codex uses `$patpat` or `$patpat-loop`. Portable hosts use `Use patpat to ...`.

### Playbooks

| Playbook | For |
| --- | --- |
| [Investigation](skills/patpat-loop/playbooks/investigation.md) | A read-only question. How does this work, why was it built this way, are we sure. |
| [Defect](skills/patpat-loop/playbooks/defect.md) | Reproduce a failure, prove the root cause, and fix it with runtime evidence. |
| [Regression first](skills/patpat-loop/playbooks/regression-first.md) | A cheap deterministic test exists. Write the failing check, then the fix. |
| [Performance](skills/patpat-loop/playbooks/performance.md) | A measured slowness against a comparable baseline. |
| [Metric hillclimb](skills/patpat-loop/playbooks/metric-hillclimb.md) | Sustained improvement of one metric, one accepted win at a time. |
| [Runtime forensics](skills/patpat-loop/playbooks/runtime-forensics.md) | A live symptom: leak, idle spin, glitch. |
| [Trace forensics](skills/patpat-loop/playbooks/trace-forensics.md) | A captured profile, trace, or heap snapshot. |
| [Rationale forensics](skills/patpat-loop/playbooks/rationale-forensics.md) | Why the code reached this shape, from repository evidence. |
| [Blast radius](skills/patpat-loop/playbooks/blast-radius.md) | What else this change could break, proven rather than asserted. |
| [Architecture change](skills/patpat-loop/playbooks/architecture-change.md) | Contracts, migrations, or a redesign that must settle before code. |
| [Bounded change](skills/patpat-loop/playbooks/bounded-change.md) | New or changed behavior from a named data shape. |
| [Behavior-preserving refactor](skills/patpat-loop/playbooks/behavior-preserving-refactor.md) | Structure changes without behavior changes. |
| [Prototype](skills/patpat-loop/playbooks/prototype.md) | A throwaway sketch that makes a design decision cheap. |
| [Visual equivalence](skills/patpat-loop/playbooks/visual-equivalence.md) | Pixel-level UI parity between two implementations. |
| [Bespoke workflow](skills/patpat-loop/playbooks/bespoke-workflow.md) | No narrow playbook fits. Design a falsifiable sequence. |
| [Multi-phase run](skills/patpat-loop/playbooks/multi-phase-run.md) | Work that spans phases, checkpoints, or a durable graph. |
| [Session takeover](skills/patpat-loop/playbooks/session-takeover.md) | Resume or take over in-flight work from live repository state. |
| [Pause safely](skills/patpat-loop/playbooks/pause-safely.md) | Pause in-flight work without opening a PR or merging. |
| [PR drive](skills/patpat-loop/playbooks/pr-drive.md) | PR status only. Land only when named. |
| [PR babysit](skills/patpat-loop/playbooks/pr-babysit.md) | Get a PR green, watch CI, or address review threads. Stops merge-ready. |
| [Worktree cleanup](skills/patpat-loop/playbooks/worktree-cleanup.md) | Prune merged or abandoned git worktrees. Simulators stay outside the core. |
| [Arena](skills/patpat-loop/playbooks/arena.md) | Competing isolated attempts at one brief, then a verified synthesis. |
| [Swarm](skills/patpat-loop/playbooks/swarm.md) | Parallel slices or races, one aggregated report. |
| [Autopilot](skills/patpat-loop/playbooks/autopilot.md) | A verified queue or stack. Merge only when named. |
| [Issue loop](skills/patpat-loop/playbooks/issue-loop.md) | Named-provider triage and reproduce. Stays paused until enabled. |
| [Default delivery](skills/patpat-loop/playbooks/default-delivery.md) | After proof, commit and open a ready PR unless opted out. |
| [Authorized delivery](skills/patpat-loop/playbooks/authorized-delivery.md) | Merge a green verified PR only on explicit land or merge; pause for deploy. |
| [Independent review](skills/patpat-loop/playbooks/independent-review.md) | Challenge an implementation and its proof without editing. |
| [Skill change](skills/patpat-loop/playbooks/skill-change.md) | Write or revise a SKILL.md. |
| [Behavioral evaluation](skills/patpat-loop/playbooks/behavioral-eval.md) | Test whether a skill triggers and behaves correctly. |
| [Project verifier](skills/patpat-loop/playbooks/project-verifier.md) | Build or repair project-local proof against the real system. |
| [Learning](skills/patpat-loop/playbooks/learning.md) | Encode a recurring failure as the smallest durable constraint. |
| [Automation design](skills/patpat-loop/playbooks/automation-design.md) | Design fail-closed automation for a named integration. |

## Skills

`patpat-loop` runs most of these when a step needs them. Reach for one directly when the task is already that operation.

| Skill | Use it when |
| --- | --- |
| [`patpat`](skills/patpat/SKILL.md) | Slash alias for the loop. `/patpat` is the default entry. |
| [`patpat-loop`](skills/patpat-loop/SKILL.md) | The work is non-trivial and needs the full loop. |
| [`patpat-inspect`](skills/patpat-inspect/SKILL.md) | Explain, audit, or diagnose without editing. |
| [`patpat-plan`](skills/patpat-plan/SKILL.md) | Sequence verifiable phases without implementing them. |
| [`patpat-impact`](skills/patpat-impact/SKILL.md) | Prove blast radius and downstream invariants. |
| [`patpat-architect`](skills/patpat-architect/SKILL.md) | Settle contracts, migrations, and risk first. |
| [`patpat-change`](skills/patpat-change/SKILL.md) | Implement one bounded feature or refactor. |
| [`patpat-debug`](skills/patpat-debug/SKILL.md) | Reproduce, root-cause, and fix. |
| [`patpat-perf`](skills/patpat-perf/SKILL.md) | Improve a measured resource regression. |
| [`patpat-verify`](skills/patpat-verify/SKILL.md) | Test a claim on the real artifact or user surface. |
| [`patpat-review`](skills/patpat-review/SKILL.md) | Independently try to falsify the change and its evidence. |
| [`patpat-run`](skills/patpat-run/SKILL.md) | Drive or resume a durable multi-phase graph. |
| [`patpat-arena`](skills/patpat-arena/SKILL.md) | Compete isolated attempts and synthesize one verified result. |
| [`patpat-swarm`](skills/patpat-swarm/SKILL.md) | Cover slices or races and return one report. |
| [`patpat-setup`](skills/patpat-setup/SKILL.md) | Install, validate, or remove Patpat on a host. |
| [`patpat-ship`](skills/patpat-ship/SKILL.md) | Default commit-and-PR after proof; merge only when explicitly named. |
| [`patpat-skill`](skills/patpat-skill/SKILL.md) | Author a reusable skill. |
| [`patpat-eval`](skills/patpat-eval/SKILL.md) | Evaluate skill triggering with isolated prompts. |
| [`patpat-verifier`](skills/patpat-verifier/SKILL.md) | Create or maintain a project-specific verifier. |
| [`patpat-learn`](skills/patpat-learn/SKILL.md) | Encode a recurring failure. |
| [`patpat-automation`](skills/patpat-automation/SKILL.md) | Design fail-closed automation. Do not enable it yet. |
| [`patpat-engineer`](skills/patpat-engineer/SKILL.md) | Execute one isolated slice for a named owner. |

Principles live under [`skills/patpat-loop/principles/`](skills/patpat-loop/principles/). They are references, not discoverable skills. The [capability map](docs/guide/capability-map.md) records what is covered, gated, or left outside the core.

## Agent roles

Two roles, one contract each:

- `patpat-engineer` owns one bounded implementation slice and returns artifacts to the integration owner.
- `patpat-reviewer` is read-only and tries to break the implementation and its evidence.

Cursor and Antigravity ship a thin native adapter only for the reviewer. The engineer stays a portable skill until a host can enforce file ownership. Codex receives both roles as skills.

## Durable runs

[`patpat-run`](skills/patpat-run/SKILL.md) is a standard-library state machine, not a prose checklist. It refuses `ACT` without a proof contract, `REVIEW` without a current content-bound evidence file, and completion without independent review. The third identical blocker stops the run.

```bash
python3 skills/patpat-run/scripts/run_state.py --self-test
```

## Not shipped

These stay bounded by the operating protocol:

- Writable arena, swarm, and autopilot require isolation and fall back to serial work
- Issue-loop stays paused until a named provider, sandbox, canary, and enable request exist
- Merge of a red CI, package publish, and production deploy
- Model-selection presets and persona skills

After verify and review, `/patpat` commits and opens a ready PR. Overnight, going to bed, or don't stop stops merge-ready and flags the user. Merge only on explicit land or merge when checks are green. It still pauses for production deploy, force-push, secret rotation, and risky auth or billing changes.

## Validate

```bash
python3 scripts/validate.py --self-test
python3 scripts/dry_run_loop.py --self-test
python3 scripts/install_skills.py --self-test
python3 scripts/stage_plugin.py --self-test
python3 scripts/smoke_codex_plugin.py
python3 scripts/smoke_antigravity_plugin.py
```

## Design lineage

Patpat is an independent system. Its core is the [operating protocol](skills/patpat-loop/references/operating-protocol.md). Its router, playbooks, sticky `/patpat` mode, and named ship path are informed by [Lauren Tan's pstack](https://github.com/cursor/plugins/tree/main/pstack). It does not take pstack's voice, model-role presets, Graphite merge-when-ready, persona skills, or "never block on the human" for delivery.

## License

MIT
