import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

const [pidText, stage, tmp] = process.argv.slice(2);
const pid = Number(pidText);
const safeStage =
  typeof stage === "string" && path.isAbsolute(stage) && /^.+\.statechart-[A-Za-z0-9_-]+$/.test(path.basename(stage));
const safeTmp =
  typeof tmp === "string" && path.isAbsolute(tmp) && /^statechart-[A-Za-z0-9_-]+$/.test(path.basename(tmp));

if (!Number.isSafeInteger(pid) || pid <= 0 || !safeStage || !safeTmp) process.exit(2);

let done = false;
const cleanup = async () => {
  if (done) return;
  done = true;
  await new Promise<void>((resolve) => {
    const child =
      process.platform === "win32"
        ? spawn("taskkill.exe", ["/PID", String(pid), "/T", "/F"], {
            stdio: "ignore",
            windowsHide: true,
          })
        : spawn("kill", ["-KILL", "--", `-${pid}`], { stdio: "ignore" });
    child.once("error", () => resolve());
    child.once("close", () => resolve());
  });
  for (const target of [stage, tmp]) fs.rmSync(target, { recursive: true, force: true });
};

let intentional = false;
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk: string) => {
  if (chunk.includes("done\n")) intentional = true;
});
process.stdin.once("end", () => {
  if (intentional) process.exit(0);
  void cleanup();
});
