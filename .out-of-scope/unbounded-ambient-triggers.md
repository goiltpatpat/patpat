# Unbounded Ambient Skill Triggers

## Rejected idea

Making every Patpat specialist skill ambiently model-invoked with long keyword trigger lists so the host automatically fires Patpat workflows on ordinary chat messages.

## Why it is out of scope

Ambient discovery imposes permanent **context load** (every skill description sits in every turn's prompt) and causes false-positive workflow activations that hijack ordinary requests or cross authority boundaries without explicit user opt-in.

## What we do instead

- Apply the **Two-Load & Two-Tier Invocation Model** (`skills/patpat-loop/references/operating-protocol.md` and `route-catalog.md`):
  - Keep user-invoked workflows marked `disable-model-invocation: true` (zero ambient context load, concise human-facing description).
  - Reserve ambient discovery for the explicit entry points (`patpat`, `patpat-loop`, `patpat-inspect`) and a minimal set of composable primitives when warranted.
  - Require explicit `/patpat` / `$patpat` activation for the Patpat loop, and compose specialists internally along declared `metadata.patpat.ontology` state-graph edges without expanding authority.
