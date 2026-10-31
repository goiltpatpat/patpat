# Upstream source and Patpat adaptations

The complete `pstack/skills/statechart` tree is copied from Cursor's public plugins repository at commit [`4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`](https://github.com/cursor/plugins/tree/4dd1d05818d19792e7cd6e818f1667f95f7e1dbe/pstack/skills/statechart). The original tree contained 407 files. Its MIT terms and copyright are preserved in [`LICENSE.pstack`](LICENSE.pstack).

Patpat keeps the upstream parser, intermediate representation, graph passes, TLC runner, report backends, and corpus. Local changes are limited to:

- `scripts/backends/mermaid.ts`: optional legend suppression for receipt traces, whose phase and evidence keys are shown in the adjacent Patpat report, and `\p{M}` Unicode combining-mark preservation so Thai vowel/tone marks remain readable UTF-8 in Mermaid output.
- `scripts/run.ts`, `scripts/statechart.ts`, `scripts/janitor.ts`, `scripts/frontends/dot.ts`, and `scripts/test/`: replace POSIX-shell process cleanup with direct Node process management, add Windows support, and normalize CRLF line endings for cross-platform checkouts. `outputLines` and `fileLines` drop the CR that Java on Windows writes before each LF, including the last line of each read chunk; `runJava` starts a `.ts` or `.js` java stand-in with Node because Windows cannot run it by its shebang. The corpus, CLI, and TLC-output tests read committed goldens with CRLF normalized, `test/output-lines.test.ts` covers CR at every chunk edge, and the non-ASCII folder test is skipped on Windows, where Java reads arguments in the ANSI code page.
- `scripts/statechart.cmd`: Windows entry point.
- `scripts/package.json`: Patpat package identity and the pinned Pele renderer (`kepano/pele` v1.9.0, MIT license; bundled Lucide icons under ISC) used by saved receipts.
- `scripts/render_receipt_chart.mjs`: Patpat adapter from an already-validated selected receipt path to the copied PStack Mermaid backend and local Pele renderer. It does not parse TLA+ or claim a selected trace is the complete reachable graph.
- `SKILL.md` (upstream `SKILL.md`): Patpat frontmatter, routing scope, the state and mutation gate, the no-mise `TLA2TOOLS`/`JAVA` note, receipt evidence, and replay boundaries. Patpat ships this tree as the first-class `patpat-statechart` skill.

Patpat receipt metadata remains alongside the chart as comments, typed JSON, and the offline HTML evidence view. The raw TLC action, exact `changed_keys`, bounded result, static source mapping, mutant identity, and replay status stay distinct. Rendering never invokes TLC or Python replay.
