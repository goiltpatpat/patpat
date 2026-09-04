# Patpat Capability Map

This map defines the engineering outcomes Patpat owns, the controls that bound them, and the surfaces that remain deliberately gated or outside the core. Repository artifacts and executable behavior are authoritative. Capability is not measured by skill or file count.

## Control model

```text
Protocol -> Playbooks -> Skills -> Evidence -> Host Adapters
```

- The [operating protocol](../../skills/patpat-loop/references/operating-protocol.md) defines judgment, safety, authority, and evidence invariants.
- Playbooks turn those invariants into task-specific decision paths.
- Skills expose focused entry points without replacing the protocol.
- Evidence binds claims to an observable surface and current repository state.
- Host adapters package the canonical `skills/` tree; they do not redefine behavior or grant authority.

Each layer may narrow the one before it. No layer may weaken a safety gate or turn capability into permission.

## Reading the map

Availability and evidence are separate dimensions:

| Availability | Meaning |
| --- | --- |
| `available` | Patpat has an owned control path for the outcome. |
| `gated` | The path exists but remains unavailable until named preconditions pass. |
| `outside core` | The outcome belongs to the host, project, or ordinary agent competence. |

| Evidence level | Required basis |
| --- | --- |
| `specified` | The invariant and authority boundary are explicit. |
| `contract-tested` | A deterministic check passes on the claimed revision. |
| `behavior-evaluated` | A representative agent run produces an inspectable receipt. |
| `host-verified` | A named host, revision, and lifecycle stage are observed directly. |

These labels are claims, not decoration. Missing or stale evidence lowers the evidence level. Evidence from one host does not transfer to another.

## Operational capabilities

The table records availability and the required proof surface. It does not assign permanent evidence levels; record those in the revision-bound run or host receipt when the claim is made.

| Outcome | Availability | Control owner | Proof surface and boundary |
| --- | --- | --- | --- |
| Route and control engineering work | `available` | [`patpat-loop`](../../skills/patpat-loop/SKILL.md), operating protocol, and [route catalog](../../skills/patpat-loop/references/route-catalog.md) | Validate routing and protocol reachability. Explicit activation is required; resemblance to a workflow does not activate Patpat. |
| Understand and design | `available` | [`patpat-inspect`](../../skills/patpat-inspect/SKILL.md), [`patpat-impact`](../../skills/patpat-impact/SKILL.md), [`patpat-plan`](../../skills/patpat-plan/SKILL.md), and [`patpat-architect`](../../skills/patpat-architect/SKILL.md) | Inspect repository evidence and return falsifiable findings, boundaries, or plans. Read-only work does not mutate or ship. |
| Change, debug, and improve performance | `available` | [`patpat-change`](../../skills/patpat-change/SKILL.md), [`patpat-debug`](../../skills/patpat-debug/SKILL.md), and [`patpat-perf`](../../skills/patpat-perf/SKILL.md) | Prove changed behavior on the repository's authoritative test or runtime surface. Builds and static checks alone do not prove user-visible behavior. |
| Verify and challenge claims | `available` | [`patpat-verify`](../../skills/patpat-verify/SKILL.md), [`patpat-review`](../../skills/patpat-review/SKILL.md), and [`patpat-verifier`](../../skills/patpat-verifier/SKILL.md) | Bind verification to current inputs and artifacts. Independent review must use a distinct actor; declared identity is not host-attested independence. |
| Execute durable work | `available` | [`patpat-run`](../../skills/patpat-run/SKILL.md), the [execution graph](../../skills/patpat-loop/references/execution-graph.md), and checked run/program state | [`run_state.py`](../../skills/patpat-run/scripts/run_state.py), [`validate_plan.py`](../../skills/patpat-run/scripts/validate_plan.py), and [`program_state.py`](../../skills/patpat-run/scripts/program_state.py) enforce transitions and freshness. State coordinates work; it does not spawn agents or grant delivery authority. |
| Deliver verified work | `available` | [`patpat-ship`](../../skills/patpat-ship/SKILL.md) and the provider-neutral [`pr_watch.py`](../../skills/patpat-ship/scripts/pr_watch.py) evaluator | Activation authorizes the loop, proof, and verify. Default commit and ready PR require delivery intent. Merge requires explicit `land` or `merge` language and current green evidence. |
| Extend and learn | `available` | [`patpat-skill`](../../skills/patpat-skill/SKILL.md), [`patpat-eval`](../../skills/patpat-eval/SKILL.md), and [`patpat-learn`](../../skills/patpat-learn/SKILL.md) | Add the smallest reusable constraint for a reproduced failure. A prose change alone does not prove behavioral improvement. |
| Design bounded automation | `available` | [`patpat-automation`](../../skills/patpat-automation/SKILL.md) | Specify idempotency, retries, compensation or an irreversible boundary, observability, and a kill switch. Design and scaffolding do not authorize enabling, scheduling, or external writes. |
| Install and update | `available` | [`patpat-setup`](../../skills/patpat-setup/SKILL.md), host manifests, staging, installer, updater, and smoke scripts | Follow the [installation reference](./installing.md). Package validation, discovery, execution, sticky state, mutation, delivery, and live evaluation remain separate claims. |

## Guarded capabilities

Every capability in this section is `gated` and remains fail closed until its admission evidence is current.

| Capability | Admission gate | Safe fallback |
| --- | --- | --- |
| Writable arena, swarm, or coordinated fan-out | A content-bound earned-parallelism receipt validated by [`team_shape.py`](../../skills/patpat-run/scripts/team_shape.py), isolated workspaces and resources, a named integration owner, stable verification, and whole-system proof | Run serially. Read-only investigation may fan out across independent evidence sources. |
| Pull-request readiness verdict | Provider evidence must bind repository, pull request, base, and exact head. Provider restrictions are authoritative lower bounds. | Read-only observation may return unknown or blocked. A watcher `ready` verdict returns a handoff and never grants merge authority. |
| Provider-triggered issue automation | A named provider, exact write contract, sandbox, canary, explicit enable request, and fresh authority | Stay paused or triage read-only. Provider-triggered pull requests remain draft without separate interactive delivery authority. |
| Irreversible or high-risk mutation or delivery | Explicit approval for force-push, package publish, production deploy, secret rotation, destructive operations, or risky auth, billing, and permission changes | Pause and report blast radius, rollback, and required proof. |

## Host adapter boundary

The canonical behavior lives in `skills/`. A host manifest, command wrapper, hook, or reviewer adapter may expose that behavior only within capabilities the host can prove. Installation does not prove prompt-time discovery; discovery does not prove execution; execution does not prove sticky state, mutation, delivery, or live evaluation. Record host claims with the host name, Patpat revision, lifecycle stage, and receipt.

## Deliberate non-goals

These surfaces are `outside core`. Patpat does not own generic teaching or technical writing, language style catalogs, personas, model presets, chat-history preference mining, generic memory, simulator maintenance, or host-specific bot interfaces and schedulers. Keep them as ordinary agent capabilities or project/host extensions unless a repeated engineering failure demonstrates a Patpat-specific control need.

## Maintenance contract

1. Start from a reproduced decision or failure mode that existing controls cannot express cleanly.
2. Place the correction at the lowest effective layer: protocol, principle, playbook, skill, deterministic script, or host adapter.
3. Define the invariant, falsifier, proof surface, freshness rule, and authority boundary before adding an artifact.
4. Classify availability separately from evidence. Deterministic fixtures are contract evidence, not behavioral agent evidence.
5. Bind behavioral and host claims to the tested revision. Downgrade stale, missing, or cross-host evidence.
6. Reject expansion when an existing artifact can express the rule or when complexity exceeds demonstrated value.
7. Validate map changes with `python3 scripts/validate.py --self-test` and `git diff --check`.
