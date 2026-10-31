---
name: patpat
description: Explicit alias for Patpat Loop. Use only when the user invokes /patpat, $patpat, /patpat-loop, or $patpat-loop, or directly asks to activate Patpat mode.
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Task","requires_state":["workspace-root-open"],"produces_state":["patpat-mode-activated"],"verification_cmd":"git status --short"}'
---

# Patpat

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

Read and follow [`patpat-loop`](../patpat-loop/SKILL.md) in full. `/patpat` and `/patpat-loop` are the same entry point.
