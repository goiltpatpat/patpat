---
name: patpat-swarm
description: Fan out isolated workers across parallel slices or races and return one aggregated report.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"GitRepository","requires_state":["execution-plan-settled"],"produces_state":["swarm-slices-integrated"],"verification_cmd":"git status --short"}'
---

# Patpat Swarm

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full. Do not load the router.

Read [earned parallelism](../patpat-loop/principles/earned-parallelism.md) and apply the [swarm playbook](../patpat-loop/playbooks/swarm.md). Every worker must read the [worker contract](../patpat-engineer/references/worker-contract.md) first: line 1 of every spawned subagent/worker kickoff MUST be `Read <abs-path>/skills/patpat-engineer/references/worker-contract.md before anything else.` (resolved to the absolute path, because slash-command skills do not auto-load in spawned agents).

Read-only coverage may run in parallel. Every writable worker needs a separate Git worktree or host-enforced sandbox plus all earned-parallelism gates. Disjoint paths in one worktree are not isolation. If those gates fail, run serially and name missing lanes. Inherit the parent model unless the user named models or the host lets the parent choose; then follow [model choice](../patpat-setup/SKILL.md#model-choice). Do not invent coverage for a silent worker. The parent verifies the integrated result.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
