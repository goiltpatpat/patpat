# Patpat

<img align="right" height="210" alt="Patpat mascot" src="assets/mascot.png">

[![Validate](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/goiltpatpat/patpat/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-2f6f5f.svg)](LICENSE)

**A little more proof. A lot less guesswork.**

Patpat is an evidence-driven operating layer for AI agents. It gives an agent the judgment of a careful senior engineer: understand the real problem, choose the right depth of work, make a focused change, prove the result on the surface that matters, and say plainly what is still unverified. It covers code and repository work, other deliverables such as documents and analyses, and mixed work, and it runs on Codex, Claude Code, Grok CLI, Antigravity, Cursor, and other Agent Skills hosts.

The mascot is friendly. The questions are quite persistent.

- **Understand before changing.** Inspect the real workspace, find the contract that matters, and protect work already in progress.
- **Make evidence part of the work.** Decide what would demonstrate success before acting, exercise the authoritative surface, and separate verified from assumed.
- **Keep people in control.** Scale the workflow to the risk, and never turn a capability into permission.

[Guide](docs/guide/README.md) · [Install and update](docs/guide/installing.md) · [Capability map](docs/guide/capability-map.md) · [Releases](https://github.com/goiltpatpat/patpat/releases) · [Security](https://github.com/goiltpatpat/patpat/security/policy)

<br clear="all">

## What Patpat is made of

```text
Protocol -> Playbooks -> Skills -> Evidence -> Host Adapters
```

| Layer | What it gives the agent |
| --- | --- |
| [Operating protocol](skills/patpat-loop/references/operating-protocol.md) | One spine of judgment, safety, authority, and evidence rules that every route follows. |
| [Playbooks](skills/patpat-loop/references/route-catalog.md) | Decision paths for specific situations: a defect, a migration, a PR handoff, a performance regression, a session takeover. |
| [Skills](#choose-a-skill) | 29 focused entry points, from read-only inspection to checked statecharts and delivery. |
| Evidence | Deterministic tools the agent can trust over its own summary: a durable-run state machine, plan and program validators, assignment fencing, TLA+/TLC model checking, receipt-bound reports. |
| Host adapters | Thin packaging for each host. They never redefine behavior or grant authority. |

Each layer may narrow the one before it. No layer may weaken a safety gate.

## Quick start

Requires Python 3.11 or newer. Install, start a **new** session, and confirm the agent can see Patpat; a package listing alone does not prove discovery.

| Host | Install | Invoke |
| --- | --- | --- |
| Codex | `codex plugin marketplace add goiltpatpat/patpat` then `codex plugin add patpat@patpat` | `$patpat` |
| Claude Code | `claude plugin marketplace add goiltpatpat/patpat` then `claude plugin install patpat@patpat` | `/patpat:patpat` |
| Grok CLI | `grok plugin install goiltpatpat/patpat --trust` | `/patpat` |
| Antigravity | From a [clean clone](docs/guide/installing.md#antigravity): `agy plugin validate <clone>` then `agy plugin install <clone>` | `/patpat` or host UI |
| Cursor | Customize → From GitHub Repository → `goiltpatpat/patpat` | `/patpat` |
| Other Agent Skills hosts | `python3 scripts/install_skills.py --target <proven skills dir> --dry-run`, then without `--dry-run` | `Use patpat to ...` |

Fresh-session invocation on Claude Code and Cursor, and Cursor's live import, are not yet verified by this project. The [installation guide](docs/guide/installing.md) covers local trees, portable packages, updates, removal, and per-host hook behavior. Agents installing Patpat follow [`AGENTS.md`](AGENTS.md).

Then give it a concrete task:

```text
$patpat reproduce this timeout, fix the cause, and verify the result. local only
$patpat explain where this request is validated and what could bypass it
$patpat plan the migration, identify the risks, and tell me what evidence we need
$patpat can our checkout charge a customer twice? show me the path
```

## How it works

```text
FRAME -> INSPECT -> PROOF CONTRACT -> ACT -> VERIFY
VERIFY -> REPORT when local, reversible, and not shipping
VERIFY -> REVIEW before delivery, high-risk work, or durable-run LEARN | REPORT
REVIEW -> LEARN? -> propose and wait for approval -> approved edit -> VERIFY -> REVIEW -> REPORT
```

- **The right depth, chosen for you.** A typo gets a quick check. Auth, billing, migrations, and cross-cutting work get design and independent review first. Patpat reads the risk signals; there are no modes to pick.
- **Proof before edits.** The agent names the claim, the surface that proves it, the action, the expected observation, and the cleanup before it changes anything. A build supports a claim; it does not prove user-visible behavior. Green is a signal, not an alibi.
- **Failures change the plan.** Failed evidence is classified as an implementation defect, a verifier defect, or an environment blocker, and the run returns to the earliest invalid step. Three identical failures stop the run and name the evidence needed to continue.
- **Honest reports.** Every claim is labeled `verified`, `partially verified`, `implemented but not verified`, or `not implemented`.
- **Beyond code.** For documents, analyses, and other deliverables, Patpat applies the same judgment through [general task guidance](skills/patpat-loop/references/general-task-judgment.md) without Git ceremony.

**Your words control delivery.** Activation authorizes the loop, proof, and verification. Commit-and-PR needs delivery intent; overnight or "don't stop" means verify, review, open a PR, and stop merge-ready. Merge needs the words land or merge. `local only` keeps work local, and `disable /patpat` turns Patpat off.

## Choose a skill

`/patpat` routes the task for you. Call a skill directly when the task is already that operation:

| Task | Skill |
| --- | --- |
| Explain how or why code works, without editing | [`patpat-inspect`](skills/patpat-inspect/SKILL.md) |
| Fix a reproducible bug from its root cause | [`patpat-debug`](skills/patpat-debug/SKILL.md) |
| Make one bounded feature or refactor | [`patpat-change`](skills/patpat-change/SKILL.md) |
| Settle a design, contract, or migration first | [`patpat-architect`](skills/patpat-architect/SKILL.md) |
| Prove a claim on the real app or artifact | [`patpat-verify`](skills/patpat-verify/SKILL.md) |
| Get an independent, skeptical review | [`patpat-review`](skills/patpat-review/SKILL.md) |
| Draw an architecture, workflow, or lifecycle diagram | [`patpat-repository-diagram`](skills/patpat-repository-diagram/SKILL.md) |
| Check whether a flow can get stuck or break a rule, and see the bug as a path | [`patpat-statechart`](skills/patpat-statechart/SKILL.md) |
| Drive or resume long multi-phase work | [`patpat-run`](skills/patpat-run/SKILL.md) |
| Commit and open a PR after verified work | [`patpat-ship`](skills/patpat-ship/SKILL.md) |

The diagram and statechart skills work as a pair: a lifecycle diagram can seed a statechart with the same labels, and a broken rule returns to the diagram as a guided story that marks where the flow goes wrong.

<details>
<summary>All 29 skills</summary>

| Skill | Use it when |
| --- | --- |
| [`patpat`](skills/patpat/SKILL.md) | Slash alias for the loop. |
| [`patpat-loop`](skills/patpat-loop/SKILL.md) | The work is non-trivial and needs the full loop. |
| [`00-workspace-mapper`](skills/00-workspace-mapper/SKILL.md) | Explicitly map an unfamiliar workspace. |
| [`patpat-inspect`](skills/patpat-inspect/SKILL.md) | Explain, audit, or diagnose without editing. |
| [`patpat-impact`](skills/patpat-impact/SKILL.md) | Prove blast radius and downstream invariants. |
| [`patpat-plan`](skills/patpat-plan/SKILL.md) | Sequence verifiable phases without implementing them. |
| [`patpat-architect`](skills/patpat-architect/SKILL.md) | Settle contracts, migrations, and risk first. |
| [`patpat-interrogate`](skills/patpat-interrogate/SKILL.md) | Challenge a design or change from adversarial perspectives. |
| [`patpat-repository-diagram`](skills/patpat-repository-diagram/SKILL.md) | Turn an idea, plan, or codebase into an interactive diagram. |
| [`patpat-statechart`](skills/patpat-statechart/SKILL.md) | Chart how a flow moves between states, check its rules with TLC, and show each bug as a path. |
| [`patpat-change`](skills/patpat-change/SKILL.md) | Implement one bounded feature or refactor. |
| [`patpat-debug`](skills/patpat-debug/SKILL.md) | Reproduce, root-cause, and fix. |
| [`patpat-perf`](skills/patpat-perf/SKILL.md) | Improve a measured resource regression. |
| [`patpat-game-builder`](skills/patpat-game-builder/SKILL.md) | Build a playable game slice, then verify the real player path. |
| [`patpat-verify`](skills/patpat-verify/SKILL.md) | Test a claim on the real artifact or user surface. |
| [`patpat-verifier`](skills/patpat-verifier/SKILL.md) | Create or maintain a project-specific verifier. |
| [`patpat-formal-verify`](skills/patpat-formal-verify/SKILL.md) | Create and maintain bounded formal models that later changes rerun. |
| [`patpat-review`](skills/patpat-review/SKILL.md) | Independently try to falsify a change and its evidence. |
| [`patpat-unslop`](skills/patpat-unslop/SKILL.md) | Cut filler from engineering docs, PR text, and diffs. |
| [`patpat-run`](skills/patpat-run/SKILL.md) | Drive or resume a durable multi-phase graph. |
| [`patpat-engineer`](skills/patpat-engineer/SKILL.md) | Execute one isolated slice for a named owner. |
| [`patpat-arena`](skills/patpat-arena/SKILL.md) | Compete isolated attempts and synthesize one verified result. |
| [`patpat-swarm`](skills/patpat-swarm/SKILL.md) | Cover slices or races and return one report. |
| [`patpat-ship`](skills/patpat-ship/SKILL.md) | Commit-and-PR with delivery intent; merge only when named. |
| [`patpat-learn`](skills/patpat-learn/SKILL.md) | Encode a recurring failure as the smallest durable constraint. |
| [`patpat-skill`](skills/patpat-skill/SKILL.md) | Author a reusable skill. |
| [`patpat-eval`](skills/patpat-eval/SKILL.md) | Evaluate skill triggering and behavior with an evidence rubric. |
| [`patpat-automation`](skills/patpat-automation/SKILL.md) | Design fail-closed automation without enabling it. |
| [`patpat-setup`](skills/patpat-setup/SKILL.md) | Install, validate, or remove Patpat on a host. |

</details>

<details>
<summary>All playbooks</summary>

| Playbook | For |
| --- | --- |
| [Investigation](skills/patpat-loop/playbooks/investigation.md) | Read-only explanation: how it works, where it lives, who owns it. |
| [Rationale forensics](skills/patpat-loop/playbooks/rationale-forensics.md) | Why code reached its current shape, code anchors first. |
| [Defect](skills/patpat-loop/playbooks/defect.md) | Reproduce a failure, prove the root cause, fix it with runtime evidence. |
| [Regression first](skills/patpat-loop/playbooks/regression-first.md) | A cheap deterministic test exists: write the failing check, then the fix. |
| [Runtime forensics](skills/patpat-loop/playbooks/runtime-forensics.md) | A live symptom: leak, idle spin, glitch. |
| [Trace forensics](skills/patpat-loop/playbooks/trace-forensics.md) | A captured profile, trace, or heap snapshot. |
| [Performance](skills/patpat-loop/playbooks/performance.md) | Measured slowness against a comparable baseline. |
| [Metric hillclimb](skills/patpat-loop/playbooks/metric-hillclimb.md) | Sustained improvement of one metric, one accepted win at a time. |
| [Blast radius](skills/patpat-loop/playbooks/blast-radius.md) | What else a change could break, proven rather than asserted. |
| [Architecture change](skills/patpat-loop/playbooks/architecture-change.md) | Contracts, migrations, or a redesign that must settle before code. |
| [Bounded change](skills/patpat-loop/playbooks/bounded-change.md) | New or changed behavior from a named data shape. |
| [Behavior-preserving refactor](skills/patpat-loop/playbooks/behavior-preserving-refactor.md) | Structure changes without behavior changes. |
| [Prototype](skills/patpat-loop/playbooks/prototype.md) | A throwaway sketch that makes a design decision cheap. |
| [Visual equivalence](skills/patpat-loop/playbooks/visual-equivalence.md) | Pixel-level UI parity between two implementations. |
| [Bespoke workflow](skills/patpat-loop/playbooks/bespoke-workflow.md) | No narrow playbook fits: design a falsifiable sequence. |
| [Multi-phase run](skills/patpat-loop/playbooks/multi-phase-run.md) | Work that spans phases, checkpoints, or a durable graph. |
| [Session pickup](skills/patpat-loop/playbooks/session-pickup.md) | Continue your own interrupted work. |
| [Session takeover](skills/patpat-loop/playbooks/session-takeover.md) | Take over in-flight work from live repository state. |
| [Pause safely](skills/patpat-loop/playbooks/pause-safely.md) | Pause in-flight work without opening a PR or merging. |
| [PR drive](skills/patpat-loop/playbooks/pr-drive.md) | Address authorized PR findings; land only when explicitly requested. |
| [PR readiness handoff](skills/patpat-loop/playbooks/pr-handoff.md) | Bring a PR to verified merge-ready, then return control. |
| [Worktree cleanup](skills/patpat-loop/playbooks/worktree-cleanup.md) | Prune merged or abandoned Git worktrees. |
| [Arena](skills/patpat-loop/playbooks/arena.md) | Competing isolated attempts at one brief, then a verified synthesis. |
| [Swarm](skills/patpat-loop/playbooks/swarm.md) | Parallel slices or races, one aggregated report. |
| [Autopilot](skills/patpat-loop/playbooks/autopilot.md) | A verified queue or stack; merge only when named. |
| [Issue loop](skills/patpat-loop/playbooks/issue-loop.md) | Named-provider triage and reproduction; paused until enabled, PRs default to draft. |
| [Default delivery](skills/patpat-loop/playbooks/default-delivery.md) | With delivery intent, commit and open one ready PR after verify and review. |
| [Authorized delivery](skills/patpat-loop/playbooks/authorized-delivery.md) | Merge a green verified PR only on explicit land or merge. |
| [Independent review](skills/patpat-loop/playbooks/independent-review.md) | Challenge an implementation and its proof without editing. |
| [Skill change](skills/patpat-loop/playbooks/skill-change.md) | Write or revise a SKILL.md. |
| [Behavioral evaluation](skills/patpat-loop/playbooks/behavioral-eval.md) | Test whether a skill triggers and behaves correctly. |
| [Project verifier](skills/patpat-loop/playbooks/project-verifier.md) | Build or repair project-local proof against the real system. |
| [Learning](skills/patpat-loop/playbooks/learning.md) | Encode a recurring failure as the smallest durable constraint. |
| [Automation design](skills/patpat-loop/playbooks/automation-design.md) | Design fail-closed automation for a named integration. |
| [Build a playable slice](skills/patpat-game-builder/playbooks/build-playable-slice.md) | The smallest end-to-end game loop for a concrete brief. |
| [Diagnose gameplay](skills/patpat-game-builder/playbooks/diagnose-gameplay.md) | Find the first gameplay state that diverges from the expected result. |
| [Verify a playthrough](skills/patpat-game-builder/playbooks/verify-playthrough.md) | Prove rules, input, visuals, and target-runtime behavior separately. |
| [Visual iteration](skills/patpat-game-builder/playbooks/visual-iteration.md) | Improve requested game presentation against frozen conditions. |

</details>

## Durable runs and coordination

[`patpat-run`](skills/patpat-run/SKILL.md) is a standard-library state machine, not a prose checklist. It refuses `ACT` without a proof contract, `REVIEW` without a current content-bound evidence file, and completion without independent review. The third identical blocker stops the run, and work survives context loss because state lives in Git metadata rather than the conversation.

Multi-PR programs use a checked JSON plan. The program store validates dependencies, owned files, proof surfaces, exact-head evidence, review gates, and delivery authority; it fences each assignment with a generation token, and a dependency's head change invalidates downstream evidence. The fencing rule is model-checked with TLA+. The store coordinates state; it does not spawn agents or grant authority. See [durable runs](docs/guide/06-durable-runs.md) and [earned parallelism](docs/guide/07-earned-parallelism.md).

Two agent roles keep parallel work honest: `patpat-engineer` owns one bounded slice and returns artifacts to the integration owner, and the reviewer role ([`patpat-review`](skills/patpat-review/SKILL.md)) is read-only and tries to break the result and its evidence. Workers never ship; the parent verifies the integrated result. Host-specific reviewer adapters are listed in the [capability map](docs/guide/capability-map.md#host-adapter-boundary).

## Where Patpat stops

Patpat does not turn capability into authority, and it does not claim more than its evidence shows:

- **It guides; hosts enforce.** Patpat is instructions plus deterministic scripts. Prose cannot stop an edit; only a host-enforced gate can, and no such edit gate ships today.
- **No measured-improvement claim yet.** There is no published benchmark of agents with and without Patpat.
- **It coordinates; it does not run agents.** Spawning, monitoring, waking, scheduling, and cancelling workers belong to the host.
- **Parallel writes need isolation.** Arena, swarm, and autopilot require separate worktrees or host sandboxes and otherwise fall back to serial work.
- **Risky actions always pause.** Production deploy, package publish, force-push, data deletion, secret rotation, and risky auth or billing changes need explicit approval. A real CI failure blocks merge.
- **No model presets.** Workers inherit the parent model unless you or the host choose; see [model choice](skills/patpat-setup/SKILL.md#model-choice).

## Trust model

| Question | Answer |
| --- | --- |
| What writes does it make? | Your working tree, only for the requested task. Durable-run state under Git metadata (`.git/patpat/`, or the worktree's Git directory). Session mode under the host's plugin data folder. `.patpat/context-graph.json` only when you ask for a workspace map. |
| What leaves the machine? | No telemetry. Delivery pushes with `git` and calls GitHub through your `gh` CLI. The first native statechart run downloads Java and TLC through mise. Diagram source links query the public GitHub API only when you opt in. |
| What persists across sessions? | Host hooks restore Patpat mode after resume only where the [capability map](docs/guide/capability-map.md#sticky-mode-hook-status) records it; elsewhere, invoke Patpat again. |
| How is a result proven? | On its authoritative surface: the real app, artifact, or test, not a summary. Independent review is required before delivery and for high-risk work. |

## Requirements

| Use | Needs |
| --- | --- |
| Core skills, hooks, durable runs, diagrams, saved model checks and replay | Python 3.11+, standard library only |
| Native statechart and TLA+ model checking | Node 22.18 to 22.x or 23.6+ (or Bun 1.1.5+, Deno 2+), Java 11+, and TLC; mise installs Java and TLC on first run, or set `TLA2TOOLS` |
| Saved-receipt statechart rendering | Node 22.18 to 22.x or 23.6+, and `npm ci` in `skills/patpat-statechart/scripts` |
| Delivery and PR observation | `git` and an authenticated `gh` |

## Extend and validate

Run the repository contract checks with `python3 scripts/validate.py --self-test`; the [installation guide](docs/guide/installing.md#verification) lists the extended local checks, and the [CI workflow](https://github.com/goiltpatpat/patpat/blob/main/.github/workflows/validate.yml) is the authoritative list. [Extending Patpat](docs/guide/extending.md) and [extend and evaluate](docs/guide/08-extend-and-evaluate.md) explain how to add a skill or playbook and how to test whether it routes and behaves correctly. Principles live under [`skills/patpat-loop/principles/`](skills/patpat-loop/principles/); they are references, not discoverable skills.

## Security, support, and contributions

Report vulnerabilities privately through the [security policy](https://github.com/goiltpatpat/patpat/security/policy); never put secrets, private logs, or exploit details in a public issue. The current `main` branch and the latest tagged release are supported. Pull requests should keep scope narrow and include observable evidence for the claim they change.

## License

MIT. [`skills/patpat-statechart`](skills/patpat-statechart/THIRD_PARTY_NOTICES.md) and [`skills/patpat-repository-diagram`](skills/patpat-repository-diagram/references/THIRD_PARTY_NOTICES.md) include third-party code under MIT; their notices travel with each skill.
