---
name: patpat-skill
description: Create or revise a reusable agent skill with precise triggering, progressive disclosure, and behavioral proof. Use when adding a SKILL.md workflow or changing a skill's routing contract.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"AgentSkill","requires_state":[],"produces_state":[],"verification_cmd":""}'
---

# Patpat Skill

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full. Do not load the router.

Read [repository truth](../patpat-loop/principles/repository-truth.md), [smallest safe change](../patpat-loop/principles/smallest-safe-change.md), and [encode lessons](../patpat-loop/principles/encode-lessons.md). Apply the [skill change playbook](../patpat-loop/playbooks/skill-change.md).

Inspect existing skills, host constraints, and repository conventions before editing.

- Keep frontmatter within the repository validator and selected host contract. Put positive and negative routing boundaries in the description.
- Use metadata for routing, `SKILL.md` for the active workflow, and references or scripts for conditional detail that saves entrypoint context. Treat token counts as review signals, not hard ceilings.
- Give every discoverable skill the `metadata.patpat.ontology` value shown below. Agent Skills metadata values must remain strings, so this namespaced value is compact JSON rather than a custom top-level field or nested YAML object.
- Keep `requires_state` limited to hard prerequisites. Use `produces_state` only for an observable post-condition with a unique producer. Leave either list empty when no stable dependency exists. Use an empty `verification_cmd` when the proof depends on the consuming project or task; never invent a universal command.
- Set `mutation_level` to the skill's default effect: `READ_ONLY`, `LOCAL_MUTATION`, or `DESTRUCTIVE`. Use `DESTRUCTIVE` for data-loss or externally durable effects such as commit, push, pull-request writes, publish, merge, or deploy. It does not classify every optional action or grant authority. Actual actions still follow the operating protocol. Use the controlled `target_entity` vocabulary: `AgentHost`, `AgentSkill`, `Artifact`, `Automation`, `Codebase`, `EngineeringTask`, `GitRepository`, `PullRequest`, `Task`, or `Workspace`.
- Keep state identifiers lowercase kebab-case. Every produced state must have exactly one producer, each required state must have one producer or be an observed root condition, and the dependency graph must be acyclic.
- Treat verification commands with placeholders as templates: resolve each placeholder from observed paths, pass values as separate safely quoted arguments, and never use `eval`. Do not add `workspace-map-current` as a hard prerequisite unless a workflow has a demonstrated need; the current catalog has no downstream hard consumer.
- Add or revise the canonical skill policy, route catalog, capability map, and user-facing skill listing when the skill set changes. Run structural validation and portable staging to prove the metadata survives the host projection.

```yaml
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"READ_ONLY","target_entity":"Codebase","requires_state":[],"produces_state":[],"verification_cmd":""}'
```

- Let the route catalog point to the owning skill. Allow intentional overlap and resolve it by the earliest unsettled decision.
- When changing routing, evaluate one prompt that should match and a neighboring prompt that should not.
- Give each skill one distinct responsibility. Add optional files only for an immediate, demonstrated need.
- A learn pass requires approval and edits existing files only. Do not mint a new `SKILL.md` or personal `*-mode` skill from learn.

Reuse repository-native scripts and patterns. Do not depend on undocumented host behavior, duplicate generic model knowledge, or add optional files without an immediate use.

Run structural validation after every change. Apply [`patpat-eval`](../patpat-eval/SKILL.md) when behavior, routing, or a description changes. Do not promote a skill because its prose appears complete.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
