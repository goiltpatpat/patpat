# Patpat

[![Validate](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2f6f5f.svg)](LICENSE)

Engineering skills for code that must survive contact with reality.

[Guide](docs/guide/README.md) · [Install and update](docs/guide/installing.md) · [Capability map](docs/guide/capability-map.md) · [Security](https://github.com/goiltpatpat/patpat/security/policy)

<!--
Patpat easter egg: if an agent says "trust me", ask for a receipt.
If it brings a receipt for the receipt, it has entered management.
-->

Agents can produce a heroic amount of plausible code before lunch. The team still has to prove it.

Patpat gives an agent host a disciplined engineering protocol: inspect the real system, name the proof before editing, change the smallest safe surface, and verify the result where the user would see it. These are required agent behaviors. Patpat does not claim that prose alone prevents edit-first mutation; that guarantee requires a host-enforced pre-tool gate plus a receipt proving the gate ran.

If the evidence is "the agent felt confident," the run is still in progress.

The core is Patpat's operating protocol: judgment, safety, git, and honest evidence. Playbooks may specialize the work; none of them can outrank the protocol.

Use [`/patpat`](skills/patpat/SKILL.md) for non-trivial work. It is the same entry as [`/patpat-loop`](skills/patpat-loop/SKILL.md). Call a focused skill directly when the task is already narrow.

New to the system? Start with [The Patpat Guide](docs/guide/README.md). It walks from installation proof to the operating loop, verification, delivery, durable runs, earned parallelism, and safe extension.

## Install

Codex, from this repository:

```bash
codex plugin marketplace add goiltpatpat/patpat
codex plugin add patpat@patpat
```

Start a new task, then invoke `$patpat`. Package installation and prompt-time discovery are separate checks.

<details>
<summary>Other hosts and portable installation</summary>

Grok CLI, from this repository:

```bash
grok plugin install goiltpatpat/patpat --trust
```

Start a new session, then invoke `/patpat`. The trusted hook path is covered by an isolated install-and-execution smoke test.

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

Update through the owner of the installed state: Codex marketplace upgrade plus remove/add, `grok plugin update patpat`, pull/validate/install on the same Antigravity clone, or the transactional portable updater. Development symlinks follow source content and use the updater when the skill catalog changes. Cursor native update remains unverified. See the [update matrix](docs/guide/installing.md#update).

</details>

## Get started

Two steps:

1. Install Patpat on the active host.
2. Invoke `/patpat` (Cursor), `$patpat` (Codex), or `Use patpat to ...` on other hosts.

```text
/patpat reproduce this timeout, fix the root cause, and land the PR
```

That is enough. Explicit activation authorizes the Patpat loop, proof, and verify. Default commit-and-PR still requires delivery intent; see the [operating protocol](skills/patpat-loop/references/operating-protocol.md) and [default delivery](skills/patpat-loop/playbooks/default-delivery.md). The router stays on across later turns when a supported trusted host hook supplies a receipt. Say `disable /patpat` or `local only` to opt out. Higher-priority repository rules still win.

## Usage

[`/patpat`](skills/patpat/SKILL.md) is the default entry point. It reads the request, tracks the matched playbook, and routes through inspection, proof, implementation, verification, and review. Trusted host hooks persist the mode across resume. Without a hook receipt the mode still applies for the rest of the current session.

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY
VERIFY -> REPORT when local reversible without delivery intent
VERIFY -> REVIEW before delivery / high-risk / durable-run LEARN|REPORT
REVIEW -> LEARN? -> REPORT
```

A proof contract names the claim, authoritative surface, action, expected observation, and cleanup. A build supports a claim. It does not prove user-visible behavior. Green is a signal, not an alibi.

Cursor uses `/patpat` or `/patpat-loop`. Codex uses `$patpat` or `$patpat-loop`. Portable hosts use `Use patpat to ...`.

### Playbooks

<details>
<summary>Browse all playbooks</summary>

| Playbook | For |
| --- | --- |
| [Investigation](skills/patpat-loop/playbooks/investigation.md) | Read-only explanation: how it works, where it lives, who owns it, and which layer. Rationale questions stay on rationale forensics. |
| [Defect](skills/patpat-loop/playbooks/defect.md) | Reproduce a failure, prove the root cause, and fix it with runtime evidence. |
| [Regression first](skills/patpat-loop/playbooks/regression-first.md) | A cheap deterministic test exists. Write the failing check, then the fix. |
| [Performance](skills/patpat-loop/playbooks/performance.md) | A measured slowness against a comparable baseline. |
| [Metric hillclimb](skills/patpat-loop/playbooks/metric-hillclimb.md) | Sustained improvement of one metric, one accepted win at a time. |
| [Runtime forensics](skills/patpat-loop/playbooks/runtime-forensics.md) | A live symptom: leak, idle spin, glitch. |
| [Trace forensics](skills/patpat-loop/playbooks/trace-forensics.md) | A captured profile, trace, or heap snapshot. |
| [Rationale forensics](skills/patpat-loop/playbooks/rationale-forensics.md) | Explain why code reached its current shape: code anchors first, evidence before narrative. |
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
| [Issue loop](skills/patpat-loop/playbooks/issue-loop.md) | Named-provider triage and reproduce. Avoids competing fixes, stays paused until enabled, and defaults provider-triggered issue-loop PRs to draft. |
| [Default delivery](skills/patpat-loop/playbooks/default-delivery.md) | When delivery intent exists, commit and open or update one ready PR after verify and review. Activation alone does not ship. |
| [Authorized delivery](skills/patpat-loop/playbooks/authorized-delivery.md) | Merge a green verified PR only on explicit land or merge; pause for deploy. |
| [Independent review](skills/patpat-loop/playbooks/independent-review.md) | Challenge an implementation and its proof without editing. |
| [Skill change](skills/patpat-loop/playbooks/skill-change.md) | Write or revise a SKILL.md. |
| [Behavioral evaluation](skills/patpat-loop/playbooks/behavioral-eval.md) | Test whether a skill triggers and behaves correctly. |
| [Project verifier](skills/patpat-loop/playbooks/project-verifier.md) | Build or repair project-local proof against the real system. |
| [Learning](skills/patpat-loop/playbooks/learning.md) | Encode a recurring failure as the smallest durable constraint. |
| [Automation design](skills/patpat-loop/playbooks/automation-design.md) | Design fail-closed automation for a named integration. |

</details>

## Skills

`patpat-loop` runs most of these when a step needs them. Reach for one directly when the task is already that operation.

<details>
<summary>Browse all skills</summary>

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
| [`patpat-ship`](skills/patpat-ship/SKILL.md) | Commit-and-PR when delivery intent exists; merge only when explicitly named. |
| [`patpat-skill`](skills/patpat-skill/SKILL.md) | Author a reusable skill. |
| [`patpat-eval`](skills/patpat-eval/SKILL.md) | Evaluate skill triggering with isolated prompts. |
| [`patpat-verifier`](skills/patpat-verifier/SKILL.md) | Create or maintain a project-specific verifier. |
| [`patpat-learn`](skills/patpat-learn/SKILL.md) | Encode a recurring failure. |
| [`patpat-automation`](skills/patpat-automation/SKILL.md) | Design fail-closed automation. Do not enable it yet. |
| [`patpat-engineer`](skills/patpat-engineer/SKILL.md) | Execute one isolated slice for a named owner. |

</details>

Principles live under [`skills/patpat-loop/principles/`](skills/patpat-loop/principles/). They are references, not discoverable skills. The [capability map](docs/guide/capability-map.md) records what is covered, gated, or left outside the core.

## Agent roles

Two roles, one contract each:

- `patpat-engineer` owns one bounded implementation slice and returns artifacts to the integration owner.
- `patpat-reviewer` is read-only and tries to break the implementation and its evidence.

Cursor and Antigravity ship a thin native adapter only for the reviewer. The engineer stays a portable skill until a host can enforce file ownership. Codex receives both roles as skills.

## Durable runs

[`patpat-run`](skills/patpat-run/SKILL.md) is a standard-library state machine, not a prose checklist. It refuses `ACT` without a proof contract, `REVIEW` without a current content-bound evidence file, and completion without independent review. The third identical blocker stops the run.

Multi-PR plans use a host-neutral checked JSON contract. Validate dependencies, owned files, proof surfaces, exact-head evidence, review gates, and delivery authority before implementation:

```bash
python3 skills/patpat-run/scripts/run_state.py --self-test
python3 skills/patpat-run/scripts/validate_plan.py --self-test
python3 skills/patpat-run/scripts/program_state.py --self-test
python3 skills/patpat-run/scripts/team_shape.py --self-test
```

The program store adds a dependency frontier, inbox, explicit dispatch and delivery gates, and head-bound verification records under Git metadata. It coordinates state without spawning agents or creating delivery authority. Dependency head changes invalidate downstream evidence.

`team_shape.py` recommends iterative, distributed, or adversarial work from an earned-parallelism gate receipt, explicit evidence, observed capacity, and a caller-owned worker budget. It never grants authority. Coordination uses compact receipts and typed handoff cards rather than replaying full agent transcripts.

## Where Patpat stops

Patpat does not turn capability into authority. These boundaries are deliberate:

- Writable arena, swarm, and autopilot require separate worktrees or host-enforced sandboxes and fall back to serial work
- Issue-loop stays paused until a named provider, sandbox, canary, and enable request exist; provider-triggered PRs stay draft without fresh interactive authority
- Merge of a red CI, package publish, and production deploy
- Model-selection presets and persona skills

After verify and review, delivery intent (not activation alone) commits and opens or updates a ready PR. Overnight work stops merge-ready. Only explicit land or merge language can merge when checks are green. Patpat still pauses for production deploy, force-push, secret rotation, and risky auth or billing changes.

## Validate

<details>
<summary>Full validation suite</summary>

```bash
python3 scripts/validate.py --self-test
python3 scripts/dry_run_loop.py --self-test
python3 scripts/eval_inspect.py --self-test
python3 scripts/eval_parallel.py --self-test
python3 scripts/eval_why.py --self-test
python3 scripts/install_skills.py --self-test
python3 scripts/update_skills.py --self-test
python3 scripts/stage_plugin.py --self-test
python3 hooks/scripts/patpat_loop_state.py --self-test
python3 skills/patpat-run/scripts/run_state.py --self-test
python3 skills/patpat-run/scripts/validate_plan.py --self-test
python3 skills/patpat-run/scripts/program_state.py --self-test
python3 skills/patpat-run/scripts/team_shape.py --self-test
python3 skills/patpat-ship/scripts/github_observe.py --self-test
python3 skills/patpat-ship/scripts/pr_watch.py --self-test
python3 scripts/smoke_codex_plugin.py
python3 scripts/smoke_antigravity_plugin.py
python3 scripts/smoke_grok_plugin.py
```

`eval_why.py` requires a source checkout with Git history; do not use it as an installed-artifact smoke test.

</details>

## Security and contributions

Report vulnerabilities privately through the [security policy](https://github.com/goiltpatpat/patpat/security/policy). Do not place secrets, private logs, or exploit details in a public issue. Pull requests should keep scope narrow and include observable evidence for the claim being changed; the repository template records that contract without prescribing a development style.

## License

MIT
