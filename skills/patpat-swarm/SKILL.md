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

Read [earned parallelism](../patpat-loop/principles/earned-parallelism.md) and apply the [swarm playbook](../patpat-loop/playbooks/swarm.md). Every worker must follow the [worker contract](../patpat-engineer/references/worker-contract.md): for filesystem-capable workers that can read the skill tree, line 1 of the kickoff MUST be `Read <abs-path>/skills/patpat-engineer/references/worker-contract.md before anything else.` (resolved path, because slash-command skills do not auto-load in spawned agents); for sandboxed or no-filesystem subagents (such as `browser` or workspace-jailed agents) that cannot read outside the sandbox, omit that `Read` line and inline the compact worker contract summary (operator = user, bounded scope, no ship/external writes, no unauthorized spawn, no `sleep`/polling loops, raw evidence only) at the top of the brief.

Read-only coverage may run in parallel. Every writable worker needs a separate Git worktree or host-enforced sandbox with its own Git index (in Git repos) or isolated filesystem boundary (in non-Git sandboxes) plus all earned-parallelism gates. Disjoint paths in one worktree are not isolation. If those gates fail (including non-Git workspaces without a host-enforced filesystem sandbox), run serially and name missing lanes. Separate write targets before serializing shared state (per-worker files, keys, or branches merged at read time; serialize structurally only for true single-writer invariants). Inherit the parent model unless the user named models or the host lets the parent choose (per `patpat-setup` `#model-choice`, linked in the swarm playbook). Do not invent coverage for a silent worker. The parent verifies the integrated result.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
