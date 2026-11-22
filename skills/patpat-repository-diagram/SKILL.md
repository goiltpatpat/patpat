---
name: patpat-repository-diagram
description: Turn a brief, plan, or codebase into a self-contained interactive HTML/SVG diagram with typed views and stable IDs.
disable-model-invocation: true
metadata:
  patpat.ontology: '{"schema":"patpat-ontology/v1","mutation_level":"LOCAL_MUTATION","target_entity":"Artifact","requires_state":["workspace-root-open"],"produces_state":["interactive-diagram-rendered"],"verification_cmd":"python3 scripts/validate.py"}'
---

# Patpat Interactive Diagram

Before following this skill, apply the [skill state and mutation gate](../patpat-loop/references/operating-protocol.md#skill-state-and-mutation-gate).

Use this route only when the user explicitly requests a diagram, map, visual explainer, or shareable view. Deliver a self-contained HTML artifact with editable typed JSON and SVG, preserving stable IDs on refinements. Patpat owns the schema, renderer, layout, viewer, and output contract (never install Archify). See [design references](references/spec-contract.md#selected-design-references) and [third-party notices](references/THIRD_PARTY_NOTICES.md). Replace `<skill-root>` with the absolute directory containing this loaded `SKILL.md` before running scripts.

Route rule-checking, state reachability, TLA+/TLC statecharts, or saved `patpat-model-check-receipt` visuals to [patpat-statechart](../patpat-statechart/SKILL.md). Reserve `docs/diagrams/` strictly for repository architecture and structural diagrams (never statechart verification runs). A TLC invariant violation marks a model state, not a lifecycle terminal or runtime defect proof.

## Scope and route

Create diagrams only; route prose explanations to [patpat-inspect](../patpat-inspect/SKILL.md), downstream risk to [patpat-impact](../patpat-impact/SKILL.md), and code edits to engineering skills.

| Type | Use for |
| --- | --- |
| `architecture` | Component ownership, calls, stores, and supported boundaries |
| `workflow` | Ordered work, gates, branches, retries, and outcomes |
| `sequence` | Calls and returns over time, including async messages |
| `dataflow` | Sources, transformations, stores, and consumers |
| `lifecycle` | States, transitions, retries, cancellation, and terminal outcomes |

Choose the smallest fitting view and state why; ask only if the choice changes the story. Default destination: `docs/diagrams/<slug>` (or repo/request convention). Overwrite an existing artifact only on an explicit replacement request.

For repository-backed diagrams, follow [repository truth](../patpat-loop/principles/repository-truth.md), [investigation playbook](../patpat-loop/playbooks/investigation.md), and [how-report contract](../patpat-inspect/references/how-report.md); read [operating protocol](../patpat-loop/references/operating-protocol.md) in full for security, cross-cutting, or material architecture questions without loading the router.

## Evidence and authoring

Separate user-brief claims (not code-verified) from repository evidence. For repo-backed diagrams, record Git root, full `HEAD`, dirty state, and normalized relative paths with inclusive line ranges (`confirmed` = directly evidenced, `inferred` = reasoned, `unknown` = stated gap). Never present static paths as runtime behavior or embed source snippets, credentials, tokens, or private URLs.

Author typed JSON outside the target repository in the user's language per [schema and evidence contract](references/spec-contract.md#schema-evidence-and-layout-fields) and [typed graph rules](references/spec-contract.md#typed-graph-contract) (`render.py guide <type> --format text`). Start with automatic layout and add explicit position/route hints only to fix measured geometry issues without suppressing blocking warnings. Apply layout guardrails, reader-first composition, story views, and optional Python import-map rules from [authoring and rendering guide](references/authoring-and-rendering.md).

## Render and prove

Use the bundled renderer exclusively: run `validate` -> `finalize` -> `check` (passing `--repo-root` whenever citing repo files). Consult [authoring and rendering guide](references/authoring-and-rendering.md#render-browser-gate-and-comparison-details) and [spec contract](references/spec-contract.md#finalization-and-browser-checks) for schema 1 vs 2, transactional `finalize`, Chromium browser checks, [interactive viewer](references/spec-contract.md#interactive-viewer), [preview](references/spec-contract.md#preview), [comparison](references/spec-contract.md#architecture-comparison), and cleanup. Inspect the rendered artifact at reader size; report only checks actually run.

## Report

Return links to the HTML and editable JSON (plus SVG/receipt when useful), or editable source for chat-only visuals with unavailable render checks noted. State the exact revision and committed vs working-tree files for repo evidence, or note brief-only unverified claims. Report semantic review, structural checks, browser checks, visual inspection, and unresolved unknowns separately.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
