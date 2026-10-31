# Third-party notices

`patpat-statechart` is part of Patpat and is covered by Patpat's MIT license in the repository root `LICENSE`.

The model-checking command in `scripts/` (parser, chart passes, TLC runner, report and Mermaid backends, and test corpus) and the chart-writing guidance are derived from the `statechart` skill in Cursor's public plugins repository, `pstack/skills/statechart` at commit `4dd1d05818d19792e7cd6e818f1667f95f7e1dbe`. [`UPSTREAM.md`](UPSTREAM.md) lists every Patpat change. The upstream notice below must stay with those files in every copy of this skill.

`scripts/package.json` also names Pele (`pele@1.9.0`, MIT) and fast-check (MIT, devDependency) as npm dependencies. They are installed by `npm ci` and are not copied into this repository.

## pstack statechart

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
