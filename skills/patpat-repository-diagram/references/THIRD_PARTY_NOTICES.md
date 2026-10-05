# Third-party notices

## Archify

Patpat adapts Archify's projected-label readability calculation from [`archify/renderers/shared/desktop-readability.mjs`](https://github.com/tt-a1i/archify/blob/594f6087358610bd16e64e5602976020871b6bff/archify/renderers/shared/desktop-readability.mjs) at source commit `594f6087358610bd16e64e5602976020871b6bff`. That file was byte-identical at the [`main` HEAD reviewed on 2026-10-05](https://github.com/tt-a1i/archify/blob/73aaa0696e8f72c232ea710e6fa94fd953f3e773/archify/renderers/shared/desktop-readability.mjs). The Python renderer applies the same projection rule—source text size multiplied by the smaller of one or rendered-diagram-width divided by viewBox width—and checks a 6 px desktop readability floor. The source implementation is MIT licensed.

The remaining renderer, typed schema, viewer, and authoring workflow are Patpat-owned. Patpat does not include Archify's template, branding, fonts, runtime, or dependencies.

```text
MIT License

Copyright (c) 2026 tt-a1i (Archify)
Copyright (c) 2025 Cocoon AI

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
