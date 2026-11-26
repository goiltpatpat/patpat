---
name: patpat-arena
description: Run isolated competing attempts at one brief, pick a base, graft the strongest parts, and verify the synthesis.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"GitRepository","requires_state":["execution-plan-settled"],"produces_state":["arena-candidate-selected"],"verification_cmd":"git status --short"}'
---

# Patpat Arena

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

When invoked directly, read the [operating protocol](../patpat-loop/references/operating-protocol.md) and [execution graph](../patpat-loop/references/execution-graph.md) in full. Do not load the router.

Read [earned parallelism](../patpat-loop/principles/earned-parallelism.md) and apply the [arena playbook](../patpat-loop/playbooks/arena.md).

Fan out writable attempts only after each worker has a separate Git worktree or host-enforced sandbox with its own Git index (in Git repos) or isolated filesystem boundary (in non-Git sandboxes) and process boundary. Disjoint files or directories in one worktree are not isolation. If isolation is unavailable, run one serial attempt and say so. Inherit the parent model unless the user named models or the host lets the parent choose (per `patpat-setup` `#model-choice`, linked in the arena playbook).

## Orthogonal constraints and deep-module judging

Avoid homogeneous races that converge on the same local optimum. Assign each isolated candidate a distinct **Design It Twice** orthogonal constraint—such as *minimal interface (1–3 entry points)*, *maximum flexibility*, *common-caller ergonomics*, or *ports and adapters*—grounded in the **Deep Modules** vocabulary (*Module, Interface, Implementation, Adapter, Depth, Seam*).

When an empirical question (performance, ergonomics, failure mode, or integration behavior) can settle a fork, run a throwaway isolated prototype before escalating a choice to the user; reserve user escalation for genuine product preferences or authority boundaries.

Challenge each surviving candidate with the [arena playbook](../patpat-loop/playbooks/arena.md) before selection, scoring **Depth**, **Locality**, and **Seam** placement alongside correctness and proof strength. Use a separate reviewer only when available, authorized, and within the earned worker budget; otherwise the parent performs the adversarial pass and reports that it was not independently attested. **Cross-Vendor Judge Rule:** when selecting a separate judge or second-opinion reviewer, use a model from a different vendor than the author (same-vendor families—such as two Claude models or two GPT/Codex models—cannot judge each other). **2-Failure Escalation Rule:** escalate model tier only when the user explicitly requests it or after two failed runs of the same brief, never on perceived difficulty alone. The parent owns pick, graft (only where the synthesis stays deeper than either base), verification, and any authorized delivery. Worker output is a candidate, not a completed change.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
