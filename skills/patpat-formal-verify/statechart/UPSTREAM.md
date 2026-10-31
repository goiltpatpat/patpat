# Upstream source and Patpat adaptations

The complete `pstack/skills/statechart` tree is copied from Cursor's public plugins repository at commit [`4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`](https://github.com/cursor/plugins/tree/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/statechart). The original tree contained 407 files. Its MIT terms and copyright are preserved in [`LICENSE.pstack`](LICENSE.pstack).

Patpat keeps the upstream parser, intermediate representation, graph passes, TLC runner, report backends, and corpus. Local changes are limited to:

- `scripts/backends/mermaid.ts`: optional legend suppression for receipt traces, whose phase and evidence keys are shown in the adjacent Patpat report, and `\p{M}` Unicode combining-mark preservation so Thai vowel/tone marks remain readable UTF-8 in Mermaid output.
- `scripts/run.ts`, `scripts/statechart.ts`, `scripts/janitor.ts`, `scripts/frontends/dot.ts`, and `scripts/test/`: replace POSIX-shell process cleanup with direct Node process management, add Windows support, and normalize CRLF line endings for cross-platform checkouts.
- `scripts/statechart.cmd`: Windows entry point.
- `scripts/package.json`: Patpat package identity and the pinned Pele renderer (`kepano/pele` v1.9.0, MIT license; bundled Lucide icons under ISC) used by saved receipts.
- `scripts/render_receipt_chart.mjs`: Patpat adapter from an already-validated selected receipt path to the copied PStack Mermaid backend and local Pele renderer. It does not parse TLA+ or claim a selected trace is the complete reachable graph.
- `STATECHART.md`: Patpat-owned statechart workflow, receipt evidence, and replay boundaries.

Patpat receipt metadata remains alongside the chart as comments, typed JSON, and the offline HTML evidence view. The raw TLC action, exact `changed_keys`, bounded result, static source mapping, mutant identity, and replay status stay distinct. Rendering never invokes TLC or Python replay.
