# Authoring, Layout, and Rendering Guide

Companion reference for [`patpat-repository-diagram`](../SKILL.md). Load when authoring graph layout, story views, Python import maps, or executing browser/comparison renders.

## Topology and routing guardrails

Apply three layout rules for clean first-draft geometry:

1. **Contiguous Lane Principle (หลักการเลนต่อเนื่อง)**: Keep components of the same boundary or stage in contiguous topological layers and vertical spans without interleaving unrelated nodes across distant layers. Group early-exit or terminal nodes (such as fail-closed stop or reject) into their originating stage lane to preserve contiguous bounds.
2. **Left-Feedback / Right-Forward Convention (ระเบียบคืนกลับชิดซ้าย)**: In ordered flows (TB or LR), advance forward progress monotonically along center and right tracks. Place nodes with retry, loop, or compensation transitions (`feedback: true`) at the leftmost index (`Index 0`) of shared `layout.layers`, with forward-branching nodes to the right, preventing routing collisions and node crossings.
3. **Concise Edge Labeling (ป้ายกำกับกระชับ)**: Keep transition and relationship labels brief (≤ 25 characters per line, at most 2 lines) to preserve clearance (> 2.0 SVG units) between routes and adjacent text boxes. Put secondary parameters and long descriptions into node claims and evidence records.

## Reader-first composition

Before authoring, define the intended reader, the question answered, and one evidenced conclusion. Build a semantic view rather than serializing a raw file list.

- **Architecture views**: Label components by evidenced responsibility and edges by the actual call, data, or event. Keep file paths and symbols in evidence details unless a dependency map was requested.
- **Workflows and lifecycles**: Use reader-facing actions and situations on labels; keep raw code names, state variables, and evidence IDs in details. Ensure shape and line style convey meaning without color. Show the main path first, then only decision or failure branches. Show feedback edges only when the source supports recovery; keep unrecoverable failure, cancellation, and rejection as terminal outcomes.
- **Boundaries and density**: Group components only at evidenced ownership or system boundaries. Aim for ~20 visible transitions or fewer; narrow the question or split into guided views rather than shrinking labels.
- **Static dependency maps**: State explicitly that edges come from static imports and do not imply runtime calls or a complete architecture.
- **Guided story views**: For talks or reviews, author schema 2 story views for ordered exploration (`Simulate flow` plays captioned walkthroughs and falls back to the main path by relationship kind). Story order does not prove causality or runtime impact.
- **Post-render inspection**: Inspect at reader size. Fix meaning and scope before geometry, then verify label wrapping, reading direction, branch distinction, edge clearance, and visual balance. Passing geometry diagnostics alone does not prove semantic accuracy.

## Optional Python import map

Use `import_graph.py` only for explicit dependency-map requests.

1. Run `python3 <skill-root>/scripts/import_graph.py --help` and send `--out-dir` outside the repository.
2. It parses static imports without executing code or following symlinks; its edges are import dependencies, not runtime calls.
3. Inspect the JSON report and sidecar before rendering. Report selected roots/scope, unresolved or ambiguous imports, skipped files, and limits; never present a partial inventory as complete.
4. If the report states `no-resolved-repository-imports`, keep the report and stop; resource-limit failures emit no partial artifacts. Remove temporary `.imports.json` files with their source spec after review.

## Render, browser gate, and comparison details

- **Schema selection**: Use schema 2 (offline interactive viewer) for interactive requests; schema 1 for static artifacts.
- **Transactional finalization**: `finalize` checks the artifact and evidence, runs a local Chromium gate by default, and promotes passing outputs one file at a time through a recoverable transaction. After interruption, automatic recovery runs only when ownership and permissions are proven; otherwise files remain untouched for manual review. Keep the renderer lock file while operations run.
- **Flags**: Pass `--repo-root` whenever evidence cites repo files. Discover command flags via `python3 <skill-root>/scripts/render.py <command> --help`.
  - `--overwrite`: Use only on an explicit replacement request.
  - `--public-source-links`: Opt-in; sends direct unauthenticated GitHub requests (no proxy/Git credentials) and emits links only for evidence matching the exact committed snapshot.
  - `--no-browser`: Use only when the browser gate cannot or should not run, and report browser behavior as unverified.
- **Browser inspection**: When interaction is requested and a browser is available, open the final artifact, exercise requested controls, and inspect the screenshot separately. A render receipt proves load and captured layout, not semantic accuracy or interaction behavior.
- **Comparison (`compare`)**: Use only to inspect structural changes between prior architecture artifacts; it does not infer runtime impact, risk, compatibility, or merge safety (route downstream risk to [`patpat-impact`](../../patpat-impact/SKILL.md)).
- **Cleanup**: Remove temporary specs, screenshots, receipts, and preview servers unless requested.
