---
name: patpat-repository-diagram
description: Turn an explicitly requested idea, question, plan, or codebase into a beautiful interactive visual. Creates a self-contained HTML/SVG diagram from a user brief, repository evidence, or both; supports iterative refinement and five typed views. Use patpat-inspect for prose-only explanations and engineering skills for code changes.
---

# Patpat Interactive Diagram

Turn anything the user explicitly wants to understand, plan, or share into an interactive visual. Accept a short idea, a detailed plan, an existing repository, or a mix of brief and source evidence. Deliver one focused, self-contained HTML artifact with an editable typed JSON source and SVG export. Let users continue with requests such as “highlight the cache miss”, “add the approval branch”, or “switch to light theme”; preserve stable IDs and change only the requested parts.

Patpat owns this skill's schema, renderer, layout, viewer, output contract, and maintenance. It adapts current Archify methods for authoring, measured readability, validation-before-delivery, source-grounded interaction, and last-good preview; see [design references and attribution](references/spec-contract.md#selected-design-references) and [third-party notices](references/THIRD_PARTY_NOTICES.md). Do not install Archify or depend on its runtime.

For source investigation, read [repository truth](../patpat-loop/principles/repository-truth.md), apply the [investigation playbook](../patpat-loop/playbooks/investigation.md), and report with the [how-report contract](../patpat-inspect/references/how-report.md). Read the [operating protocol](../patpat-loop/references/operating-protocol.md) in full for sensitive, security, cross-cutting, or material architecture questions. Do not load the router.

## Scope

Use this route only when the user asks for a visual, map, diagram, explainer, or shareable view. A repository is optional. Do not turn prose-only questions or ordinary code inspections into diagrams. This skill creates artifacts; it does not edit application code, install dependencies, publish, or deliver externally.

Choose the smallest type that answers the question:

| Type | Use for |
| --- | --- |
| `architecture` | Component ownership, calls, stores, and supported boundaries |
| `workflow` | Ordered work, gates, branch conditions, retries, and outcomes |
| `sequence` | Calls and returns over time, including async messages |
| `dataflow` | Sources, transformations, stores, and consumers |
| `lifecycle` | States, transitions, retries, cancellation, and terminal outcomes |

Choose the type that makes the subject easiest to understand. If several fit, make a judgment and state it in the artifact's summary; ask only when the distinction materially changes the story. If the user asks for a chat-only visual, return editable source and state which render checks were unavailable. Create project files only when the user requests an artifact or the project convention clearly expects it.

## Optional Python import map

For an explicitly requested Python dependency map, use the Patpat-owned static analyzer to derive `depends_on` edges from Python syntax before authoring the diagram. It uses only the Python standard library, scans Git-tracked and non-ignored untracked `.py` files, and never executes repository code or follows symlinks. Default import roots are the Git root and `src/` when present; pass `--python-root` for other actual import roots and `--scope` to focus the scan. A successful bounded analysis writes a complete `.imports.json` sidecar outside the repository and writes a diagram source only when resolvable repository imports exist and the strict geometry and renderer-size gates pass. It stops without partial artifacts if the Git inventory exceeds 8 MB, the candidate count exceeds 10,000 Python files, scanned source bytes exceed 64 MB, or import facts exceed 25,000. These limits keep both analysis and its review report bounded.

```text
python3 <skill-root>/scripts/import_graph.py --repo-root <git-root> --out-dir <temporary-outside-root> --name <slug> [--scope <relative-directory>] [--python-root <relative-import-root>] [--language en|th]
python3 <skill-root>/scripts/render.py validate <temporary-outside-root>/<slug>.diagram.json --repo-root <git-root>
python3 <skill-root>/scripts/render.py finalize <temporary-outside-root>/<slug>.diagram.json --repo-root <git-root> --out-dir <destination> --name <slug>
python3 <skill-root>/scripts/render.py check <destination>/<slug>.html --repo-root <git-root>
```

Inspect the analyzer's JSON result before running the renderer commands above. If its status is `no-resolved-repository-imports`, keep the report and stop; no `.diagram.json` is created. A resource-limit error creates neither output file. Otherwise, the diagram contains only import relationships whose target is a parseable Python file inside the selected scope. The sidecar records hashes for readable files within the 1 MB cap, skipped files, standard-library imports, ambiguous or unresolved imports, layout adjustments, and analyzer limits. Oversize and non-regular sources are skipped before their contents are read and have no content hash. Do not hide unresolved counts or describe the graph as a call graph, runtime trace, or complete architecture. It does not infer symbol-level imports, import-time effects, or arbitrary dynamic loading. The generated spec must pass the renderer's strict geometry gate; if a safe route cannot be derived, keep the diagnostic report and do not emit a broken diagram. If the graph exceeds renderer limits, it likewise refuses to emit a truncated diagram. Keep the sidecar with the editable source during review; remove both when they are temporary.

## Trace and author

1. Pick the evidence mode. For a brief-only diagram, work from the user's stated facts and make no repository claims. For a codebase diagram, capture the Git root, full HEAD, and dirty state; inspect the call path, gates, errors, and side effects that change the story. Mixed evidence is allowed and remains visibly separated.
2. Use stable IDs for entities and relationships. Mark direct statements or source-supported claims `confirmed`, reasoned additions `inferred`, and unresolved facts `unknown` with a short reason. Brief claims are digest-bound but are not code-verified; repository claims need normalized relative paths and inclusive line ranges. A line range proves only what those bytes show. Never present static code paths as observed runtime behavior.
3. Author the type-specific JSON in a temporary directory outside the target repository. Follow the [source contract](references/spec-contract.md). Set the language to the user's language (`th` or `en`). Keep labels short, place the primary path first, keep branches near their owner, use groups only for evidenced boundaries, mark cycle-closing edges `feedback: true`, and omit detail that does not answer the request. Start graph diagrams with automatic positions and routes; inspect geometry diagnostics and the rendered view before adding complete `positions` or sparse `edge_hints` for a specific layout problem. These hints are supported for architecture, workflow, dataflow, and lifecycle graphs; sequence geometry remains governed by participant and message order. If TB feedback routes cross peer nodes, place returning source entities into separate explicit ordered layers and validate again; never suppress a blocking geometry warning. Geometry hints affect appearance only and never change authored relationships or evidence. In workflows, make the success or default path the clearest visual trunk; keep rejection, cancellation, failures, and blockers on distinct secondary exits. Show failure classification and explicit feedback transitions to the earliest invalid stage; do not label a terminal step as though it resumes the flow. Evidence certainty describes claim support, never whether a step passed or completed. Never embed source snippets, credentials, tokens, or private remote URLs.
4. For a multi-step explanation that benefits from guided reading, add optional schema 2 `views`: a small set of named stories whose ordered stable IDs point to authored nodes or relationships. Give each beat a reason to appear in that order, use a concise optional note for transitions the graph cannot express, and check the share link at the first, middle, and final beat. The viewer reveals only the selected beat's direct context; story order does not prove causality or runtime impact. Leave `views` out when a single overview answers the request.
5. Design for the reader: one clear title and a short summary; meaningful semantic shapes and color; labels that survive the desktop readability gate; generous route clearance; compact controls; and progressive disclosure for secondary exploration. Do not add decoration or inventory to fill space.
6. Choose the destination from the user's request or an existing artifact convention. Otherwise use `docs/diagrams/<slug>`. Never overwrite an existing artifact without the user's replacement request.

## Render and inspect

Use the renderer shipped beside this skill; do not substitute Mermaid or a third-party renderer for the requested Patpat HTML/SVG deliverable. Replace `<skill-root>` below with the absolute directory containing this loaded `SKILL.md`; it is a path placeholder, not literal shell syntax. Read the supported model and profile rules first:

```text
python3 <skill-root>/scripts/render.py guide --format text
python3 <skill-root>/scripts/render.py guide <diagram-type> --format text
```

Schema 1 makes a static, offline SVG/HTML artifact. Schema 2 enables interactions using only the exact trusted viewer shipped with this skill; the HTML pins it through a restrictive CSP hash. The viewer never executes diagram JSON or contacts external services. It works offline; live refresh is enabled only by the explicit `?patpat-preview=1` URL printed by Patpat's loopback preview command. Prefer schema 2 for a requested interactive visual. Omit `--repo-root` for brief-only work; pass the exact Git root whenever any evidence cites repository files. The optional `deployment-ownership` profile remains repo-only and fails closed unless every component is assigned exactly once to a directly source-confirmed boundary. Browser quality profiles are separate from the authored model profile.

Validate, render, and verify the output set:

```text
python3 <skill-root>/scripts/render.py validate <temporary-spec.json> [--repo-root <repository-root>]
python3 <skill-root>/scripts/render.py finalize <temporary-spec.json> [--repo-root <repository-root>] --out-dir <destination> --name <slug> [--browser-profile standard|showcase] [--browser <chromium>] [--public-source-links]
python3 <skill-root>/scripts/render.py check <destination>/<slug>.html [--repo-root <repository-root>]
```

`finalize` renders into private temporary storage, runs the strict artifact/evidence check and a local Chromium gate, then promotes only the passing set through a journaled, recoverable transaction. Promotion replaces files one at a time, so readers may observe a mixed set during that brief window; interruption triggers rollback or recovery, and uncertain ownership fails closed for manual review. A hidden `.patpat-diagram.lock` file remains in the output directory for cross-process coordination; leave it in place while renderer operations may run. The default `standard` gate saves its 1440×1100 screenshot and browser receipt beside the editable JSON, HTML, SVG, and artifact receipt. Use `--browser-profile showcase` to gate and retain desktop/tablet/mobile captures in both themes and the contact sheet as part of the same recoverable transaction. A failed gate leaves the previous output set intact. `--no-browser` explicitly skips only the browser gate; report that visual runtime remains unverified.

`--public-source-links` is opt-in and makes two unauthenticated direct requests to GitHub's public API. Links are emitted only for repository evidence whose bytes match the exact full commit; brief claims, working-tree files, unsupported remotes, private repositories, and unverified commits stay plain text. No Git credential helper, authorization header, or configured proxy is used. If the network check is unavailable, finalization succeeds without source links and records that result in the receipt.

Use standalone `browser-check` when inspecting an existing artifact or collecting captures without rebuilding it. Keep its screenshot and receipt in temporary paths unless requested. Use filenames that share one slug:

```text
python3 <skill-root>/scripts/render.py browser-check <destination>/<slug>.html [--repo-root <repository-root>] --screenshot <temporary-directory>/<slug>.browser.png --receipt <temporary-directory>/<slug>.browser.receipt.json
```

The default `standard` profile captures one 1440×1100 light-theme screenshot. The `showcase` profile captures desktop (1440×1100), tablet (1024×768), and mobile (390×844) in both light and dark themes, plus a contact sheet. It requires the schema 2 viewer and verifies the embedded viewer's CSS viewport width and height, screenshot dimensions, and horizontal page overflow. PNG chunks, checksums, compressed scanlines, and capture dimensions are verified before any screenshot enters a receipt. All captures, contact sheet, and receipt are stored as one recoverable output set:

```text
python3 <skill-root>/scripts/render.py browser-check <destination>/<slug>.html [--repo-root <repository-root>] --screenshot <temporary-directory>/<slug>.browser.png --receipt <temporary-directory>/<slug>.browser.receipt.json --profile showcase
```

For schema 2, the viewer supports an accessible keyboard-selectable finder for components and relationships, camera-revealing focus, automatic zoom-based MAP/READ/FULL depth (MAP below 100%, READ from 100% through 174%, FULL at 175% and above), semantic-kind and evidence-certainty lenses, pairwise component-role comparison, intent preview, a semantic passport with evidence links and upstream/downstream counts, upstream/downstream reach, exact authored routes with step navigation, relationship context, and a collapsible overview map beside the primary toolbar. Role comparison dims unrelated kinds, distinguishes the selected pair, highlights direct cross-kind links only, reports both directions, and provides a shareable deep link without inferring transitive impact. The overview shows visible node IDs and distinct start, decision, action, and outcome markers; selecting a node focuses it, while dragging pans the diagram. Manual depth remains available until Auto is selected again. It also supports deep links, light/dark and high-contrast themes, three visual presets, presentation mode with a visible exit fallback, responsive zoom steps, and reduced-motion-aware route traces. On narrow layouts, the initial pan centers the first authored node; presentation preserves the canvas center across its responsive width change and restores the prior pan on exit. Keyboard shortcuts are `/` search, `S` cycle style, `T` toggle theme, `E` open exports, `R` probe a selected route, `L` focus the semantic lens, `M` focus the overview, `F` enter presentation, `+`/`-` zoom, `0` reset, `?` guide, and `Escape` close or exit. Printing restores labels and graph elements regardless of active focus, filters, or MAP depth. Canonical PNG can be copied to the clipboard or downloaded; Copy PNG downloads the rendered image if clipboard access is unavailable or fails. JPEG/WebP, one auto-theme SVG (light by default and dark under the system color preference), the light/dark SVG pair, and finite route-only WebM exports exclude temporary viewer state. Route and directional-reach share cards are exact-size 1200×630 PNGs derived from the already resolved authored snapshot; long route cards keep both endpoints and label omitted component and relationship counts, and reach cards show each visible component and relationship's certainty as text alongside explicit omission counts. Browser-check proves the checked HTML loaded in the selected local browser and binds captures to that HTML; it does not prove semantic accuracy, exercise controls, or judge visual clarity. When interactions are part of the request and a browser is available, open the final HTML and exercise search/focus, one authored route or reach, theme, presentation exit, and a representative export. Inspect the screenshot or contact sheet separately.

Guided stories navigate ordered stable node or relationship IDs, highlight the current beat with direct context, and restore that exact beat from a shareable deep link. When interactions are part of the request and a browser is available, exercise the story's first, middle, and final beats in addition to other relevant controls.

Use the optional loopback preview when iterative authoring benefits from it:

```text
python3 <skill-root>/scripts/render.py preview <temporary-spec.json> [--repo-root <repository-root>] --name <slug>
```

Preview binds to `127.0.0.1` on an ephemeral port, watches the spec and any repository evidence, and serves only the last validated build when a candidate fails. It is a local authoring aid, not a hosted or shared service.

Compare two previously generated architecture artifacts only when the user asks to inspect structural change:

```text
python3 <skill-root>/scripts/render.py compare <previous.html> <current.html> --repo-root <repository-root> --out-dir <destination> --name <slug>
```

Comparison reports stable-ID `added`, `removed`, `changed`, `moved`, and `rerouted` records with receipt-bound rendered before/after SVG snapshots and the authored delta table. The snapshots retain the exact checked input models, source revision headers, and accessible titles/descriptions; the page remains static and uses one hashed local stylesheet. Moved records and inventories include authored layer and within-layer position. It does not infer impact, risk, compatibility, deployment state, or merge safety. Do not use it as a substitute for `patpat-impact`, tests, or review.

Run `self-test` after renderer changes. Its layout and safety checks do not prove that source claims are semantically correct or that a picture is perceptually clear. Run the repository validator when changing the skill or its output contract.

Run `python3 <skill-root>/scripts/import_graph.py --self-test` after analyzer changes. It checks bounded source reads, symlink/non-regular handling where supported, parser and unresolved-import contracts, cycle classification, and strict layout repair. The repository validator runs this check as part of its self-test.

Before delivery, verify:

- The question's main path, branches, calls, states, or boundaries are represented with the correct direction and conditions.
- Every `brief` claim is labeled as user-provided and not code-verified; every repository claim has a valid path, line range, digest, and current revision. Unsupported behavior stays `unknown` or is omitted.
- The rendered labels fit, nodes and labels do not collide, arrows remain readable, and line styles carry meaning without color. Interactive panels also contain long native-select options, status text, and relationship labels at mobile, breakpoint-edge, and desktop widths.
- The text outline and evidence tables expose the same entities and relationships as the SVG; schema 1 is static and schema 2 runs only the exact trusted viewer.
- No unrelated target file changed. Interrupted finalization auto-recovers only from a user-owned POSIX staging directory with mode `0700` and a journal with mode `0600`; if platform permissions cannot be proven, recovery fails closed and leaves files for manual review. Still run `check` afterward.
- Temporary specs, screenshots, and preview servers are cleaned up unless the user requested those files.

Correct the JSON when a check or screenshot exposes a defect, then repeat `finalize`, `check`, and browser inspection. Do not claim checks that were not run or describe layout diagnostics as perceptual review.

## Report

Return links to the HTML and editable JSON, with SVG and receipt links available as supporting artifacts. For repository-backed or mixed evidence, state the exact revision and whether each cited file came from committed content or the working tree. For brief-only work, state that claims came from the user's brief and were not code-verified. Separate semantic review, structural/output check, browser render check, and visual inspection; identify what remains unperformed and any unresolved unknowns.

## Proof closure

Close repository mutations through:

- [`patpat-verify`](../patpat-verify/SKILL.md)
- [`patpat-review`](../patpat-review/SKILL.md)
