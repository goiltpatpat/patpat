# Third-party notices

`patpat-statechart` is part of Patpat and is covered by Patpat's MIT license in the repository root `LICENSE`.

## Derived code

The model-checking command in `scripts/` (parser, intermediate representation, chart passes, TLC runner, report and Mermaid backends) and its test corpus are derived from the MIT-licensed `statechart` skill in Cursor's public plugins repository, commit `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`. The notice below must stay with those files in every copy of this skill.

Patpat changes to the derived files:

- `scripts/run.ts`, `scripts/statechart.ts`, `scripts/janitor.ts`, `scripts/frontends/dot.ts`: direct Node process management in place of POSIX-shell cleanup, Windows support, and CRLF handling, including the CR Java on Windows writes before each LF.
- `scripts/backends/mermaid.ts`: optional legend suppression for receipt traces, and Unicode combining marks (`\p{M}`) kept so Thai text stays readable.
- `scripts/test/`: CRLF-normalized golden reads, `output-lines.test.ts`, and a Windows skip for the non-ASCII folder test.
- `scripts/package.json`: Patpat package identity and the pinned Pele renderer.

Patpat-authored files: `SKILL.md`, `references/chart-view.md`, `references/reading-results.md`, `references/receipt-rendering.md`, `scripts/statechart.cmd`, `scripts/render_receipt_chart.mjs`, `scripts/render_statechart_receipts.py`, and `examples/`. `references/render.md` keeps the derived Pele theme.

`scripts/package.json` also names Pele (`pele@1.9.0`, MIT; bundled Lucide icons, ISC) and fast-check (MIT, devDependency). `npm ci` installs them; they are not copied into this repository.

## Notice

```text
MIT License

Copyright (c) 2026 Lauren Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
