# Model-check receipt statecharts

Use this path when a saved `patpat-model-check-receipt` already contains the bounded result, selected trace, raw TLC action, and `changed_keys`. It projects that evidence into a reader-facing statechart. It does not parse TLA+, invoke TLC, or replay the Python implementation.

## Data flow

```text
saved receipt JSON + explicit view mapping
    -> strict receipt/view checks
    -> selected-trace projection into the statechart Chart IR (scripts/ir.ts)
    -> statechart Mermaid backend (scripts/backends/mermaid.ts) + local Pele SVG
    -> Patpat evidence manifest and HTML
```

The receipt is the normalized model-check input. Do not feed a selected path to the native command's compiler or graph passes as if it were the complete reachable graph. The view mapping is the authored presentation layer: it provides state labels, phase names, semantic step descriptions, and a per-step implementation mapping. Descriptions are explicitly tagged as authored interpretations and anchored to expected receipt state values and `changed_keys`; they are not passed off as raw TLC action names. Each step must either reference source ranges and state an expected code effect, or say why the available receipt cannot support a code mapping. A stale or ambiguous mapping fails closed.

The renderer accepts only `kind: patpat-model-check-receipt` with integer `schema_version: 1`; it rejects unsupported receipt/view schema versions and malformed evidence before output publication. The output retains exact raw states/actions/deltas, receipt/model/source digests, view and renderer digests, bounds, mutant identity, target invariant, trace-selection method, and TLC counterexample count. Trace rows must have consecutive indexes, a well-formed state object, a sorted unique `changed_keys` list, and deltas that recompute from adjacent states. The final state alone carries the invariant marker.

The three outputs have different meanings:

| Layer | Meaning | Required presentation |
| --- | --- | --- |
| Bounded model (TLC) | Result for the exact receipt and finite bounds | Show bounds, baseline/mutant, target invariant, reported counterexample count, and whether the diagram shows a selected path |
| Implementation mapping | Static source crosswalk | Show repository-relative source locations and digests; do not relabel a generic TLA action as a Python function call |
| Replay | Execution against the Python implementation | Emit `not-run / model-only` when no replay report is supplied; otherwise show only the report validated against the exact receipt, model, and current implementation digest |

Each invariant-breaking trace endpoint is a state with an explicit red violation marker. It is not a `terminal` kind and does not imply that a process stopped. Phase colors and violation marks are separate visual dimensions. A baseline receipt with no trace becomes a bounded-result panel with the invariant results; never invent a model path for it. Counterexample counts include all TLC-reported paths while the chart identifies the one selected path stored in the receipt.

Every connector is labeled with the authored, reader-facing action and exact `changed_keys` delta. Each adjacent transition card shows the raw TLC action from the receipt and keeps the static implementation mapping in its own labeled section. The Mermaid export also records the complete authored interpretation, raw action, source mapping, expected effect or unmapped reason, bounds, mutant, invariant, counterexample count, trace-selection method, provenance hashes, and replay status.

Mermaid state-transition labels reserve `:` and `;` as grammar delimiters. In the Mermaid edge label only, the Mermaid backend writes those characters as `#58;` and `#59;` while preserving Unicode combining marks (`\p{M}`) in UTF-8; the exact raw action remains in the adjacent `%%` evidence comment, projected JSON, and HTML details. This avoids a raw receipt action being split into extra Mermaid statements ([state parser](https://github.com/mermaid-js/mermaid/blob/develop/packages/mermaid/src/diagrams/state/parser/stateDiagram.jison#L142-L144), [semicolon report](https://github.com/mermaid-js/mermaid/issues/5410)).

## View mapping contract

The AssignmentGeneration pilot at [`../examples/assignment-generation-statechart.view.json`](../examples/assignment-generation-statechart.view.json) demonstrates the strict JSON shape. Its state entries contain an index, a reader-facing label, a phase, concise facts, an expected subset of raw state values, and a `violation` marker. Its edge entries contain source/target indexes, a reader-facing label, the exact expected raw TLC action, and the exact expected `changed_keys` list. The renderer also recalculates each delta from adjacent state snapshots and refuses mismatches.

The version 2 view file binds model path, bounds, mutant ID, mutant constants, target invariant, receipt name, and each transition's source mapping/expected effect or explicit unmapped reason. It must cover every state and every transition in each selected trace. It must mark only the final state as violating for the targeted counterexample. Baseline entries must have no states or steps, `mutant_id: null`, and all saved properties must pass with zero counterexamples.

Implementation references use repository-relative paths and inclusive line ranges. Rendering hashes the current model bytes, each source file/range, the view mapping, and the renderer; it records the Git head and tracked working-tree dirty flag and refuses stale model digests or missing source ranges. This is a source snapshot binding, not runtime correspondence proof. Static mapping describes the expected behavior of the referenced code and does not replace replay evidence.

## Command

Create a new output path. The renderer refuses an output path that already exists, stages its files privately beside the destination, and publishes with an atomic no-replace operation only after every receipt and view mapping passes validation. It fails closed when the host cannot provide an exclusive directory rename. By default, replay remains `not-run / model-only`. An optional saved replay report is validated against the exact stale-generation trace, model digest, receipt digest, and current Python source digest; this flag does not execute Python or TLC, and the evidence does not carry over to other cases.

Receipt diagrams use this skill's Mermaid backend and pinned Pele `1.9.0` renderer. Node.js 22 or newer is required. The adapter draws only the validated selected trace, disables links/images, and makes no network calls during rendering. It does not invoke the native statechart TLC runner.

```text
python3 <repo-root>/skills/patpat-statechart/scripts/render_statechart_receipts.py \
  --receipt-dir <directory-containing-saved-receipts> \
  --view <view-mapping.json> \
  --repo-root <repository-root> \
  --out-dir <new-output-directory>
```

Before rendering, execute `npm ci` with the working directory set to `<repo-root>/skills/patpat-statechart/scripts`.

To include a previously saved replay report for the `stale-generation` case, add:

```text
  --replay-report <saved-replay-report.json>
```

The output contains a case index and, for every case, `.statechart.json`, `.mmd`, `.svg`, and `.html` files. HTML, SVG, and Mermaid are generated locally without remote assets or uploads. The SVG uses the Mermaid backend's state and transition layout; the exact raw TLC action, full trace, and `changed_keys` remain available in the SVG metadata, MMD comments, JSON, and visible HTML transition cards. The HTML places the phase and invariant color key beside the graph, then shows bounded TLC, static mapping, and replay evidence in separate panels. The key stays outside the Mermaid graph so it cannot skew short-path layout. Do not send project receipts to a remote renderer unless the user explicitly authorizes that data flow. MMD is an editable export; the local SVG/HTML is the primary offline presentation.

## Design reference

The receipt adapter calls only this skill's Mermaid backend (`scripts/backends/mermaid.ts`) and Pele. It does not call the native command's TLA+ frontend, compiler, graph passes, or TLC runner; it starts from the normalized TLC receipt instead of recompiling TLA+. The hand-off follows the same contract as [`patpat-formal-verify`](../../patpat-formal-verify/SKILL.md): map model actions to code and expected effects, prove mutants fail, and keep model and runtime evidence separate. Origin and license are in [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md).

The blueprint palette and grouped trace framing are inspired by the user's supplied statechart image. Color describes the authored model phase; the red mark describes an invariant break. They are not interchangeable. The local renderer preserves that visual grammar without transmitting receipt data to Pele or another external service.
