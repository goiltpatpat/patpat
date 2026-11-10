#!/usr/bin/env node
import { type ChildProcess, spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { parseArgs } from "node:util";
import { killGroup, messageOf } from "./run.ts";

const USAGE = `Usage: statechart SPEC.tla [--config FILE] [--view FILE] [--out DIR]

Checks SPEC.tla with TLC and draws its state graph as Mermaid. Above 500 states, the chart
draws only the paths to the rules that break, and with no rule broken there is no chart.mmd.
  --config FILE  TLC config. Default: SPEC.cfg beside the spec.
  --view FILE    A module that exports state(vars) and, if you want, step(action, from, to),
                 group(vars), colors, and title. state() returns a string for a flat chart, an
                 array for parent states, or an object for regions. Default: each state's values.
                 colors gives each group blue, orange, purple, yellow, teal, tan, or pink.
  --out DIR      Where to write report.md, chart.mmd, tlc.out, and tlc-RULE.out for each
                 property that breaks and each rule that breaks off the chart. The folder must
                 be new or empty. Default: SPEC-chart.
Exit code: TLC's own on the config as written: 0 when every rule holds, 1 when a rule breaks,
and 2 when TLC stops with an error, a signal kills the check, or the command cannot run. 130 or
143 when SIGINT or SIGTERM stops the check. Only exits 0 and 1 write output.`;

let stop: NodeJS.Signals | undefined;
const stopped = new Promise<void>((resolve) => {
  for (const name of ["SIGINT", "SIGTERM"] as const)
    process.on(name, () => {
      stop ??= name;
      resolve();
    });
});

let flags;
let specFile;
try {
  const args = parseArgs({
    allowPositionals: true,
    options: { config: { type: "string" }, view: { type: "string" }, out: { type: "string" } },
  });
  flags = args.values;
  [specFile] = args.positionals;
  if (args.positionals.length !== 1) throw new Error("Give one SPEC.tla.");
} catch (error) {
  console.error(`${messageOf(error)}\n\n${USAGE}`);
  process.exit(2);
}

const codeOf = (error: unknown) =>
  error instanceof Error && "code" in error ? error.code : undefined;

try {
  const configFile = flags.config ?? specFile.replace(/\.tla$/, ".cfg");
  if (!fs.existsSync(configFile))
    throw new Error(`Cannot find the TLC config ${configFile}. Pass --config FILE.`);
  const out = flags.out ?? specFile.replace(/\.tla$/, "-chart");
  let entries: string[] = [];
  let dest: string;
  try {
    entries = fs.readdirSync(out);
    dest = fs.realpathSync(out);
  } catch (error) {
    if (codeOf(error) !== "ENOENT")
      throw new Error(
        `${out} cannot be the output folder. ${messageOf(error)}. Pass --out with a new folder.`,
        { cause: error },
      );
    if (fs.lstatSync(out, { throwIfNoEntry: false }))
      throw new Error(
        `${out} cannot be the output folder. It is a broken link. Pass --out with a new folder.`,
        { cause: error },
      );
    dest = path.resolve(out);
  }
  if (entries.length)
    throw new Error(
      `${out} is not empty. It has ${entries.sort()[0]}. The command writes only to a new or empty folder. Pass --out with a new folder.`,
    );

  let base = path.dirname(dest);
  while (!fs.existsSync(base)) base = path.dirname(base);
  const stage = fs.mkdtempSync(path.join(base, `.${path.basename(dest)}.statechart-`));
  const done = path.join(stage, "done");
  let tmp: string | undefined;
  let janitor: ChildProcess | undefined;
  let exitCode: number;
  try {
    tmp = fs.mkdtempSync(path.join(os.tmpdir(), "statechart-"));
    const runtime = process.versions.deno
      ? [
          "run",
          "--quiet",
          "--no-prompt",
          "--allow-read",
          "--allow-write",
          "--allow-run",
          "--allow-env",
        ]
      : process.execArgv;
    const worker = spawn(
      process.execPath,
      [
        ...runtime,
        path.join(import.meta.dirname, "worker.ts"),
        stage,
        specFile,
        configFile,
        ...(flags.view ? [flags.view] : []),
      ],
      {
        detached: true,
        stdio: ["ignore", "inherit", "inherit"],
        env: { ...process.env, TMPDIR: tmp, TEMP: tmp, TMP: tmp },
      },
    );
    janitor = spawn(
      process.execPath,
      [
        ...process.execArgv,
        path.join(import.meta.dirname, "janitor.ts"),
        String(worker.pid),
        stage,
        tmp,
      ],
      { detached: true, stdio: ["pipe", "ignore", "ignore"], windowsHide: true },
    );
    const exited = new Promise<number>((resolve) =>
      worker.on("exit", (code) => resolve(code ?? 2)),
    );
    await Promise.race([stopped, exited]);
    await killGroup(worker.pid as number);
    const verdict = await exited;
    if (stop) {
      console.error(`${stop} stopped the check, so the command wrote nothing.`);
      exitCode = 128 + os.constants.signals[stop];
    } else if (worker.signalCode) {
      console.error(`${worker.signalCode} killed the check, so the command wrote nothing.`);
      exitCode = 2;
    } else if ((verdict === 0 || verdict === 1) && fs.existsSync(done)) {
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      try {
        try {
          fs.renameSync(done, dest);
        } catch (error) {
          // Windows will not rename onto any existing folder; rmdir still refuses one that is not empty.
          if (process.platform !== "win32" || codeOf(error) !== "EPERM") throw error;
          if (!fs.statSync(dest, { throwIfNoEntry: false })?.isDirectory()) throw error;
          fs.rmdirSync(dest);
          fs.renameSync(done, dest);
        }
      } catch (error) {
        if (codeOf(error) !== "ENOTEMPTY" && codeOf(error) !== "EEXIST") throw error;
        throw new Error(
          `${path.join(out, fs.readdirSync(dest).sort()[0])} appeared while the check ran, so the command wrote nothing. Pass --out with a new folder.`,
          { cause: error },
        );
      }
      const mmdPath = path.join(dest, "chart.mmd");
      if (fs.existsSync(mmdPath)) {
        try {
          const { render } = await import("pele");
          const mmdSource = fs.readFileSync(mmdPath, "utf8");
          const rendered = render(mmdSource, {
            fontFamily: "Tahoma, sans-serif",
            fontFamilyMono: "Consolas, monospace",
            fontSize: 16,
            limit: 1_000_000,
            outputLimit: 8_000_000,
            maxEdges: 10_000,
          });
          const svgPath = path.join(dest, "chart.svg");
          const htmlPath = path.join(dest, "chart.html");
          const style = `<style>
.pele {
  --pele-bg: #ffffff;
  --pele-fg: #1c1c1c;
  --pele-muted: #656565;
  --pele-line: #808080;
  --pele-surface: #fcfcfc;
  --pele-surface-alt: #f1f1f1;
  --pele-border: #c9c9c9;
}
.pele .blue rect { fill: #c3e0ff; }
.pele .orange rect { fill: #f0d3bf; }
.pele .purple rect { fill: #e3d5ff; }
.pele .yellow rect { fill: #f0dcbf; }
.pele .teal rect { fill: #bfe3df; }
.pele .tan rect { fill: #e5d9ce; }
.pele .pink rect { fill: #ffcbe6; }
.pele .breaks rect {
  fill: #ffecee !important;
  stroke: #e72e3b !important;
  stroke-width: 2.5px !important;
}
.pele .breaks text {
  fill: #cd2834 !important;
}
.pele .mayBreak rect {
  fill: #fff3e6 !important;
  stroke: #e8730c !important;
  stroke-width: 2.5px !important;
}
.pele .mayBreak text {
  fill: #b85a06 !important;
}
.pele .bugPath rect {
  stroke: #1680f3 !important;
  stroke-width: 2.5px !important;
}
.pele .repeats rect {
  stroke: #9b35d6 !important;
  stroke-width: 2.5px !important;
  stroke-dasharray: 6 3;
}
@media (prefers-color-scheme: dark) {
  .pele {
    --pele-bg: #1f1f1f;
    --pele-fg: #f5f5f5;
    --pele-muted: #acacac;
    --pele-line: #939393;
    --pele-surface: #121212;
    --pele-surface-alt: #2c2c2c;
    --pele-border: #4e4e4e;
  }
  .pele .blue rect { fill: #1b3857; }
  .pele .orange rect { fill: #573117; }
  .pele .purple rect { fill: #3c2e57; }
  .pele .yellow rect { fill: #573d17; }
  .pele .teal rect { fill: #174641; }
  .pele .tan rect { fill: #3d3127; }
  .pele .pink rect { fill: #57233e; }
  .pele .breaks rect {
    fill: #2e2021 !important;
    stroke: #cf2b35 !important;
  }
  .pele .breaks text {
    fill: #ff6463 !important;
  }
  .pele .mayBreak rect {
    fill: #2e2619 !important;
    stroke: #d0700f !important;
  }
  .pele .mayBreak text {
    fill: #ffa257 !important;
  }
  .pele .bugPath rect {
    stroke: #116dd2 !important;
  }
  .pele .repeats rect {
    stroke: #9a3fcf !important;
  }
}
</style>`;
          const styledSvg = rendered.svg.replace(/(<svg\b[^>]*>)/, `$1${style}`);
          fs.writeFileSync(svgPath, styledSvg, "utf8");
          const htmlContent = `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Statechart Viewer</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: #ffffff;
      color: #1c1c1c;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 100vh;
      padding: 24px;
    }
    @media (prefers-color-scheme: dark) {
      body {
        background: #1f1f1f;
        color: #f5f5f5;
      }
    }
    .top-bar {
      width: 100%;
      max-width: 1100px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 14px;
      margin-bottom: 20px;
      border-bottom: 1px solid rgba(128, 128, 128, 0.25);
    }
    .badge {
      font-family: Consolas, monospace;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.05em;
    }
    .nav-links a {
      color: #1680f3;
      text-decoration: none;
      font-size: 13px;
      font-family: Consolas, monospace;
      margin-left: 16px;
    }
    .nav-links a:hover {
      text-decoration: underline;
    }
    .chart-container {
      width: 100%;
      max-width: 1100px;
      border: 1px solid rgba(128, 128, 128, 0.25);
      border-radius: 12px;
      padding: 24px;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
      display: flex;
      justify-content: center;
      overflow: auto;
    }
    .chart-container svg {
      max-width: 100%;
      height: auto;
    }
  </style>
</head>
<body>
  <div class="top-bar">
    <div class="badge">STATECHART VIEWER</div>
    <div class="nav-links">
      <a href="chart.svg" target="_blank">Raw SVG</a>
      <a href="chart.mmd" target="_blank">Mermaid</a>
      <a href="report.md" target="_blank">Report</a>
    </div>
  </div>
  <div class="chart-container">
    ${styledSvg}
  </div>
</body>
</html>`;
          fs.writeFileSync(htmlPath, htmlContent, "utf8");
        } catch {
          // Pele optional render fallback
        }
      }
      process.stdout.write(fs.readFileSync(path.join(dest, "report.md")));
      console.log(`\nWrote ${out}`);
      exitCode = verdict;
    } else exitCode = 2;
  } finally {
    fs.rmSync(stage, { recursive: true, force: true });
    if (tmp) fs.rmSync(tmp, { recursive: true, force: true });
    janitor?.stdin?.end("done\n");
  }
  process.exit(exitCode);
} catch (error) {
  console.error(messageOf(error));
  process.exit(2);
}
