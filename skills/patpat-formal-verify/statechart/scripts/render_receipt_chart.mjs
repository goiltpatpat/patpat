#!/usr/bin/env node

import fs from "node:fs";
import { render } from "pele";
import { mermaid } from "./backends/mermaid.ts";

const [inputPath, mmdPath, svgPath] = process.argv.slice(2);
if (!inputPath || !mmdPath || !svgPath) {
  process.stderr.write("usage: render_receipt_chart.mjs <chart.json> <chart.mmd> <chart.svg>\n");
  process.exit(2);
}

const xmlText = (value) =>
  String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

try {
  for (const outputPath of [mmdPath, svgPath])
    if (fs.existsSync(outputPath)) throw new Error(`refusing to replace existing file: ${outputPath}`);

  const input = JSON.parse(fs.readFileSync(inputPath, "utf8"));
  for (const region of input.chart.regions) {
    const paths = new Map(region.states.map((state) => [JSON.stringify(state.path), state.path]));
    for (const step of region.steps) {
      step.from = paths.get(JSON.stringify(step.from));
      step.to = paths.get(JSON.stringify(step.to));
      if (!step.from || !step.to) throw new Error("receipt step references an unknown PStack state path");
    }
  }
  const source = `${mermaid(input.chart, { includeLegend: false })}\n`;
  const result = render(source, {
    fontFamily: "Tahoma, sans-serif",
    fontFamilyMono: "Consolas, monospace",
    fontSize: 16,
    responsive: false,
    links: false,
    images: false,
    limit: 1_000_000,
    outputLimit: 8_000_000,
    maxEdges: 10_000,
  });
  const groupColors = {
    blue: ["#173950", "#85a9c5"],
    orange: ["#49391f", "#fbbf65"],
    purple: ["#302a55", "#c4b5fd"],
    yellow: ["#403b20", "#e8cf76"],
    teal: ["#123b4a", "#5eead4"],
    tan: ["#3b3028", "#c3a28b"],
    pink: ["#482a3c", "#f0a4cb"],
  };
  const coloredSvg = result.svg.replace(
    /(<g class="pele-node ([^"]*)"[^>]*>)([\s\S]*?<rect\b)([^>]*?)(\/?>)/g,
    (full, openG, classes, beforeRect, rectAttrs, endRect) => {
      if (classes.includes("breaks") || classes.includes("mayBreak")) return full;
      const group = classes.split(/\s+/).find((name) => Object.hasOwn(groupColors, name));
      if (!group) return full;
      const [fill, stroke] = groupColors[group];
      return `${openG}${beforeRect}${rectAttrs} style="fill:${fill};stroke:${stroke}"${endRect}`;
    },
  );
  const skin = [
    '<style>.pele{--pele-bg:#071b30;--pele-fg:#e8f2fb;--pele-fg-on-dark:#e8f2fb;--pele-muted:#adc3d7;--pele-line:#85a9c5;--pele-surface:#0c2742;--pele-surface-alt:#102e4c;--pele-border:#47708c;--pele-radius:10px}',
    '.pele .blue rect{fill:#173950!important}.pele .orange rect{fill:#49391f!important}.pele .purple rect{fill:#302a55!important}.pele .yellow rect{fill:#403b20!important}.pele .teal rect{fill:#123b4a!important}.pele .tan rect{fill:#3b3028!important}.pele .pink rect{fill:#482a3c!important}',
    '.pele .bugPath rect{stroke:#5eead4!important;stroke-width:2.5px!important}',
    '.pele .breaks rect{fill:#4c263c!important;stroke:#ff829c!important;stroke-width:3px!important}.pele .breaks text{fill:#fff!important}',
    '.pele .mayBreak rect{fill:#49391f!important;stroke:#fbbf65!important;stroke-width:3px!important}.pele .mayBreak text{fill:#fff!important}</style>',
    `<defs><pattern id="patpat-grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#24415e" stroke-width="0.65" opacity="0.10"/></pattern></defs>`,
    `<rect width="${result.width}" height="${result.height}" fill="#071b30"/>`,
    `<rect width="${result.width}" height="${result.height}" fill="url(#patpat-grid)"/>`,
    `<metadata>${xmlText(JSON.stringify(input.evidence ?? {}))}</metadata>`,
    `<desc>TLC selected receipt trace rendered with the Patpat Statechart Mermaid backend. Replay evidence is separate.</desc>`,
  ].join("");
  const svg = coloredSvg.replace(/(<svg\b[^>]*>)/, `$1${skin}`);
  if (svg === coloredSvg) throw new Error("Pele output has no SVG root element");
  fs.writeFileSync(mmdPath, source, { encoding: "utf8", flag: "wx" });
  fs.writeFileSync(svgPath, svg, { encoding: "utf8", flag: "wx" });
} catch (error) {
  process.stderr.write(`Patpat Statechart rendering failed: ${error instanceof Error ? error.message : String(error)}\n`);
  process.exit(2);
}
