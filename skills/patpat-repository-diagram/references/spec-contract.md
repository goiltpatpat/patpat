# Diagram source contract

## Schema, evidence, and layout fields

The renderer accepts UTF-8 JSON with this shared envelope:

```json
{
  "schema_version": 2,
  "type": "architecture",
  "language": "en",
  "title": "Request path",
  "summary": "How a request reaches persistence",
  "layout": {
    "direction": "LR",
    "layers": [["N1"], ["N2"], ["N3"]]
  },
  "evidence": [
    {
      "id": "S1",
      "origin": "repository",
      "path": "src/request.py",
      "start_line": 8,
      "end_line": 14,
      "claim": "The route delegates request handling to the service"
    }
  ],
  "body": {
    "components": [],
    "relationships": [],
    "boundaries": []
  }
}
```

- **Schema versions & `profile`**: Schema 1 emits a static artifact (no executable viewer). Schema 2 supports the same five types and the versioned trusted viewer. Optional `profile` is valid only on schema 2 `architecture` and accepts `{ "type": "deployment-ownership" }`, requiring every component to belong to one directly confirmed, evidenced boundary (fail-closed authored-evidence check, not live infra discovery).
- **`views` (schema 2)**: 1–12 guided stories, each with stable `id`, `label` (≤120 chars), ordered `focus` array of 1–40 unique existing node/relationship IDs, and optional `note` (≤320 chars). Viewer displays the beat + direct neighbors and `#story/<view-id>/<element-id>` deep links. Stories describe only the authored sequence (no transitive impact or inferred steps).

Evidence records select their source explicitly (`origin` defaults to `repository` when omitted):

```json
{ "id": "B1", "origin": "brief", "claim": "A cache miss reads the primary database." }
{ "id": "S1", "origin": "repository", "path": "src/cache.py", "start_line": 24, "end_line": 31, "claim": "A cache miss reads the primary database." }
```

- **`brief` vs `repository`**: Brief evidence (`id`, `claim`) records its digest in the receipt as `"not code-verified"` (user-stated, not proven by repo/runtime) and stays separate from repository evidence in mixed diagrams. Any repository evidence requires `--repo-root`; brief-only validate/finalize/check/preview/browser-check need no repository.
- **`language`**: Optional; auto-infers `th` if title/summary/body contains Thai text, else `en`. Set `th` explicitly for Thai UI labels and keep title, summary, and labels in the same language.
- **`layout`**: Optional. Graph diagrams use `direction` `LR` or `TB`; sequence diagrams use temporal left-to-right order and reject `TB`. Optional `layers` sets rank and reading order (every entity once; ordinary relationships forward; with `positions`, ranks progress along `direction` and peers follow layer-array order). Violations block finalization. Mark cycle-closing edges `feedback: true` to route around the outside; the renderer never removes or silently reverses edges.
- **`positions` & `edge_hints`** (graph diagrams only, optional without schema change):
  - `positions`: maps every graph entity once to top-left `{ "x": number, "y": number }` in SVG units (`0–20,000`). Renderer measures node size from label; leave room around nodes and below the shared header.
  - `edge_hints`: sparse map by relationship ID supporting `source_side`/`target_side` (`top`, `right`, `bottom`, `left`), 1–12 absolute `waypoints` (`{ "x", "y" }`, `0–20,000`), and `label` (`{ "segment": int, "offset": { "x", "y" } }`). Hinted sides get a short normal lead when the route does not leave/enter along that side; later segments cannot re-enter the hinted endpoint. `segment` indexes the final route's adjacent point pairs from `0`; `offset` is relative to segment midpoint (`±2,000` SVG units). Without an explicit label hint on a moved route, the label sits at the longest segment's midpoint.
  - Hints control geometry only (cannot add edges, change endpoints/direction, or strengthen evidence); add only after inspecting automatic layout. Invalid IDs/coordinates/fields/segment indexes fail validation/rendering. Geometry blockers (node/label overlap, label-to-route clearance `< 2` SVG units over 2 passes, route crossings, self-crossings, inconsistent rank direction, header intersections, clipped boundaries, out-of-canvas paths) fail finalization with measured distance, required clearance, label bounds, and segment endpoints. Architecture delta reports moved components, rerouted relationships, and label-layout changes.
- **Nodes, edges, and certainty**: Every entity, relationship, boundary, and lane needs a unique short `id`, concise `label` (wraps rather than elides), `certainty`, and `evidence_ids`. `confirmed` = directly stated in cited input; `inferred` = reasoned from cited input (visibly inferred); `unknown` = requires short `reason` and empty `evidence_ids`.
- **Repository file & byte limits**: Paths must be normalized, relative, ≤61 inclusive lines, and resolve to regular files with no symlinks in any path component (and regular file in the selected Git tree if present; absent paths are `working-tree` only with no permalink). Limits: `1,000,000` bytes per working-tree file and committed Git blob; `64,000,000` total source bytes across unique cited paths (counting working-tree and committed separately; repeated evidence on one path shares one read). Oversized or changing files block validation. Commit, working-tree, and brief-claim digests are recorded separately.
- **Public source permalinks**: Opt-in via `finalize --public-source-links`. Checks repo visibility and commit availability via direct unauthenticated GitHub API requests (no proxy or Git credentials). Only exact committed-snapshot digest matches become links; briefs and working-tree evidence stay text. Network/visibility/commit failures fail closed by omitting links while allowing finalization; receipt records verification time.

## Typed graph contract

Use exactly one body shape:

| `type` | Required body arrays | Entity kinds | Relationship kinds |
| --- | --- | --- | --- |
| `architecture` | `components`, `relationships`; optional `boundaries` | `actor`, `service`, `gateway`, `worker`, `database`, `cache`, `queue`, `external`, `component` | `call`, `data`, `event`, `deploys_to`, `contains`, `depends_on` |
| `workflow` | `steps`, `transitions`; optional `lanes` | `start`, `action`, `gate`, `decision`, `wait`, `terminal` | `next`, `yes`, `no`, `approval`, `retry`, `cancel`, `error`, `condition` |
| `sequence` | `participants`, `messages` | `actor`, `client`, `service`, `worker`, `database`, `queue`, `external`, `system` | `call`, `return`, `async`, `event` |
| `dataflow` | `entities`, `flows` | `source`, `transform`, `store`, `consumer`, `sink`, `queue` | `data`, `event`, `stream`, `snapshot` |
| `lifecycle` | `states`, `transitions` | `initial`, `state`, `terminal` | `transition`, `timeout`, `retry`, `cancel`, `error` |

- Relationships/transitions have `id`, `source`, `target`, `label`, `kind`, `certainty`, `evidence_ids`, and optional boolean `feedback`.
- `sequence` messages also require a unique positive integer `order`; direction is sender to receiver (including returns).
- `workflow` requires ≥1 `start` and ≥1 `terminal`; every `gate`/`decision` has ≥2 outgoing transitions; `terminal` has 0 outgoing; every step is reachable from a `start` and can reach a `terminal` (structural check only, not semantic completeness).
- `lifecycle` requires 1 `initial` and ≥1 `terminal` state.
- `boundaries` use `component_ids`; `lanes` use `step_ids`; both carry `certainty` and `evidence_ids`.

## Output and receipt bounds

- **Caps**: 80 entities, 160 relationships, 240 evidence entries, 1 MB source file. Packaged HTML, SVG, and receipt files: 8 MB each. Browser screenshot transaction: 16 MB per PNG, 48 MB all PNGs, 1 MB browser receipt, 66 MB showcase contact SVG, 64 KB recovery journal. Bounds are enforced before parsing/hashing/copying; files changing during read are rejected.
- **Canvas & readability**: Projected node-label readability must be ≥6 px at 960 px desktop width. Minimum SVG canvas width is 1200 units.
- **Outputs**: `<name>.diagram.json`, `<name>.svg`, `<name>.html`, `<name>.receipt.json`. HTML embeds SVG + text outline, works offline with no remote assets, and in schema 2 pins the exact shipped viewer bytes via restrictive CSP hash (author JSON cannot supply executable code). The viewer contacts no external service; only Patpat's loopback preview URL enables same-origin live status checks. The receipt binds spec, source mode, repo identity/revision, evidence digests, layout diagnostics, readability budget, and output digests.

## Layout diagnostics

- Self-loops reserve separate ports, lanes, and label space. In `LR`, top-peer loops route above and bottom-peer loops route below; middle-peer loops are rejected (use `TB` or reorder layers). Layers are never silently reordered; unresolved collisions block finalization.
- `TB` feedback routes from multiple peers in one shared layer can cross nodes before outer lanes, blocking finalization; separate returning sources into explicit ordered layers and re-validate.

## Renderer commands

Replace `<skill-root>` with the absolute directory containing this skill's `SKILL.md` (placeholder, not shell syntax). Requires Python 3.11+:

```text
python3 <skill-root>/scripts/render.py validate <spec.json> [--repo-root <repository-root>]
python3 <skill-root>/scripts/render.py finalize <spec.json> [--repo-root <repository-root>] --out-dir <output-directory> --name <slug>
python3 <skill-root>/scripts/render.py check <output-directory>/<slug>.html [--repo-root <repository-root>]
python3 <skill-root>/scripts/render.py browser-check <output-directory>/<slug>.html [--repo-root <repository-root>] --screenshot <temporary-directory>/<slug>.browser.png --receipt <temporary-directory>/<slug>.browser.receipt.json
python3 <skill-root>/scripts/render.py browser-check <output-directory>/<slug>.html [--repo-root <repository-root>] --screenshot <temporary-directory>/<slug>.browser.png --receipt <temporary-directory>/<slug>.browser.receipt.json --profile showcase
python3 <skill-root>/scripts/render.py preview <spec.json> [--repo-root <repository-root>] --name <slug>
python3 <skill-root>/scripts/render.py compare <previous.html> <current.html> --repo-root <repository-root> --out-dir <output-directory> --name <slug>
```

## Finalization and browser checks

- `finalize` refuses to overwrite existing files without `--overwrite` (prefer a new name). It builds in private temp storage, verifies artifact/evidence, runs the browser gate, and promotes via a journaled, recoverable file-by-file transaction (uncertain ownership fails closed for manual review). Keep `.patpat-diagram.lock` in the output directory while renderer operations may run.
- **Profiles & recovery**: `standard` captures a 1440×1100 light-theme PNG + HTML-bound browser receipt. `showcase` (schema 2 only) captures desktop (1440×1100), tablet (1024×768), and mobile (390×844) in both themes + contact sheet. `--no-browser` skips the runtime gate. POSIX auto-recovery requires user-owned `0700` staging dir and `0600` journal; otherwise files stay untouched for manual review. Run `check` after promotion.
- **Gate scope**: Both profiles verify theme, embedded SVG, exact CSS viewport dimensions, decoded PNG, no horizontal overflow, and (schema 2) viewer init. Neither judges semantic accuracy, interaction behavior, or visual clarity—inspect screenshots and test requested interactions in a real browser.

## Interactive viewer

Schema 2 viewer capabilities:
- **Navigation & depth**: Keyboard-selectable finder, camera-revealing focus, automatic zoom depth (`MAP` <100%, `READ` 100–174%, `FULL` ≥175%; manual depth persists until `Auto`), semantic-kind/certainty lenses, intent preview, evidence-linked semantic passport (direct/reachable counts), upstream/downstream reach, authored routes with step navigation, relationship context, overview map, deep links, light/dark/high-contrast themes, 3 visual presets, presentation mode (visible exit fallback, preserves canvas center across width changes and restores prior pan on exit), and reduced-motion-aware route traces. Narrow layouts center the first authored node initially.
- **Walkthrough player (`P`)**: Plays selected story, else sequence messages by `order`, else main path from start (preferring normal kinds over `error`, `cancel`, `timeout`, `retry`, `no`). Captions show position, label, endpoints, alternate paths, exception marker, and story note on final beat; pauses when page is hidden; polite live region announces steps unless narrated. Sound cues (`A`, in-page synthesized) and speech narration (`N`, prefers on-device voice, falls back to browser default) are off by default. In presentation mode, only player + exit button remain with larger captions.
- **Shortcuts**: `/` search, `S` visual style, `T` theme, `E` exports, `R` probe route, `L` semantic lens, `M` overview, `F` presentation, `P` walkthrough, `A` audio, `N` narration, `+`/`-` zoom, `0` reset, `?` guide, `Escape` close/exit, arrow keys step, `Space` play/pause (only on page, figure, or exit button).
- **Print & exports**: Print restores all elements/labels regardless of focus, filters, or MAP depth. Exports exclude temporary viewer state while keeping the selected visual preset: canonical PNG (copy or download; Copy falls back to download if clipboard fails), JPEG/WebP, auto-theme SVG (light default, dark on system preference), light/dark SVG pair, finite route-only WebM, and 1200×630 route/reach cards (long route cards keep both endpoints and count omitted items; reach cards label certainty of visible items + omitted counts). Viewer controls/captures are separate from editable source and deterministic receipt.

## Preview

`preview` binds `127.0.0.1` on an ephemeral port, serves generated HTML + status endpoint, watches spec/repo evidence, keeps last-good in-memory build on invalid edits, and exits on Ctrl-C (local authoring aid only).

## Architecture comparison

`compare` (also named `delta`) compares two checked architecture HTMLs by stable IDs/facts, emitting `<slug>.delta.{json,html,receipt.json}` with `added`, `removed`, `changed`, `moved`, `rerouted`, layer/within-layer positions, and receipt-bound before/after SVG snapshots (single-read snapshot, static HTML + hash-pinned local stylesheet). Does not infer impact, risk, compatibility, runtime behavior, or merge safety (use `patpat-impact`).

## Cleanup

Remove temporary specs, screenshots, receipts, and preview servers after review; keep only requested deliverables.

## Selected design references

Method-only design shortlist; do not import external DSLs, runtimes, or templates. See `THIRD_PARTY_NOTICES.md` for MIT attribution of the projected-label readability formula.
