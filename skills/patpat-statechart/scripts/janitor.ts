import fs from "node:fs";
import path from "node:path";
import { finished } from "node:stream/promises";
import { killGroup } from "./kill.ts";

const [pidText, stage, tmp] = process.argv.slice(2);
const pid = Number(pidText);
const safeStage =
  typeof stage === "string" && path.isAbsolute(stage) && /^.+\.statechart-[A-Za-z0-9_-]+$/.test(path.basename(stage));
const safeTmp =
  typeof tmp === "string" && path.isAbsolute(tmp) && /^statechart-[A-Za-z0-9_-]+$/.test(path.basename(tmp));

if (!Number.isSafeInteger(pid) || pid <= 0 || !safeStage || !safeTmp) process.exit(2);

let input = "";
process.stdin.setEncoding("utf8").on("data", (chunk: string) => (input += chunk));
await finished(process.stdin).catch(() => {});
if (input.includes("done\n")) process.exit(0);
const running = !input.includes("exited");
const groupOutlivesWorker = process.platform !== "win32";
if (running || groupOutlivesWorker) await killGroup(pid);
for (const target of [stage, tmp]) fs.rmSync(target, { recursive: true, force: true });
